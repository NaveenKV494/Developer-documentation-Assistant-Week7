from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import BinaryIO
import uuid

from app.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHUNK_STRATEGY,
    DOCUMENTS_DIR,
    REGISTRY_FILE,
    ROOT_DIR,
    STORAGE_DOCUMENTS_DIR,
)
from app.ingestion.chunker import chunk_parsed_document
from app.ingestion.parser import _read_bytes, parse_document
from app.models.response import DocumentMetadata
from app.retrieval.vector_store import delete_document_chunks, upsert_chunks


def _load_registry() -> dict[str, dict]:
    """Load registry mapping document_id to document metadata dict."""
    if not REGISTRY_FILE.exists():
        return {}
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_registry(registry: dict[str, dict]) -> None:
    """Save registry to JSON manifest."""
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


def list_documents() -> list[DocumentMetadata]:
    """Return all indexed documents sorted by upload time."""
    registry = _load_registry()
    docs = [DocumentMetadata.model_validate(v) for v in registry.values()]
    docs.sort(key=lambda d: d.uploaded_at, reverse=True)
    return docs


def get_document_metadata(document_id: str) -> DocumentMetadata | None:
    """Get metadata for a single document."""
    registry = _load_registry()
    data = registry.get(document_id)
    return DocumentMetadata.model_validate(data) if data else None


def upload_and_index_document(
    file_source: str | Path | BinaryIO | bytes,
    filename: str | None = None,
    strategy: str = CHUNK_STRATEGY,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    collection_name: str | None = None,
) -> DocumentMetadata:
    """Complete pipeline: save raw file to storage, parse, chunk, and index into vector store."""
    data, detected_name = _read_bytes(file_source)
    resolved_filename = filename or detected_name or "document.txt"
    resolved_filename = Path(resolved_filename).name  # Sanitize filename

    if not data:
        raise ValueError("Cannot index empty file.")

    # Generate document ID and isolate raw document storage
    document_id = uuid.uuid4().hex[:12]
    doc_dir = STORAGE_DOCUMENTS_DIR / document_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    saved_path = doc_dir / resolved_filename
    saved_path.write_bytes(data)

    # Parse document
    blocks = parse_document(data, resolved_filename)

    # Chunk parsed document
    chunks = chunk_parsed_document(
        blocks=blocks,
        document_id=document_id,
        filename=resolved_filename,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        strategy=strategy,
    )

    if not chunks:
        # Clean up saved file if chunking produced no text
        shutil.rmtree(doc_dir, ignore_errors=True)
        raise ValueError(f"No indexable chunks produced from {resolved_filename}")

    # Upsert chunks into vector store
    upsert_chunks(chunks, collection_name=collection_name)

    # Relative path for portable storage reference
    try:
        rel_storage_path = str(saved_path.relative_to(ROOT_DIR))
    except ValueError:
        rel_storage_path = str(saved_path)

    metadata = DocumentMetadata(
        document_id=document_id,
        filename=resolved_filename,
        file_type=Path(resolved_filename).suffix.lstrip(".").lower() or "txt",
        file_size=len(data),
        uploaded_at=datetime.now(timezone.utc).isoformat(),
        chunk_count=len(chunks),
        storage_path=rel_storage_path,
    )

    registry = _load_registry()
    registry[document_id] = metadata.model_dump()
    _save_registry(registry)

    return metadata


def delete_document(
    document_id: str,
    collection_name: str | None = None,
) -> bool:
    """Delete document chunks from vector store and remove files from storage."""
    registry = _load_registry()
    if document_id not in registry:
        return False

    # Delete from vector store
    delete_document_chunks(document_id, collection_name=collection_name)

    # Delete stored file folder
    doc_dir = STORAGE_DOCUMENTS_DIR / document_id
    if doc_dir.exists():
        shutil.rmtree(doc_dir, ignore_errors=True)

    # Delete from registry
    del registry[document_id]
    _save_registry(registry)
    return True


def format_bytes(size_bytes: int) -> str:
    """Format bytes to human readable string (KB, MB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def get_document_chunks(
    document_id: str,
    collection_name: str | None = None,
) -> list[dict]:
    """Retrieve all indexed chunks for a document to inspect chunking quality."""
    from app.retrieval.vector_store import get_vector_store

    collection = get_vector_store(collection_name=collection_name)
    try:
        results = collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"],
        )
    except Exception:
        return []

    docs = results.get("documents") or []
    metas = results.get("metadatas") or []
    ids = results.get("ids") or []

    chunks = []
    for doc_id, text, meta in zip(ids, docs, metas):
        meta = meta or {}
        chunks.append({
            "chunk_id": doc_id,
            "text": text,
            "page": meta.get("page", 1),
            "section": meta.get("section", ""),
            "chunk_index": meta.get("chunk_index", 0),
            "block_kinds": meta.get("block_kinds", ""),
        })

    chunks.sort(key=lambda c: c.get("chunk_index", 0))
    return chunks


def clear_all_documents(collection_name: str | None = None) -> int:
    """Delete all indexed documents, chunk vectors, and registry entries."""
    registry = _load_registry()
    count = len(registry)
    for doc_id in list(registry.keys()):
        delete_document(doc_id, collection_name=collection_name)

    if STORAGE_DOCUMENTS_DIR.exists():
        shutil.rmtree(STORAGE_DOCUMENTS_DIR, ignore_errors=True)
        STORAGE_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

    _save_registry({})
    return count


def seed_existing_markdown_docs(collection_name: str | None = None) -> list[DocumentMetadata]:
    """Ingest existing markdown documentation files into the new multi-document storage."""
    if not DOCUMENTS_DIR.exists():
        return []

    indexed: list[DocumentMetadata] = []
    current_registry = _load_registry()
    existing_filenames = {doc["filename"] for doc in current_registry.values()}

    for md_file in sorted(DOCUMENTS_DIR.glob("*.md")):
        if md_file.name in existing_filenames:
            continue
        try:
            meta = upload_and_index_document(
                file_source=md_file,
                filename=md_file.name,
                collection_name=collection_name,
            )
            indexed.append(meta)
        except Exception as exc:
            print(f"Failed to seed {md_file.name}: {exc}")

    return indexed

