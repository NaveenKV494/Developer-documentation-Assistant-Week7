"""Generate 20 complete traces using the existing Week 4 RAG pipeline.

Usage:
    python run_week5_traces.py
    python run_week5_traces.py --strategy baseline --top-k 5
"""
from __future__ import annotations
import argparse
from pathlib import Path
from app.config import GENERATION_MODEL
from app.retrieval.retriever import retrieve_relevant_chunks
from app.llm.generator import generate_answer
from app.llm.prompts import build_rag_prompt
from app.observability.trace import RetrievedChunkTrace, Trace, save_trace

QUESTIONS = [
    "What are the four execution states of a .NET MAUI app?",
    "Which cross-platform lifecycle event is raised when a window is no longer visible?",
    "Where are dependencies registered in a .NET MAUI application?",
    "What is the difference between AddSingleton and AddTransient?",
    "What is the default number of rows and columns in a .NET MAUI Grid?",
    "What are the three GridUnitType values used for row heights and column widths?",
    "What are the main parts of a XAML file described in the getting-started documentation?",
    "How can XAML interact with code in a .NET MAUI application?",
    "Where does a MAUI app register its services?",
    "When does a MAUI window become no longer visible in the lifecycle?",
    "How many rows and columns does Grid have if none are declared?",
    "Which GridUnitType options can be used for sizing?",
    "What is the maximum number of concurrent API requests supported?",
    "What is the monthly price of the .NET MAUI service?",
    "What is the official SLA for .NET MAUI?",
    "What is the maximum memory limit for a .NET MAUI application?",
    "Which database engine is officially recommended for every .NET MAUI application?",
    "What is Microsoft's guaranteed response time for MAUI support?",
    "How many users can a MAUI application support simultaneously?",
    "What is the official production uptime guarantee for .NET MAUI?",
]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", choices=["structure", "baseline"], default="structure")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--sdk-version", default=None)
    p.add_argument("--output", default="traces/raw/traces.jsonl")
    args = p.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("", encoding="utf-8")

    for i, question in enumerate(QUESTIONS, 1):
        trace = Trace.new(question, args.strategy, args.top_k, args.sdk_version)
        try:
            docs = retrieve_relevant_chunks(question, args.top_k, args.strategy, args.sdk_version)
            for rank, doc in enumerate(docs, 1):
                trace.retrieved_chunks.append(RetrievedChunkTrace(
                    rank=rank, score=doc.get("score"), distance=doc.get("distance"),
                    chunk_id=doc.get("chunk_id"), source_file=doc.get("source_file"),
                    page_id=doc.get("page_id"), section=doc.get("section"),
                    sdk_version=doc.get("sdk_version"), page_type=doc.get("page_type"),
                    text=doc.get("text", ""),
                ))
            result = generate_answer(build_rag_prompt(question, docs))
            trace.generation_model = GENERATION_MODEL
            trace.answer = result.answer
            trace.grounded = result.grounded
            trace.citations = [c.model_dump() for c in result.citations]
        except Exception as exc:
            trace.error = f"{type(exc).__name__}: {exc}"
        save_trace(trace, output)
        print(f"[{i:02d}/20] {'ERROR' if trace.error else 'OK'} | {question}")

    print(f"\nSaved 20 traces to {output}")


if __name__ == "__main__":
    main()
