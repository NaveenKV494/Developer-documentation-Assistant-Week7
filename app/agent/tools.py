from __future__ import annotations

import json
from typing import Any, Callable

from app.config import CHROMA_COLLECTION_NAME
from app.models.response import Citation
from app.retrieval.retriever import retrieve_relevant_chunks
from app.retrieval.vector_store import get_vector_store


def search_docs(
    query: str,
    document_id: str | None = None,
    top_k: int = 4,
    collection_name: str | None = None,
) -> dict[str, Any]:
    """
    Search developer documentation for relevant information matching the query.
    Returns ranked chunk snippets, citations, and relevance scores.
    """
    if not query or not query.strip():
        return {
            "status": "error",
            "message": "Search query cannot be empty.",
            "results": [],
            "count": 0,
        }

    try:
        chunks = retrieve_relevant_chunks(
            query=query.strip(),
            n_results=top_k,
            document_id=document_id if document_id else None,
            collection_name=collection_name,
        )

        results: list[dict[str, Any]] = []
        for c in chunks:
            results.append({
                "chunk_id": c.get("chunk_id", ""),
                "document_id": c.get("document_id", ""),
                "filename": c.get("filename", ""),
                "page": c.get("page", 1),
                "section": c.get("section", "General"),
                "similarity_score": round(float(c.get("score", 0.0)), 4),
                "content": c.get("text", "").strip(),
            })

        return {
            "status": "success",
            "query": query,
            "count": len(results),
            "results": results,
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Search failed: {exc}",
            "results": [],
            "count": 0,
        }


def inspect_section(
    document_id: str | None = None,
    section: str | None = None,
    chunk_id: str | None = None,
    collection_name: str | None = None,
) -> dict[str, Any]:
    """
    Inspect a specific section, document, or chunk in depth when search results
    require deeper context or surrounding content.
    """
    try:
        collection = get_vector_store(collection_name=collection_name or CHROMA_COLLECTION_NAME)
        
        where_filter: dict[str, Any] = {}
        if chunk_id:
            results = collection.get(ids=[chunk_id], include=["documents", "metadatas"])
        else:
            filter_conditions: list[dict[str, Any]] = []
            if document_id:
                filter_conditions.append({"document_id": document_id})
            if section:
                filter_conditions.append({"section": section})

            if len(filter_conditions) == 1:
                where_filter = filter_conditions[0]
            elif len(filter_conditions) > 1:
                where_filter = {"$and": filter_conditions}

            results = collection.get(
                where=where_filter if where_filter else None,
                limit=10,
                include=["documents", "metadatas"],
            )

        docs = results.get("documents") or []
        metas = results.get("metadatas") or []
        ids = results.get("ids") or []

        items: list[dict[str, Any]] = []
        for cid, doc, meta in zip(ids, docs, metas):
            meta = meta or {}
            items.append({
                "chunk_id": cid,
                "document_id": meta.get("document_id", ""),
                "filename": meta.get("filename", ""),
                "page": meta.get("page", 1),
                "section": meta.get("section", ""),
                "content": doc.strip() if doc else "",
            })

        if not items:
            return {
                "status": "not_found",
                "message": f"No content found matching document_id='{document_id}', section='{section}', chunk_id='{chunk_id}'.",
                "items": [],
            }

        return {
            "status": "success",
            "target": {"document_id": document_id, "section": section, "chunk_id": chunk_id},
            "count": len(items),
            "items": items,
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to inspect section: {exc}",
            "items": [],
        }


AVAILABLE_TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "search_docs": search_docs,
    "inspect_section": inspect_section,
}

TOOL_DESCRIPTIONS = """1. `search_docs(query: str, document_id: str = None, top_k: int = 4)`
   - Description: Search uploaded developer documentation for technical concepts, APIs, configurations, or keywords.
   - Arguments: `query` (required string), `document_id` (optional string to scope search).

2. `inspect_section(document_id: str = None, section: str = None, chunk_id: str = None)`
   - Description: Read all chunks and deeper context from a specific document section or chunk ID when search results are insufficient or mention related sections.
   - Arguments: `section` (optional string name of section), `document_id` (optional string), `chunk_id` (optional string).
"""
