"""
Redis Cache for PR Review Deduplication
========================================

When a developer pushes multiple commits quickly (or force-pushes), GitHub sends
a webhook for each push. Without caching, we'd re-analyze the same PR multiple times,
wasting Groq API quota and spamming the PR with duplicate comments.

Solution: Before analyzing a PR, we check Redis: "Have we already reviewed this
exact commit SHA?" If yes, we skip the analysis entirely.

Why Redis (Upstash) instead of in-memory cache?
- Our Render free tier restarts the server frequently (cold starts)
- In-memory cache would be lost on every restart
- Redis persists across restarts and is shared if we scale to multiple workers
- Upstash's serverless Redis gives us 10K requests/day free — more than enough

Cache key structure: "ninjacg:reviewed:{commit_sha}"
Cache value: "1" (just a flag — we don't store the review result here, that's in Postgres)
TTL: 7 days (after which re-analysis is allowed)
"""

from __future__ import annotations

import redis.asyncio as redis
import structlog

from app.config import settings

logger = structlog.get_logger()

# Connection pool — reused across requests for efficiency.
# Redis connections are expensive to create (TCP handshake + TLS negotiation).
# A pool keeps connections open and reuses them.
_redis_client: redis.Redis | None = None

# Cache TTL in seconds (7 days)
CACHE_TTL = 7 * 24 * 60 * 60


def _get_redis_client() -> redis.Redis:
    """
    Get or create the Redis client singleton.

    Uses lazy initialization — the client is created on first use, not at import time.
    This prevents connection errors during module import (e.g., in tests).
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.upstash_redis_url,
            decode_responses=True,
        )
    return _redis_client


def _cache_key(commit_sha: str) -> str:
    """Build the Redis key for a commit SHA."""
    return f"ninjacg:reviewed:{commit_sha}"


async def is_already_reviewed(commit_sha: str) -> bool:
    """
    Check if a commit has already been reviewed.

    This is called at the start of every webhook handler to short-circuit
    duplicate analysis. Returns True if we should skip.

    Args:
        commit_sha: The HEAD commit SHA of the PR

    Returns:
        True if this commit has already been reviewed, False otherwise
    """
    try:
        client = _get_redis_client()
        result = await client.exists(_cache_key(commit_sha))
        if result:
            logger.info("Cache hit — skipping re-analysis", commit_sha=commit_sha[:8])
        return bool(result)
    except Exception as e:
        # If Redis is down, we proceed with analysis (fail open).
        # Better to review a PR twice than to miss a review entirely.
        logger.warning("Redis check failed, proceeding with analysis", error=str(e))
        return False


async def mark_as_reviewed(commit_sha: str) -> None:
    """
    Mark a commit as reviewed in the cache.

    Called after successfully posting a review to GitHub.
    The TTL ensures stale entries are automatically cleaned up.

    Args:
        commit_sha: The HEAD commit SHA that was reviewed
    """
    try:
        client = _get_redis_client()
        await client.set(_cache_key(commit_sha), "1", ex=CACHE_TTL)
        logger.info("Cached review result", commit_sha=commit_sha[:8], ttl_days=7)
    except Exception as e:
        # Non-fatal — if we can't cache, we'll just re-analyze next time
        logger.warning("Redis set failed", error=str(e))


async def invalidate_cache(commit_sha: str) -> None:
    """
    Remove a commit from the cache, forcing re-analysis.

    Used by the /reanalyze endpoint when a user manually requests re-review.

    Args:
        commit_sha: The commit SHA to invalidate
    """
    try:
        client = _get_redis_client()
        await client.delete(_cache_key(commit_sha))
        logger.info("Cache invalidated", commit_sha=commit_sha[:8])
    except Exception as e:
        logger.warning("Redis delete failed", error=str(e))
