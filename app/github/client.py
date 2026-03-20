"""
GitHub API Client
==================

This module handles all communication with GitHub's REST API. It provides
methods to:

1. Fetch PR diff (the raw unified diff showing what changed)
2. Fetch file contents (full source code for context/RAG)
3. Fetch changed file list (which files were modified)
4. Post a PR review with inline comments (anchored to specific lines)
5. Post a summary comment on the PR conversation

GitHub API Authentication:
- We authenticate using installation access tokens (from auth.py)
- Every request includes the token in the Authorization header
- The token is scoped to the specific repos where our app is installed

GitHub API Versioning:
- We pin to version "2022-11-28" via X-GitHub-Api-Version header
- This ensures our code doesn't break when GitHub ships API changes
- This is a best practice for any API integration in production

Rate Limits:
- GitHub Apps get 5,000 requests/hour per installation
- That's plenty for our use case (~10-20 API calls per PR review)

Reference: https://docs.github.com/en/rest
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx
import structlog

from app.github.auth import get_installation_token

logger = structlog.get_logger()

GITHUB_API = "https://api.github.com"


@dataclass
class PRData:
    """
    All the data we fetch about a PR, bundled together.

    This is passed to the agent orchestrator so agents have full context.
    A dataclass (vs a dict) gives us type safety and autocomplete in the IDE.
    """

    repo_full_name: str       # e.g. "ninjacode911/myapp"
    pr_number: int
    commit_sha: str           # HEAD commit of the PR
    title: str
    diff: str                 # Raw unified diff (the actual code changes)
    changed_files: list[dict] # List of {filename, status, additions, deletions, patch}
    file_contents: dict[str, str]  # {filepath: full_file_content} for changed files


class GitHubClient:
    """
    Async GitHub API client for a specific installation.

    Usage:
        client = GitHubClient(installation_id=12345)
        pr_data = await client.fetch_pr_data("ninjacode911/myapp", 42)
        await client.post_review_comment(...)

    Why a class instead of standalone functions?
    - The installation_id and token are shared across all API calls for one webhook event
    - A class groups these related operations together with shared state
    - Makes it easy to test by mocking one object
    """

    def __init__(self, installation_id: int):
        self.installation_id = installation_id

    async def _get_headers(self) -> dict[str, str]:
        """
        Build the authorization headers for GitHub API requests.

        Delegates to auth.py which handles token caching and refresh.
        No client-level cache — auth.py's cache is the single source of truth.
        """
        token = await get_installation_token(self.installation_id)

        return {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def fetch_pr_data(self, repo_full_name: str, pr_number: int) -> PRData:
        """
        Fetch all data needed to review a PR in one method.

        This makes 3 API calls:
        1. GET /repos/{owner}/{repo}/pulls/{pr_number} — PR metadata + diff
        2. GET /repos/{owner}/{repo}/pulls/{pr_number}/files — list of changed files
        3. GET /repos/{owner}/{repo}/contents/{path} — full content per changed file

        We fetch full file contents (not just the diff) because our agents need
        surrounding context. The diff alone doesn't show imports, class definitions,
        or the rest of the function — all critical for understanding security and
        performance implications.

        Args:
            repo_full_name: "owner/repo" format (e.g. "ninjacode911/myapp")
            pr_number: The PR number

        Returns:
            PRData with diff, changed files, and full file contents
        """
        headers = await self._get_headers()

        async with httpx.AsyncClient(timeout=30.0) as http:
            # --- 1. Fetch PR metadata ---
            pr_response = await http.get(
                f"{GITHUB_API}/repos/{repo_full_name}/pulls/{pr_number}",
                headers=headers,
            )
            pr_response.raise_for_status()
            pr_json = pr_response.json()

            commit_sha = pr_json["head"]["sha"]
            title = pr_json["title"]

            # --- 2. Fetch the raw diff ---
            # By setting Accept to "application/vnd.github.diff", GitHub returns
            # the raw unified diff instead of JSON. This is the same format you
            # see with `git diff` — it's what our agents will analyze.
            diff_response = await http.get(
                f"{GITHUB_API}/repos/{repo_full_name}/pulls/{pr_number}",
                headers={**headers, "Accept": "application/vnd.github.diff"},
            )
            diff_response.raise_for_status()
            diff = diff_response.text

            # --- 3. Fetch list of changed files ---
            # This gives us structured data: filename, status (added/modified/removed),
            # number of additions/deletions, and the patch (per-file diff).
            # We paginate because large PRs can have 100+ files.
            changed_files = []
            page = 1
            while page <= 30:  # Cap at 3000 files to prevent runaway loops
                files_response = await http.get(
                    f"{GITHUB_API}/repos/{repo_full_name}/pulls/{pr_number}/files",
                    headers=headers,
                    params={"per_page": 100, "page": page},
                )
                files_response.raise_for_status()
                batch = files_response.json()
                if not batch:
                    break
                changed_files.extend(batch)
                if len(batch) < 100:
                    break
                page += 1

            # --- 4. Fetch full file contents for each changed file ---
            # We need the complete source code (not just the diff) for RAG context.
            # The agents can then understand imports, class hierarchy, etc.
            file_contents = {}
            for file_info in changed_files:
                filename = file_info["filename"]
                status = file_info["status"]

                # Skip deleted files and binary files — no content to review
                if status == "removed":
                    continue

                try:
                    content = await self._fetch_file_content(
                        http, headers, repo_full_name, filename, commit_sha
                    )
                    if content is not None:
                        file_contents[filename] = content
                except Exception as e:
                    # Non-fatal: if we can't fetch one file, continue with the rest
                    logger.warning(
                        "Failed to fetch file content",
                        filename=filename,
                        error=str(e),
                    )

        logger.info(
            "Fetched PR data",
            repo=repo_full_name,
            pr=pr_number,
            changed_files=len(changed_files),
            files_with_content=len(file_contents),
        )

        return PRData(
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            commit_sha=commit_sha,
            title=title,
            diff=diff,
            changed_files=changed_files,
            file_contents=file_contents,
        )

    async def _fetch_file_content(
        self,
        http: httpx.AsyncClient,
        headers: dict,
        repo_full_name: str,
        filepath: str,
        ref: str,
    ) -> str | None:
        """
        Fetch the full content of a single file at a specific commit.

        GitHub's Contents API returns file content as base64-encoded string.
        We decode it to get the actual source code text.

        Why base64? Because GitHub's API is JSON-based, and JSON can't safely
        contain arbitrary binary content. Base64 encodes binary as ASCII text.
        This is the same encoding used in email attachments (MIME).

        Args:
            http: The httpx client (reused for connection pooling)
            headers: Auth headers
            repo_full_name: "owner/repo"
            filepath: Path to the file in the repo
            ref: Git ref (commit SHA) to fetch the file at

        Returns:
            The file content as a string, or None if the file is binary/too large
        """
        response = await http.get(
            f"{GITHUB_API}/repos/{repo_full_name}/contents/{filepath}",
            headers=headers,
            params={"ref": ref},
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()
        data = response.json()

        # GitHub returns "file" type for regular files.
        # Skip directories, symlinks, or submodules.
        if data.get("type") != "file":
            return None

        # Files > 1MB use a different API (Blobs). Skip for now — these are
        # usually auto-generated or binary files, not worth reviewing.
        if data.get("size", 0) > 1_000_000:
            logger.info("Skipping large file", filepath=filepath, size=data["size"])
            return None

        # Decode the base64-encoded content
        content_b64 = data.get("content", "")
        try:
            return base64.b64decode(content_b64).decode("utf-8")
        except (UnicodeDecodeError, Exception):
            # Binary file — can't decode as UTF-8
            return None

    async def post_review(
        self,
        repo_full_name: str,
        pr_number: int,
        commit_sha: str,
        body: str,
        comments: list[dict],
    ) -> dict:
        """
        Post a pull request review with inline comments.

        This is the core output mechanism of CodeProbe. A "review" in GitHub terms
        is a batch of inline comments submitted together, optionally with a top-level
        body and an event type (APPROVE, REQUEST_CHANGES, COMMENT).

        Each inline comment is anchored to a specific file and line, so it appears
        right next to the relevant code — just like a human reviewer would comment.

        GitHub's review API is atomic: either all comments post successfully, or
        none do. This prevents partial reviews that would confuse developers.

        Args:
            repo_full_name: "owner/repo"
            pr_number: PR number
            commit_sha: The exact commit SHA these comments reference
            body: The top-level review summary (shown above inline comments)
            comments: List of dicts with keys:
                - path: file path (e.g. "src/auth/login.py")
                - line: line number in the diff (the new file's line number)
                - body: the comment text (Markdown supported)

        Returns:
            The GitHub API response as a dict
        """
        headers = await self._get_headers()

        # We use "COMMENT" event — this posts the review without approving or
        # requesting changes. Our bot shouldn't block PRs at the GitHub level;
        # instead, we indicate blocking via the Health Score in the summary.
        review_payload = {
            "commit_id": commit_sha,
            "body": body,
            "event": "COMMENT",
            "comments": comments,
        }

        async with httpx.AsyncClient(timeout=30.0) as http:
            response = await http.post(
                f"{GITHUB_API}/repos/{repo_full_name}/pulls/{pr_number}/reviews",
                headers=headers,
                json=review_payload,
            )
            response.raise_for_status()

        logger.info(
            "Posted PR review",
            repo=repo_full_name,
            pr=pr_number,
            inline_comments=len(comments),
        )

        return response.json()

    async def post_comment(
        self, repo_full_name: str, pr_number: int, body: str
    ) -> dict:
        """
        Post a standalone comment on the PR conversation (not inline).

        Used for the summary comment (Health Score, finding counts, executive summary)
        when we don't have inline comments, or as a fallback.

        This uses the Issues API (PRs are issues in GitHub's data model) rather
        than the Pull Request Review API.

        Args:
            repo_full_name: "owner/repo"
            pr_number: PR number
            body: Comment text (Markdown)

        Returns:
            The GitHub API response as a dict
        """
        headers = await self._get_headers()

        async with httpx.AsyncClient(timeout=30.0) as http:
            response = await http.post(
                f"{GITHUB_API}/repos/{repo_full_name}/issues/{pr_number}/comments",
                headers=headers,
                json={"body": body},
            )
            response.raise_for_status()

        logger.info("Posted PR comment", repo=repo_full_name, pr=pr_number)

        return response.json()
