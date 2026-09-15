# Developer Documentation RAG Assistant

A submission-oriented RAG application for answering questions from Markdown developer documentation.

## Architecture

```text
Markdown
  -> ingestion + metadata
  -> baseline OR structure-aware chunking
  -> Gemini Embedding 2
  -> ChromaDB (cosine / HNSW)
  -> metadata filtering + Top-K similarity search
  -> grounded Gemini generation
  -> Pydantic structured output
  -> traceable citations / refusal
```

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Set `GEMINI_API_KEY` in `.env`. Never commit `.env`.

## Build

```powershell
python build_db.py --strategy baseline --reset
python build_db.py --strategy structure --reset
```

The two strategies use separate Chroma collections. Chroma is configured with cosine distance; HNSW is the approximate-nearest-neighbor index used by Chroma.

## Run the chatbot

```powershell
streamlit run ui/streamlit_app.py
```

The UI exposes chunking strategy, Top-K, and optional `sdk_version` metadata filtering. It displays retrieved chunks, scores, and citations.

## Run the Week 3 evaluation

```powershell
python evaluate_rag.py --generation
```

This creates:

- `results.md` — Hit@5 table, per-question records, grounded answers, refusals, and chunking decision.
- `search_dump.txt` — Top-5 retrieval results for all eight known-answer questions under both strategies.

The evaluator writes the actual numbers returned by the installed embedding/retrieval pipeline; it does not fabricate scores.

## Assignment-specific v2/v3 test

The code supports `sdk_version` metadata and filtering. The current archive contains one local documentation version, so it intentionally does not invent a v2/v3 experiment. Put the six supplied v3 reference pages (and the existing v2 pages if required by the assignment) into the corpus with correct metadata, then rebuild and rerun `evaluate_rag.py`.

For a separate folder:

```powershell
python build_db.py --strategy structure --sdk-version v3 --page-type reference --documents path\to\v3-pages
```

## Chunking

Baseline: fixed 1200-character chunks with 200-character overlap.

Structure-aware: splits on Markdown structure, preserves section metadata, and never cuts fenced code blocks or Markdown tables.

## Security / grounding

The generation prompt refuses unsupported questions. The application requires structured Pydantic output and checks that returned citations point to retrieved context.

## Week 5 — Trace & Error Analysis

This is a separate Week 5 copy. It preserves the Week 4 retrieval/generation pipeline and adds trace instrumentation plus an error-analysis workflow.

Run the app normally with:

```powershell
python -m streamlit run ui\streamlit_app.py
```

Every chat request now writes a complete trace to `traces/raw/traces.jsonl`.

For a reproducible 20-question sample:

```powershell
python run_week5_traces.py
python analyze_traces.py
```

Then complete `traces/analysis/open_coding.md` and `error_taxonomy.md` manually before selecting one fix.
