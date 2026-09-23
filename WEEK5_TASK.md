# Week 5 — Evals & Error Analysis

This project is a separate Week 5 copy of the Week 4 Developer Documentation RAG app.

## Required workflow

1. Generate ~20 complete traces with `python run_week5_traces.py`.
2. Inspect `traces/raw/traces.jsonl`.
3. Run `python analyze_traces.py` to create the review sheet.
4. Read every trace and write an honest open-coded observation before assigning a category.
5. Group observations into named problem categories in `error_taxonomy.md`.
6. Rank recurring problems by **frequency × severity**.
7. Pick one problem to fix.
8. Write a prediction before making the change.
9. Make exactly one targeted improvement.
10. Re-run the same evaluation sample and measure before/after.
11. Document the result in `results.md`.

## Retrieval vs generation

- **Retrieval failure:** the evidence needed to answer was not retrieved.
- **Generation failure:** the evidence was retrieved, but the model answered incorrectly or unsupported.

Do not call something a generation failure until the retrieved context has been inspected.

## Complete trace fields

Each trace records question, retrieval strategy, Top-K, ranked chunks, scores, chunk IDs, source, section, retrieved text, generation model, answer, grounded flag, citations, timestamp, and errors.





## Week 5 — Evals & Error Analysis

### Trace Sample

Collected and reviewed 20 real RAG traces from the application.

The sample included:
- 12 answerable developer-documentation questions
- 8 unsupported questions designed to test refusal behavior

Each trace was reviewed individually before grouping failures.

### Open Coding Summary

| Outcome | Count |
|---|---:|
| Acceptable answer | 10 |
| False refusal despite sufficient evidence | 2 |
| Correct unsupported-question refusal | 1 |
| Generation infrastructure / quota failure | 7 |
| **Total** | **20** |

### Ranked Error Taxonomy

#### 1. False refusal despite sufficient retrieved evidence
- Frequency: 2
- Severity: 4/5
- Priority score: 8
- Status: **Fix next**

The retriever returned relevant evidence, but the generator refused to answer.

Affected traces:
- Trace 10
- Trace 11

#### 2. Generation infrastructure / quota failure
- Frequency: 7
- Severity: 3/5
- Priority score: 21
- Status: Monitor / operational fix

These failures occurred because the Gemini generation API reached the
free-tier daily request quota. They occurred before a RAG answer could
be generated and therefore are treated separately from application-level
RAG quality errors.

Affected traces:
- Trace 14–20

#### 3. Correct unsupported-question refusal
- Frequency: 1
- Severity: 2/5
- Priority score: 2
- Status: Preserve

Trace 13 correctly refused an unsupported question.

### Selected Fix Target

**False refusal despite sufficient retrieved evidence.**

Although infrastructure/quota failures had a higher raw frequency × severity
score, they are not the selected RAG-quality intervention because they occur
at the generation infrastructure layer.

The application-level problem with the clearest evidence is false refusal:
the required information was already present in the retrieved context, but
the generator failed to use it.

### Prediction

The likely cause is an overly conservative grounding instruction that treats
paraphrased user questions as unsupported even when the underlying fact is
present in the retrieved documentation.

### Intervention

The system prompt was updated to:

1. Recognize paraphrases, synonyms, and equivalent wording.
2. Check all supplied context before refusing.
3. Answer when sufficient evidence exists.
4. Continue refusing when the required evidence is absent.
5. Require valid citations for factual answers.

### Validation Plan

After the Gemini generation quota becomes available, re-run only the targeted
validation cases:

- Trace 10 — should answer with grounded=true and valid citation.
- Trace 11 — should answer with grounded=true and valid citation.
- Trace 13 — should continue returning the exact refusal with grounded=false.

The goal is to improve supported-question answering without weakening
unsupported-question refusal behavior.