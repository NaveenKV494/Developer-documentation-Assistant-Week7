from app.llm.generator import generate_answer
from app.llm.prompts import build_rag_prompt
from app.retrieval.retriever import retrieve_relevant_chunks


query = "How do I configure retries and backoff?"
print(f"User Query: {query}\n")

docs = retrieve_relevant_chunks(query, n_results=5)
print("=== RETRIEVED SOURCES ===")
for i, doc in enumerate(docs, 1):
    print(
        f"{i}. {doc.get('source_file')} | {doc.get('section')} | "
        f"score={doc.get('score'):.4f} | chunk={doc.get('chunk_id')}"
    )

prompt = build_rag_prompt(query, docs)
result = generate_answer(prompt)

print("\n=== FINAL ANSWER ===")
print(result.answer)
print(f"\nGrounded: {result.grounded}")
for citation in result.citations:
    print(
        f"Source: {citation.source_file} | {citation.section} | "
        f"chunk={citation.chunk_id}"
    )
