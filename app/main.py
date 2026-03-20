"""
Ninja Code Guard — FastAPI Application Entry Point
=============================================

This is the main entry point for the Ninja Code Guard backend. It sets up:

1. The FastAPI application with CORS middleware
2. The /health endpoint (used by Render health checks and the pre-warm cron)
3. The /webhook/github endpoint (receives PR events from GitHub)

Request lifecycle for a PR review:
    GitHub webhook → HMAC validation → Redis cache check → fetch PR data
    → (Week 3+: run agents) → post review comments → cache result

The webhook handler uses FastAPI's "Background Tasks" feature to process
the review asynchronously. This means we return 200 to GitHub immediately
(within their 10-second timeout) and do the heavy lifting in the background.
Without this, GitHub would retry the webhook if we took too long.
"""

import asyncio
import json
import traceback

from fastapi import (
    BackgroundTasks, Depends, FastAPI, Header, HTTPException,
    Request, Response, Security,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
import structlog

from app.config import settings

# ── API Key auth for dashboard endpoints ──────────────────────────────────
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(_api_key_header)):
    """Reject dashboard API requests that don't carry a valid API key."""
    if not settings.dashboard_api_key:
        return  # No key configured → allow (dev mode)
    if api_key != settings.dashboard_api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")


from app.agents.performance_agent import PerformanceAgent
from app.agents.security_agent import SecurityAgent
from app.agents.style_agent import StyleAgent
from app.agents.synthesizer import synthesize
from app.context.indexer import index_repo_files
from app.context.retriever import retrieve_context
from app.db.postgres import save_review
from app.db.redis_cache import is_already_reviewed, mark_as_reviewed
from app.github.client import GitHubClient
from app.github.comment_formatter import (
    findings_to_review_comments,
    format_inline_comment,
    format_summary_comment,
)
from app.github.webhook import validate_webhook_signature

logger = structlog.get_logger()

_is_production = settings.environment == "production"

