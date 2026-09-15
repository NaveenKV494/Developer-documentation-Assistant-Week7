from app.ingestion.chunker import chunk_documents
from app.ingestion.loader import load_documents


def inspect(strategy: str) -> None:
    docs = load_documents()
    chunks = chunk_documents(docs, chunk_size=1200, chunk_overlap=200, strategy=strategy)
    odd_fences = [c for c in chunks if c["text"].count("```") % 2]
    missing_source = [c for c in chunks if not c.get("source_file")]

    print(f"\n=== {strategy.upper()} ===")
    print(f"Documents : {len(docs)}")
    print(f"Chunks    : {len(chunks)}")
    print(f"Odd fences: {len(odd_fences)}")
    print(f"No source : {len(missing_source)}")

    for chunk in chunks[:5]:
        print("\n---")
        print(f"chunk_id : {chunk['chunk_id']}")
        print(f"source   : {chunk['source_file']}")
        print(f"section  : {chunk['section']}")
        print(f"kinds    : {chunk['block_kinds']}")
        print(f"length   : {len(chunk['text'])}")
        print(chunk["text"][:500].replace("\n", " "))


if __name__ == "__main__":
    inspect("baseline")
    inspect("structure")
