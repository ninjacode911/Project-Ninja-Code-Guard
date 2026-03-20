"""
Tests for Redis cache logic.

These tests verify that:
1. A new commit SHA is correctly identified as not-yet-reviewed
2. After marking as reviewed, it's identified as already-reviewed
3. Cache invalidation works (for the /reanalyze endpoint)
4. Redis failures are handled gracefully (fail open, not closed)

We use unittest.mock to avoid needing a real Redis connection in tests.
The mock simulates Redis responses so tests run fast and offline.

Design decision: "fail open" means if Redis is down, we proceed with analysis.
This is intentional — it's better to accidentally review a PR twice than to
miss a review because the cache is unavailable. This is the same pattern
used by rate limiters in production systems (fail open = allow the request).
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.db.redis_cache import invalidate_cache, is_already_reviewed, mark_as_reviewed


@pytest.fixture
def mock_redis():
    """
    Create a mock Redis client.

    AsyncMock is Python's built-in mock for async functions.
    It automatically returns a coroutine, so `await mock_redis.exists()`
    works without a real Redis connection.
    """
    mock = AsyncMock()
    with patch("app.db.redis_cache._get_redis_client", return_value=mock):
        yield mock


class TestIsAlreadyReviewed:
    @pytest.mark.asyncio
    async def test_returns_false_for_new_commit(self, mock_redis):
        """A commit SHA that's not in Redis should return False."""
        mock_redis.exists.return_value = 0  # Redis returns 0 for non-existent keys
        result = await is_already_reviewed("abc123def456")
        assert result is False
        mock_redis.exists.assert_called_once_with("ninjacg:reviewed:abc123def456")

    @pytest.mark.asyncio
    async def test_returns_true_for_cached_commit(self, mock_redis):
        """A commit SHA that IS in Redis should return True."""
        mock_redis.exists.return_value = 1
        result = await is_already_reviewed("abc123def456")
        assert result is True

    @pytest.mark.asyncio
    async def test_redis_failure_returns_false(self, mock_redis):
        """If Redis is down, we should return False (fail open)."""
        mock_redis.exists.side_effect = ConnectionError("Redis unavailable")
        result = await is_already_reviewed("abc123def456")
        assert result is False  # Fail open — proceed with analysis


class TestMarkAsReviewed:
    @pytest.mark.asyncio
    async def test_sets_key_with_ttl(self, mock_redis):
        """Marking as reviewed should SET the key with a 7-day TTL."""
        await mark_as_reviewed("abc123def456")
        mock_redis.set.assert_called_once_with(
            "ninjacg:reviewed:abc123def456",
            "1",
            ex=7 * 24 * 60 * 60,  # 7 days in seconds
        )

    @pytest.mark.asyncio
    async def test_redis_failure_does_not_raise(self, mock_redis):
        """If Redis SET fails, we log and continue — don't crash the review."""
        mock_redis.set.side_effect = ConnectionError("Redis unavailable")
        # Should not raise — just logs a warning
        await mark_as_reviewed("abc123def456")


class TestInvalidateCache:
    @pytest.mark.asyncio
    async def test_deletes_key(self, mock_redis):
        """Cache invalidation should DELETE the key."""
        await invalidate_cache("abc123def456")
        mock_redis.delete.assert_called_once_with("ninjacg:reviewed:abc123def456")

    @pytest.mark.asyncio
    async def test_redis_failure_does_not_raise(self, mock_redis):
        """If Redis DELETE fails, we log and continue."""
        mock_redis.delete.side_effect = ConnectionError("Redis unavailable")
        await invalidate_cache("abc123def456")