app = FastAPI(
    title="Ninja Code Guard",
    description="Multi-agent PR review system",
    version="0.1.0",
    # Disable auto-generated docs in production (exposes API schema)
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

# CORS middleware allows the Next.js dashboard (on Vercel) to call our API.
# In production, restrict origins to your actual Vercel domain.
_allowed_origins = (
    [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
    if settings.cors_allowed_origins
    else ["http://localhost:3000"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key", "X-GitHub-Event", "X-Hub-Signature-256"],
)


@app.get("/health")
async def health_check():
    """
    Health check endpoint.

    Used by:
    - Render.com to verify the service is running (healthCheckPath in render.yaml)
    - The GitHub Actions pre-warm cron to keep the service from going cold
    - Our Next.js dashboard to show service status
    """
    return {"status": "ok", "service": "Ninja Code Guard"}


# --- Dashboard API Endpoints ---


@app.get("/api/repos/{owner}/{repo}/reviews")
async def get_reviews(owner: str, repo: str, _=Depends(verify_api_key)):
    """Get recent PR reviews for a repo (used by dashboard)."""
    from app.db.postgres import get_repo_reviews
    repo_full_name = f"{owner}/{repo}"
    reviews = await get_repo_reviews(repo_full_name)
    return {"repo": repo_full_name, "reviews": reviews}


@app.get("/api/repos/{owner}/{repo}/stats")
async def get_stats(owner: str, repo: str, _=Depends(verify_api_key)):
    """Get aggregate stats for a repo (used by dashboard)."""
    from app.db.postgres import get_repo_reviews
    repo_full_name = f"{owner}/{repo}"
    reviews = await get_repo_reviews(repo_full_name, limit=50)
    if not reviews:
        return {"repo": repo_full_name, "total_reviews": 0, "avg_health_score": 0}
    avg_score = sum(r.get("health_score", 0) for r in reviews) / len(reviews)
    return {
        "repo": repo_full_name,
        "total_reviews": len(reviews),
        "avg_health_score": round(avg_score),
        "reviews": reviews[:10],
    }


# --- Webhook Actions (what to do for each event type) ---

# We only process these PR actions. Others (labeled, assigned, etc.) are irrelevant.
RELEVANT_PR_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}


async def _process_pr_review(
    repo_full_name: str,
    pr_number: int,
    commit_sha: str,
    installation_id: int,
) -> None:
    """
    Background task: fetch PR data and post a review.

    Pipeline:
    1. Fetch PR diff and file contents from GitHub
    2. Index files into ChromaDB for RAG context
    3. Run 3 domain agents IN PARALLEL (asyncio.gather)
    4. Merge all findings and compute health score
    5. Post review to GitHub
    6. Cache result in Redis
    """
    try:
        logger.info(
            "Starting PR review",
            repo=repo_full_name,
            pr=pr_number,
            sha=commit_sha[:8],
        )

        # Step 1: Fetch PR data
        client = GitHubClient(installation_id)
        pr_data = await client.fetch_pr_data(repo_full_name, pr_number)

        # Step 2: Index files for RAG context
        # This embeds the file contents into ChromaDB so agents can
        # semantically search for related code across the repo
        rag_context = ""
        try:
            collection_name = await index_repo_files(
                repo_full_name, pr_data.file_contents
            )
            rag_context = await retrieve_context(
                collection_name, pr_data.diff[:5000]
            )
        except Exception as rag_err:
            logger.warning("RAG context unavailable", error=str(rag_err))

        # Step 3: Run all 3 domain agents IN PARALLEL
        # asyncio.gather() runs all three concurrently — total latency is
        # max(agent_latencies) instead of sum(agent_latencies).
        # With Groq at 500+ tokens/sec, each agent takes 2-5 seconds.
        # Parallel: ~5 seconds total. Sequential: ~15 seconds.
        security_agent = SecurityAgent()
        performance_agent = PerformanceAgent()
        style_agent = StyleAgent()

        security_findings, performance_findings, style_findings = await asyncio.gather(
            security_agent.review(pr_data, rag_context),
            performance_agent.review(pr_data, rag_context),
            style_agent.review(pr_data, rag_context),
        )

        logger.info(
            "All agents completed",
            security=len(security_findings),
            performance=len(performance_findings),
            style=len(style_findings),
            total=len(security_findings) + len(performance_findings) + len(style_findings),
            repo=repo_full_name,
            pr=pr_number,
        )

        # Step 4: Synthesize — deduplicate, rank, score, summarize
        review = synthesize(security_findings, performance_findings, style_findings)

        # Post the review to GitHub
        if review.findings:
            # Post inline comments anchored to specific lines
            review_comments = findings_to_review_comments(review.findings)
            try:
                await client.post_review(
                    repo_full_name,
                    pr_number,
                    commit_sha,
                    body=format_summary_comment(review),
                    comments=review_comments,
                )
            except Exception as review_err:
                # If inline comments fail (e.g., line not in diff), fall back to summary only
                logger.warning(
                    "Inline review failed, posting summary comment instead",
                    error=str(review_err),
                )
                await client.post_comment(
                    repo_full_name, pr_number, format_summary_comment(review)
                )
        else:
            # No findings — post a clean bill of health
            await client.post_comment(
                repo_full_name,
                pr_number,
                format_summary_comment(review),
            )

        # Save to Neon Postgres (for dashboard)
        await save_review(repo_full_name, pr_number, commit_sha, review)

        # Mark this commit as reviewed in Redis cache
        await mark_as_reviewed(commit_sha)

        logger.info(
            "PR review completed",
            repo=repo_full_name,
            pr=pr_number,
            sha=commit_sha[:8],
        )

    except Exception as e:
        # Log the full traceback so we can debug failures
        logger.error(
            "PR review failed",
            repo=repo_full_name,
            pr=pr_number,
            error=str(e),
            traceback=traceback.format_exc(),
        )


@app.post("/webhook/github")
async def webhook_github(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(..., alias="X-GitHub-Event"),
    body: bytes = Depends(validate_webhook_signature),
):
    """
    Receive and process GitHub webhook events.

    This endpoint is called by GitHub whenever a PR event occurs on repos
    where Ninja Code Guard is installed.

    How the flow works:
    1. FastAPI calls validate_webhook_signature() BEFORE this function runs
       (it's a Depends() dependency). If HMAC validation fails, we never get here.
    2. We parse the validated payload and check if it's a relevant event.
    3. If it's a PR event we care about, we check Redis cache.
    4. If not cached, we enqueue the review as a background task.
    5. We return 200 immediately — GitHub expects a response within 10 seconds.

    Why background tasks?
    - GitHub has a 10-second webhook timeout. If we don't respond in time,
      GitHub marks the delivery as failed and may retry (causing duplicates).
    - Our actual review takes 15-20 seconds (agent calls + synthesis).
    - So we acknowledge receipt immediately and process in the background.

    Args:
        request: The FastAPI request object
        background_tasks: FastAPI's background task queue
        x_github_event: The event type header (e.g., "pull_request")
        body: The validated request body (returned by validate_webhook_signature)
    """
    # Parse the validated JSON payload
    payload = json.loads(body)

    # We only handle pull_request events for now
    if x_github_event != "pull_request":
        logger.debug("Ignoring non-PR event", github_event=x_github_event)
        return {"status": "ignored", "reason": f"event type: {x_github_event}"}

    action = payload.get("action", "")
    if action not in RELEVANT_PR_ACTIONS:
        logger.debug("Ignoring irrelevant PR action", action=action)
        return {"status": "ignored", "reason": f"action: {action}"}

    # Extract key data from the webhook payload
    pr = payload["pull_request"]
    repo_full_name = payload["repository"]["full_name"]
    pr_number = payload["number"]
    commit_sha = pr["head"]["sha"]

    # Skip draft PRs — they're not ready for review
    if pr.get("draft", False):
        logger.info("Skipping draft PR", repo=repo_full_name, pr=pr_number)
        return {"status": "ignored", "reason": "draft PR"}

    # Check Redis cache — have we already reviewed this exact commit?
    if await is_already_reviewed(commit_sha):
        return {"status": "skipped", "reason": "already reviewed", "sha": commit_sha[:8]}

    # Get the installation ID (needed for GitHub App authentication)
    installation_id = payload.get("installation", {}).get("id")
    if not installation_id:
        logger.error("No installation ID in webhook payload")
        return Response(status_code=400, content="Missing installation ID")

    # Enqueue the review as a background task
    # This returns 200 to GitHub immediately while processing continues
    background_tasks.add_task(
        _process_pr_review,
        repo_full_name=repo_full_name,
        pr_number=pr_number,
        commit_sha=commit_sha,
        installation_id=installation_id,
    )

    logger.info(
        "Webhook received — review enqueued",
        repo=repo_full_name,
        pr=pr_number,
        sha=commit_sha[:8],
        action=action,
    )

    return {
        "status": "accepted",
        "pr": pr_number,
        "sha": commit_sha[:8],
    }
