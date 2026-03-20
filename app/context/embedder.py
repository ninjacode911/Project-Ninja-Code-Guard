"""
Code Embedding Pipeline
========================

Converts source code into vector embeddings using sentence-transformers.
These embeddings are stored in ChromaDB for semantic search.

How it works:
1. Source code is split into chunks (functions, classes, or fixed-size blocks)
2. Each chunk is embedded into a 384-dimensional vector
3. Vectors capture semantic meaning — similar code has similar vectors
4. When reviewing a PR, we query ChromaDB with the diff to find related code

Why embeddings for code?
Consider this diff:
    + user_id = request.args.get("id")
    + data = db.query(f"SELECT * FROM users WHERE id = {user_id}")

To evaluate this, the agent needs to know:
- Does `db.query()` parameterize inputs? → Need the DB wrapper's source code
- Is there middleware that validates `user_id`? → Need the middleware source
- Are there other similar patterns in the codebase? → Need semantic search

Embeddings let us find this related code WITHOUT knowing the exact file paths.
The query "SQL query with user input" returns relevant code chunks ranked by
semantic similarity — not keyword matching, but meaning matching.

Model: all-MiniLM-L6-v2
- 384 dimensions, 22M parameters
- Runs locally on CPU in ~10ms per chunk (GPU: ~1ms)
- Optimized for semantic similarity tasks
- Good enough for code — not perfect, but fast and free
"""

from __future__ import annotations

import structlog

from app.config import settings

logger = structlog.get_logger()

# Lazy-loaded model to avoid slow import at startup
_model = None


def get_embedding_model():
    """
    Lazy-load the sentence-transformers model.

    We load on first use (not at import time) because:
    1. The model takes ~2 seconds to load
    2. Not every request needs embeddings (cached reviews skip this)
    3. Tests shouldn't load a real ML model
    """
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(settings.embedding_model)
            logger.info("Loaded embedding model", model=settings.embedding_model)
        except ImportError:
            logger.warning("sentence-transformers not installed — RAG context disabled")
            return None
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of text strings into vectors.

    Args:
        texts: List of code chunks or queries to embed

    Returns:
        List of embedding vectors (each is a list of floats)
    """
    model = get_embedding_model()
    if model is None:
        return []

    embeddings = model.encode(texts, show_progress_bar=False)
    return embeddings.tolist()


def chunk_code(content: str, filepath: str, chunk_size: int = 60) -> list[dict]:
    """
    Split source code into overlapping chunks for embedding.

    Strategy: We chunk by lines with overlap. Each chunk is ~60 lines
    with 10 lines of overlap to preserve context across boundaries.

    Why 60 lines? It's roughly one function/class — the natural unit of
    code that a developer would reason about. Too small (10 lines) loses
    context. Too large (200 lines) dilutes the embedding signal.

    Args:
        content: Full file source code
        filepath: The file path (included as metadata)
        chunk_size: Lines per chunk (default: 60)

    Returns:
        List of dicts with 'text', 'filepath', 'start_line', 'end_line'
    """
    lines = content.split("\n")
    chunks = []
    overlap = 10
    start = 0

    while start < len(lines):
        end = min(start + chunk_size, len(lines))
        chunk_text = "\n".join(lines[start:end])

        # Skip very small chunks (less than 5 non-empty lines)
        non_empty = sum(1 for line in lines[start:end] if line.strip())
        if non_empty >= 5:
            chunks.append({
                "text": f"# File: {filepath}\n{chunk_text}",
                "filepath": filepath,
                "start_line": start + 1,
                "end_line": end,
            })

        start += max(chunk_size - overlap, 1)  # Overlap for context continuity

    return chunks
