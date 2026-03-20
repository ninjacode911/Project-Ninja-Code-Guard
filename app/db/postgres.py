"""
Neon Postgres Database Client
===============================

Stores PR review history for the dashboard: health scores, finding counts,
executive summaries, and full findings JSON.

Uses psycopg2 for synchronous queries (sufficient for dashboard reads)
and asyncpg for async writes from the webhook pipeline.

Schema is auto-created on first connection via ensure_tables().
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import structlog

from app.config import settings
from app.models.findings import SynthesizedReview

logger = structlog.get_logger()

# ── Connection pool (reuse connections instead of connect-per-query) ──────
_pool = None


async def _get_pool():
    global _pool
    if _pool is None:
        import asyncpg
        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=1,
            max_size=5,
            command_timeout=10,
        )
    return _pool


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pr_reviews (
    id              TEXT PRIMARY KEY,
    repo_full_name  TEXT NOT NULL,
    pr_number       INT NOT NULL,
    commit_sha      TEXT NOT NULL,
    health_score    INT NOT NULL,
    critical_count  INT DEFAULT 0,
    high_count      INT DEFAULT 0,
    medium_count    INT DEFAULT 0,
    low_count       INT DEFAULT 0,
    summary         TEXT,
    findings        JSONB NOT NULL DEFAULT '[]',
    duration_ms     INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pr_reviews_repo ON pr_reviews(repo_full_name);
CREATE INDEX IF NOT EXISTS idx_pr_reviews_sha ON pr_reviews(commit_sha);
"""


async def ensure_tables():
    """Create the pr_reviews table if it doesn't exist."""
    if not settings.database_url:
        logger.warning("DATABASE_URL not set — skipping table creation")
        return

    try:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            await conn.execute(CREATE_TABLE_SQL)
        logger.info("Database tables ensured")
    except Exception as e:
        logger.warning("Database setup failed", error=str(e))


async def save_review(
    repo_full_name: str,
    pr_number: int,
    commit_sha: str,
    review: SynthesizedReview,
) -> None:
    """Save a PR review to the database."""
    if not settings.database_url:
        return

    try:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO pr_reviews (id, repo_full_name, pr_number, commit_sha,
                    health_score, critical_count, high_count, medium_count, low_count,
                    summary, findings, duration_ms)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """,
                str(uuid4()),
                repo_full_name,
                pr_number,
                commit_sha,
                review.health_score,
                review.critical_count,
                review.high_count,
                review.medium_count,
                review.low_count,
                review.executive_summary,
                json.dumps([f.model_dump() for f in review.findings]),
                review.duration_ms,
            )
        logger.info("Saved review to database", repo=repo_full_name, pr=pr_number)
    except Exception as e:
        logger.warning("Database save failed", error=str(e))


async def get_repo_reviews(repo_full_name: str, limit: int = 20) -> list[dict]:
    limit = min(limit, 100)  # Cap to prevent excessive queries
    """Get recent reviews for a repo."""
    if not settings.database_url:
        return []

    try:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, pr_number, commit_sha, health_score,
                       critical_count, high_count, medium_count, low_count,
                       summary, duration_ms, created_at
                FROM pr_reviews
                WHERE repo_full_name = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                repo_full_name,
                limit,
            )
        return [dict(row) for row in rows]
    except Exception as e:
        logger.warning("Database query failed", error=str(e))
        return []
