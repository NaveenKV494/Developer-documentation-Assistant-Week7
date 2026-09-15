from __future__ import annotations

import argparse

from app.config import CHUNK_OVERLAP, CHUNK_SIZE, PAGE_TYPE, SDK_VERSION
from app.ingestion.chunker import chunk_documents
from app.ingestion.loader import load_documents
from app.retrieval.retriever import get_vector_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the developer-docs Chroma index.")
    parser.add_argument("--strategy", choices=["baseline", "structure"], default="structure")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=CHUNK_OVERLAP)
    parser.add_argument("--sdk-version", default=SDK_VERSION)
    parser.add_argument("--page-type", default=PAGE_TYPE)
    parser.add_argument("--documents", default=None, help="Optional Markdown folder to ingest.")
    args = parser.parse_args()

    if args.documents:
        docs = load_documents(
            folder_path=args.documents,
            sdk_version=args.sdk_version,
            page_type=args.page_type,
        )
    else:
        docs = load_documents(sdk_version=args.sdk_version, page_type=args.page_type)

    chunks = chunk_documents(
        docs,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        strategy=args.strategy,
    )

    collection = get_vector_store(strategy=args.strategy, reset=args.reset)
    collection.upsert(
        documents=[c["text"] for c in chunks],
        metadatas=[
            {
                "source_file": c["source_file"],
                "page_id": c["page_id"],
                "sdk_version": c["sdk_version"],
                "page_type": c["page_type"],
                "chunk_id": c["chunk_id"],
                "chunk_strategy": c["chunk_strategy"],
                "section": c["section"],
                "block_kinds": ",".join(c["block_kinds"]),
            }
            for c in chunks
        ],
        ids=[c["chunk_id"] for c in chunks],
    )
    print(f"Indexed {len(chunks)} chunks into {collection.name} (sdk_version={args.sdk_version}).")


if __name__ == "__main__":
    main()
