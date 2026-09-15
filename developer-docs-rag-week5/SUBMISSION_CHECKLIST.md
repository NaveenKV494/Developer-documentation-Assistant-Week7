# Submission checklist

- [x] Existing RAG pipeline retained
- [x] Baseline fixed-size chunker
- [x] Structure-aware chunker
- [x] Code fences protected
- [x] Markdown tables protected
- [x] Metadata on every chunk
- [x] Chroma persistent vector store
- [x] Cosine similarity / HNSW configuration
- [x] Top-K retrieval with scores
- [x] `sdk_version` metadata filter
- [x] Pydantic structured generation
- [x] Grounded-answer prompt
- [x] Refusal behavior
- [x] Citation schema and validation
- [x] Eight known-answer evaluation questions
- [x] Search-only dump generation
- [x] Hit@5 comparison generation
- [x] Three grounded + three refusal test generation
- [x] Reproducible PowerShell submission runner

## Before submitting

1. Add the six supplied v3 reference pages required by Set E.
2. If the grader expects v2/v3 comparison, include the v2 corpus with `sdk_version=v2` and the new pages with `sdk_version=v3`.
3. Run `run_submission.ps1`.
4. Open `results.md` and verify the real X/8 and Y/8 values.
5. Open `search_dump.txt` and confirm all eight questions have five-result records.
6. Paste the requested unfiltered/filtered version query lists into `results.md` if your corpus contains both versions.
