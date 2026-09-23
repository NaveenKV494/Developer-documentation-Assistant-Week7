from __future__ import annotations

import os
from typing import Any

import chromadb

from app.config import (
    CHROMA_API_KEY,
    CHROMA_COLLECTION_NAME,
    CHROMA_DATABASE,
    CHROMA_DIR,
    CHROMA_MODE,
    CHROMA_SERVER_HOST,
    CHROMA_SERVER_PORT,
    CHROMA_TENANT,
)
from app.retrieval.embeddings import CustomGeminiEmbeddingFunction


def get_client_mode() -> str:
    """Return the active Chroma client mode ('cloud', 'http', or 'local')."""
    mode = (CHROMA_MODE or "auto").lower()
    if mode == "cloud" or (mode == "auto" and CHROMA_API_KEY):
        return "cloud"
    if mode == "http" or (mode == "auto" and CHROMA_SERVER_HOST):
        return "http"
    return "local"


def get_chroma_client() -> chromadb.api.ClientAPI:
    """Instantiate Chroma client based on configured mode (Cloud, HTTP, or Persistent Local)."""
    mode = get_client_mode()

    if mode == "cloud":
        kwargs: dict[str, Any] = {"api_key": CHROMA_API_KEY}
        if CHROMA_TENANT:
            kwargs["tenant"] = CHROMA_TENANT
        if CHROMA_DATABASE:
            kwargs["database"] = CHROMA_DATABASE
        return chromadb.CloudClient(**kwargs)

    if mode == "http":
        return chromadb.HttpClient(
            host=CHROMA_SERVER_HOST,
            port=CHROMA_SERVER_PORT,
        )

    # Default to local persistent storage
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_vector_store(
    collection_name: str | None = None,
    reset: bool = False,
    strategy: str | None = None,
):
    """Return the Chroma collection configured with Gemini embeddings and cosine space."""
    client = get_chroma_client()
    if strategy and not collection_name:
        target_name = f"sdk_docs_{strategy}"
    else:
        target_name = collection_name or CHROMA_COLLECTION_NAME


    if reset:
        try:
            client.delete_collection(name=target_name)
        except Exception:
            pass

    return client.get_or_create_collection(
        name=target_name,
        embedding_function=CustomGeminiEmbeddingFunction(),
        metadata={"hnsw:space": "cosine"},
    )


def upsert_chunks(
    chunks: list[dict[str, Any]],
    collection_name: str | None = None,
) -> int:
    """Upsert chunk dictionaries into the specified collection."""
    if not chunks:
        return 0

    collection = get_vector_store(collection_name=collection_name)

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for c in chunks:
        ids.append(str(c["chunk_id"]))
        documents.append(c["text"])

        # Chroma metadata requires scalar types (str, int, float, bool)
        block_kinds = c.get("block_kinds", [])
        block_kinds_str = ",".join(block_kinds) if isinstance(block_kinds, list) else str(block_kinds)

        meta: dict[str, Any] = {
            "chunk_id": str(c.get("chunk_id", "")),
            "document_id": str(c.get("document_id", "")),
            "filename": str(c.get("filename", c.get("source_file", ""))),
            "source_file": str(c.get("source_file", c.get("filename", ""))),
            "page": int(c.get("page", 1)),
            "page_id": str(c.get("page_id", c.get("page", 1))),
            "section": str(c.get("section", "")),
            "chunk_index": int(c.get("chunk_index", 0)),
            "chunk_strategy": str(c.get("chunk_strategy", "structure")),
            "block_kinds": block_kinds_str,
        }
        if "sdk_version" in c:
            meta["sdk_version"] = str(c["sdk_version"])
        if "page_type" in c:
            meta["page_type"] = str(c["page_type"])

        metadatas.append(meta)

    # Upsert in batches of 100 to prevent oversized requests
    batch_size = 100
    for start in range(0, len(chunks), batch_size):
        end = start + batch_size
        collection.upsert(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )

    return len(chunks)


def delete_document_chunks(
    document_id: str,
    collection_name: str | None = None,
) -> None:
    """Delete all indexed chunks for a given document_id."""
    collection = get_vector_store(collection_name=collection_name)
    try:
        collection.delete(where={"document_id": document_id})
    except Exception:
        # Some Chroma backends support delete by where, fallback to finding IDs
        try:
            results = collection.get(where={"document_id": document_id})
            if results and results.get("ids"):
                collection.delete(ids=results["ids"])
        except Exception:
            pass


def query_chunks(
    query_text: str,
    n_results: int = 5,
    where: dict[str, Any] | None = None,
    collection_name: str | None = None,
) -> dict[str, Any]:
    """Query Chroma collection with cosine similarity."""
    collection = get_vector_store(collection_name=collection_name)

    kwargs: dict[str, Any] = {
        "query_texts": [query_text],
        "n_results": max(1, n_results),
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    return collection.query(**kwargs)
