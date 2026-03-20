"""
ChromaDB Repo Indexer
======================

Indexes repository source code into ChromaDB for semantic search.
Each repo gets its own ChromaDB collection, keyed by the repo's full name.

How indexing works:
1. Receive file contents from GitHub API
2. Chunk each file into ~60-line blocks
3. Embed each chunk using sentence-transformers
4. Upsert into ChromaDB collection for this repo

ChromaDB is an open-source vector database that:
- Runs embedded in the Python process (no separate server needed)
- Stores vectors + metadata + documents together
- Supports fast approximate nearest neighbor (ANN) search
- Can persist to disk or run entirely in-memory

We use in-memory mode on Render (ephemeral storage) — the index is rebuilt
on each PR review. This is acceptable because indexing the changed files
takes <1 second for typical PRs.
"""

from __future__ import annotations

import chromadb
import structlog

from app.config import settings
from app.context.embedder import chunk_code, embed_texts

logger = structlog.get_logger()

# Singleton ChromaDB client (in-memory)
_chroma_client: chromadb.ClientAPI | None = None


def _get_chroma_client() -> chromadb.ClientAPI:
    """Get or create the ChromaDB client."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.Client()  # In-memory, no persistence
    return _chroma_client


def _collection_name(repo_full_name: str) -> str:
    """Generate a valid ChromaDB collection name from a repo name."""
    # ChromaDB requires alphanumeric + underscores, 3-63 chars
    name = repo_full_name.replace("/", "_").replace("-", "_")
    return f"repo_{name}"[:63]


async def index_repo_files(
    repo_full_name: str, file_contents: dict[str, str]
) -> str:
    """
    Index repository files into ChromaDB for RAG retrieval.

    This is called during each PR review to ensure the vector store
    has the latest file contents. We upsert (insert or update) so
    re-indexing the same file just overwrites the old vectors.

    Args:
        repo_full_name: "owner/repo" — used as collection name
        file_contents: dict of {filepath: source_code}

    Returns:
        Collection name (for retrieval)
    """
    client = _get_chroma_client()
    collection_name = _collection_name(repo_full_name)

    # Get or create a collection for this repo
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"repo": repo_full_name},
    )

    # Chunk all files
    all_chunks = []
    for filepath, content in file_contents.items():
        # Skip very large files (binary, generated code, etc.)
        if len(content) > 100_000:
            continue
        chunks = chunk_code(content, filepath)
        all_chunks.extend(chunks)

    if not all_chunks:
        logger.info("No chunks to index", repo=repo_full_name)
        return collection_name

    # Limit total chunks (Render memory constraint)
    max_chunks = settings.max_repo_files_index
    if len(all_chunks) > max_chunks:
        all_chunks = all_chunks[:max_chunks]

    # Embed all chunks
    texts = [chunk["text"] for chunk in all_chunks]
    embeddings = embed_texts(texts)

    if not embeddings:
        logger.warning("Embedding failed — RAG context unavailable")
        return collection_name

    # Upsert into ChromaDB
    ids = [f"{chunk['filepath']}:{chunk['start_line']}" for chunk in all_chunks]
    metadatas = [
        {"filepath": chunk["filepath"], "start_line": chunk["start_line"], "end_line": chunk["end_line"]}
        for chunk in all_chunks
    ]

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )

    logger.info(
        "Indexed repo files",
        repo=repo_full_name,
        chunks=len(all_chunks),
        collection=collection_name,
    )

    return collection_name
