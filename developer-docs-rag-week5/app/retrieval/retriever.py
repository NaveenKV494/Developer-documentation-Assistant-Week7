from __future__ import annotations

from typing import Any

from app.config import CHROMA_COLLECTION_NAME
from app.retrieval.embeddings import CustomGeminiEmbeddingFunction
from app.retrieval.vector_store import get_vector_store

__all__ = [
    "CustomGeminiEmbeddingFunction",
    "get_vector_store",
    "retrieve_relevant_chunks",
]



def _distance_to_similarity(distance: float) -> float:
    # With cosine distance, 0 is identical and 2 is maximally opposite.
    # Convert it to a convenient [-1, 1] cosine-similarity-like score.
    return 1.0 - float(distance)


def retrieve_relevant_chunks(
    query: str,
    n_results: int = 5,
    strategy: str = "structure",
    sdk_version: str | None = None,
    document_id: str | None = None,
    document_ids: list[str] | None = None,
    collection_name: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve ranked chunks with optional document isolation (document_id / document_ids)
    or legacy sdk_version filtering.
    """
    if not query.strip():
        return []

    target_collection_name = collection_name or CHROMA_COLLECTION_NAME
    collection = get_vector_store(collection_name=target_collection_name)

    # If target collection is empty and strategy was specified, fallback to sdk_docs_{strategy}
    try:
        if collection.count() == 0 and strategy:
            fallback_name = f"sdk_docs_{strategy}"
            fallback_col = get_vector_store(collection_name=fallback_name)
            if fallback_col.count() > 0:
                collection = fallback_col
    except Exception:
        pass

    # Construct Chroma 'where' filter
    filter_conditions: list[dict[str, Any]] = []

    if document_id:
        filter_conditions.append({"document_id": document_id})
    elif document_ids:
        if len(document_ids) == 1:
            filter_conditions.append({"document_id": document_ids[0]})
        elif len(document_ids) > 1:
            filter_conditions.append({"document_id": {"$in": document_ids}})

    if sdk_version:
        filter_conditions.append({"sdk_version": sdk_version})

    where: dict[str, Any] | None = None
    if len(filter_conditions) == 1:
        where = filter_conditions[0]
    elif len(filter_conditions) > 1:
        where = {"$and": filter_conditions}

    kwargs: dict[str, Any] = {
        "query_texts": [query],
        "n_results": max(1, n_results),
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    results = collection.query(**kwargs)
    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]

    retrieved: list[dict[str, Any]] = []
    for text, metadata, distance in zip(documents, metadatas, distances):
        metadata = metadata or {}
        filename = metadata.get("filename") or metadata.get("source_file") or "document"
        page_val = metadata.get("page") or metadata.get("page_id") or 1
        try:
            page_int = int(page_val)
        except (ValueError, TypeError):
            page_int = 1

        retrieved.append(
            {
                "text": text,
                "score": _distance_to_similarity(float(distance)),
                "distance": float(distance),
                "document_id": metadata.get("document_id", ""),
                "filename": filename,
                "source_file": filename,
                "page": page_int,
                "page_id": str(page_val),
                "section": metadata.get("section", ""),
                "sdk_version": metadata.get("sdk_version", ""),
                "page_type": metadata.get("page_type", ""),
                "chunk_id": metadata.get("chunk_id", ""),
                "chunk_strategy": metadata.get("chunk_strategy", strategy),
            }
        )
    return retrieved

