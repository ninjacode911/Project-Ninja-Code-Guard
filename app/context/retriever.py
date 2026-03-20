"""
RAG Context Retriever
======================

Retrieves relevant code context from ChromaDB based on the PR diff.
This is the "R" in RAG (Retrieval-Augmented Generation).

How retrieval works:
1. Take the PR diff text as a query
2. Embed the query using the same model used for indexing
3. Search ChromaDB for the most similar code chunks
4. Return the top-k chunks as additional context for the LLM

Why RAG for code review?
The PR diff only shows CHANGED lines. But understanding a change often
requires seeing RELATED code:
- If a function is called from 5 places, changing it affects all callers
- If a variable is validated in another file, the validation matters here
- If the same pattern exists elsewhere, inconsistency is a style issue

RAG gives the agents "peripheral vision" — they see not just the change,
but the surrounding codebase context that makes the change meaningful.
"""

from __future__ import annotations

import structlog

from app.context.embedder import embed_texts
from app.context.indexer import _get_chroma_client

logger = structlog.get_logger()


async def retrieve_context(
    collection_name: str,
    query_text: str,
    top_k: int = 5,
) -> str:
    """
    Retrieve relevant code context from ChromaDB.

    Args:
        collection_name: The ChromaDB collection to search
        query_text: The PR diff or a specific query
        top_k: Number of results to return (default: 5)

    Returns:
        A formatted string of relevant code chunks to include in the LLM prompt.
        Returns empty string if retrieval fails or no results found.
    """
    try:
        client = _get_chroma_client()

        # Check if collection exists
        try:
            collection = client.get_collection(name=collection_name)
        except Exception:
            logger.debug("Collection not found — no RAG context", collection=collection_name)
            return ""

        # Skip if collection is empty
        if collection.count() == 0:
            return ""

        # Embed the query
        query_embeddings = embed_texts([query_text[:5000]])  # Cap query size
        if not query_embeddings:
            return ""

        # Search for similar code chunks
        results = collection.query(
            query_embeddings=query_embeddings,
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        if not results or not results["documents"] or not results["documents"][0]:
            return ""

        # Format results as context for the LLM
        context_parts = ["## Related Code Context (from repository)\n"]

        for doc, metadata, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
            strict=False,
        ):
            filepath = metadata.get("filepath", "unknown")
            start = metadata.get("start_line", "?")
            end = metadata.get("end_line", "?")
            # ChromaDB returns L2 distance — lower = more similar
            similarity = max(0, 1 - distance / 2)  # Rough conversion to 0-1

            if similarity < 0.3:
                continue  # Skip low-relevance results

            context_parts.append(
                f"### {filepath} (lines {start}-{end}, relevance: {similarity:.0%})\n"
                f"```\n{doc}\n```\n"
            )

        if len(context_parts) == 1:  # Only the header, no results
            return ""

        context = "\n".join(context_parts)
        logger.info(
            "Retrieved RAG context",
            collection=collection_name,
            chunks_returned=len(context_parts) - 1,
        )
        return context

    except Exception as e:
        logger.warning("RAG retrieval failed", error=str(e))
        return ""
