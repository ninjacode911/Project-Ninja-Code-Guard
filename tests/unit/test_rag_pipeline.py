"""
Tests for the RAG (Retrieval-Augmented Generation) pipeline.

These tests verify:
1. Code chunking splits files correctly with overlap
2. ChromaDB indexing stores documents (with mocked embeddings)
3. Retrieval returns context for queries (with mocked embeddings)
4. Edge cases: empty files, very large files, non-existent collections

IMPORTANT: All tests mock embed_texts() to avoid loading the
sentence-transformers model, which takes ~60 seconds on first load.
"""

from unittest.mock import patch

import pytest

from app.context.embedder import chunk_code
from app.context.indexer import _collection_name, index_repo_files
from app.context.retriever import retrieve_context

# ─── Code Chunking Tests ─────────────────────────────────────────────────


class TestCodeChunking:
    def test_small_file_single_chunk(self):
        """A file smaller than chunk_size should produce one chunk."""
        code = "\n".join(f"line_{i} = {i}" for i in range(20))
        chunks = chunk_code(code, "small.py", chunk_size=60)
        assert len(chunks) == 1
        assert chunks[0]["filepath"] == "small.py"
        assert chunks[0]["start_line"] == 1
        assert "# File: small.py" in chunks[0]["text"]

    def test_large_file_multiple_chunks(self):
        """A file larger than chunk_size should produce multiple overlapping chunks."""
        code = "\n".join(f"line_{i} = {i}" for i in range(150))
        chunks = chunk_code(code, "large.py", chunk_size=60)
        assert len(chunks) >= 2

        if len(chunks) >= 2:
            first_end = chunks[0]["end_line"]
            second_start = chunks[1]["start_line"]
            assert second_start < first_end  # Overlap exists

    def test_chunk_includes_filepath_in_text(self):
        """Each chunk should include the filepath as a header for context."""
        code = "\n".join(f"line_{i} = {i}" for i in range(10))
        chunks = chunk_code(code, "src/utils/helper.py")
        assert len(chunks) >= 1
        assert "# File: src/utils/helper.py" in chunks[0]["text"]

    def test_skips_nearly_empty_chunks(self):
        """Chunks with fewer than 5 non-empty lines should be skipped."""
        code = "a = 1\n" + "\n" * 8 + "b = 2\n" + "\n" * 8 + "c = 3\n"
        chunks = chunk_code(code, "sparse.py", chunk_size=10)
        assert len(chunks) == 0

    def test_chunk_metadata_has_line_numbers(self):
        """Each chunk should have correct start_line and end_line."""
        code = "\n".join(f"x_{i} = {i}" for i in range(100))
        chunks = chunk_code(code, "numbered.py", chunk_size=30)
        assert chunks[0]["start_line"] == 1
        assert chunks[0]["end_line"] == 30
        if len(chunks) >= 2:
            assert chunks[1]["start_line"] == 21


# ─── Collection Naming Tests ─────────────────────────────────────────────


class TestCollectionNaming:
    def test_converts_repo_name_to_valid_collection(self):
        """Repo names with / and - should become valid ChromaDB collection names."""
        name = _collection_name("ninjacode911/code-guard-test")
        assert "/" not in name
        assert "-" not in name
        assert name.startswith("repo_")

    def test_truncates_long_names(self):
        """Collection names must be max 63 characters (ChromaDB limit)."""
        long_name = "organization/" + "a" * 100
        name = _collection_name(long_name)
        assert len(name) <= 63


# ─── ChromaDB Indexer Tests ──────────────────────────────────────────────


class TestIndexer:
    @pytest.mark.asyncio
    async def test_index_repo_files_returns_collection_name(self):
        """Indexing should return a valid collection name."""
        files = {
            "app.py": "\n".join(f"x_{i} = {i}" for i in range(25)),
        }
        with patch("app.context.indexer.embed_texts", return_value=[[0.1] * 384]):
            name = await index_repo_files("ninjacode911/test-repo", files)
        assert name.startswith("repo_")

    @pytest.mark.asyncio
    async def test_index_handles_empty_files(self):
        """Empty file dict should not crash."""
        name = await index_repo_files("ninjacode911/empty-repo", {})
        assert name.startswith("repo_")

    @pytest.mark.asyncio
    async def test_index_skips_large_files(self):
        """Files over 100KB should be skipped to avoid memory issues."""
        files = {
            "huge.py": "x = 1\n" * 50000,
            "small.py": "\n".join(f"y_{i} = {i}" for i in range(25)),
        }
        with patch("app.context.indexer.embed_texts", return_value=[[0.1] * 384]) as mock_embed:
            await index_repo_files("ninjacode911/skip-test", files)
            if mock_embed.called:
                texts = mock_embed.call_args[0][0]
                for text in texts:
                    assert "huge.py" not in text


# ─── ChromaDB Retriever Tests ────────────────────────────────────────────


class TestRetriever:
    @pytest.mark.asyncio
    async def test_retrieve_nonexistent_collection_returns_empty(self):
        """Querying a non-existent collection should return empty string."""
        with patch("app.context.retriever.embed_texts", return_value=[[0.1] * 384]):
            result = await retrieve_context("nonexistent_xyz_collection", "query")
        assert result == ""

    @pytest.mark.asyncio
    async def test_retrieve_returns_string(self):
        """Successful indexing + retrieval should return a string."""
        files = {
            "app.py": "\n".join(f"code_line_{i} = {i}" for i in range(25)),
        }
        with patch("app.context.indexer.embed_texts", return_value=[[0.1] * 384]):
            collection_name = await index_repo_files("ninjacode911/ret-test", files)

        with patch("app.context.retriever.embed_texts", return_value=[[0.1] * 384]):
            result = await retrieve_context(collection_name, "SQL query")

        assert isinstance(result, str)
