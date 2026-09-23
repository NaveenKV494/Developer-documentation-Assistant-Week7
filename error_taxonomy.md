# Week 5 — Error Taxonomy

## Purpose

This taxonomy groups the observations from the 20 sampled traces into named
problem categories after completing trace-level open coding.

The categories distinguish application-quality problems from retrieval problems,
infrastructure failures, and correct refusal behavior.

---

## Ranked Problem Groups

| Rank | Problem group | Frequency | Severity (1–5) | Frequency × Severity | Priority |
|---|---|---:|---:|---:|---|
| 1 | Generation infrastructure / quota failure | 7 | 3 | 21 | Monitor / operational fix |
| 2 | False refusal despite sufficient retrieved evidence | 1 | 4 | 4 | **Fix next** |
| 3 | Retrieval Top-K / ranking failure | 1 | 4 | 4 | Investigate next |
| 4 | Correct unsupported-question refusal | 1 | 2 | 2 | Preserve behavior |
| 5 | Citation / grounding failure | 0 | 4 | 0 | No demonstrated issue |
| 6 | Other | 0 | 2 | 0 | No demonstrated issue |

### Ranking note

The generation quota failure has the highest raw frequency × severity score,
but it is an infrastructure/provider limitation rather than an application-level
RAG quality problem.

The selected application-level fix target is therefore:

**False refusal despite sufficient retrieved evidence.**

The retrieval Top-K/ranking problem is recorded as a separate application-level
issue to investigate next.

---

## 1. False Refusal Despite Sufficient Retrieved Evidence

**Frequency:** 1 / 20 traces

**Trace:** 10

**Severity:** 4 / 5

### Description

The retriever returned relevant documentation containing sufficient evidence to
answer the user's question, but the generation layer returned the standard
refusal instead.

### Evidence

**Trace 10**

Question:

> When does a MAUI window become no longer visible in the lifecycle?

The top five retrieved results were from `app-lifecycle.md`, including the
`App lifecycle`, `Cross-platform lifecycle events`, and Windows lifecycle
sections.

The retrieved context included:

- the `Window` class lifecycle states;
- the `Stopped` lifecycle state;
- the mapping from `Stopped` to platform lifecycle events;
- the Windows `VisibilityChanged` mapping;
- the Windows `OnVisibilityChanged` delegate.

Despite this relevant context, the final answer was:

> I couldn't find that information in the provided documentation.

The response was marked `Grounded: False`.

### User impact

High. The assistant fails to answer a question for which the retrieved
documentation contains sufficient supporting evidence.

### Likely failure layer

Generation / grounding decision.

The retrieval results demonstrate that relevant evidence reached the generation
layer. The failure occurs when the model decides whether the supplied evidence
is sufficient to answer.

### Hypothesis

The generation prompt may be too conservative when the user's wording differs
from the wording used in the documentation, particularly when the answer
requires combining related facts from multiple retrieved context items.

### Chosen fix

Improve the generation prompt so the model:

1. Inspects all supplied context before refusing.
2. Recognizes paraphrases and semantically equivalent wording.
3. Allows synthesis of directly supported facts across multiple context items.
4. Answers when sufficient evidence is present.
5. Continues to refuse when evidence is genuinely absent.
6. Preserves citation and grounding requirements.

---

## 2. Retrieval Top-K / Ranking Failure

**Frequency:** 1 / 20 traces

**Trace:** 11

**Severity:** 4 / 5

### Description

The answer existed in the indexed documentation, but the relevant chunk was
not returned in the original Top-5 retrieval results.

As a result, the generation layer did not receive the exact evidence required
to answer the question.

### Evidence

**Trace 11**

Question:

> How many rows and columns does Grid have if none are declared?

The original Top-5 retrieval returned these chunks:

- `grid-current-structure-4`
- `grid-current-structure-2`
- `grid-current-structure-1`
- `grid-current-structure-14`
- `grid-current-structure-6`

These chunks were related to Grid rows, columns, properties, and examples, but
the specific default-value statement was absent.

The required documentation statement exists in:

- `chunk_id`: `grid-current-structure-0`
- `source_file`: `grid.md`
- `section`: `Grid`

The chunk contains:

> By default, a Grid contains one row and one column.

When the same query was tested with `n_results=10`, the
`grid-current-structure-0` chunk was returned.

### User impact

Medium to high. The answer is present in the corpus, but the retrieval layer
fails to place the required evidence within the Top-K context supplied to the
generator.

### Likely failure layer

Retrieval ranking / Top-K selection.

### Hypothesis

The semantic query is ranking several broadly related Grid chunks above the
specific chunk containing the requested default value.

### Action

Do not change retrieval yet.

First complete validation of the selected generation prompt intervention.

After that, investigate retrieval improvements such as:

- larger Top-K;
- metadata-aware ranking;
- query expansion;
- reranking;
- improved chunk-level retrieval for direct fact questions.

The retrieval algorithm should not be changed solely to fix Trace 11 until the
generation intervention has been validated.

---

## 3. Generation Infrastructure / Quota Failure

**Frequency:** 7 / 20 traces

**Traces:** 14, 15, 16, 17, 18, 19, 20

**Severity:** 3 / 5

### Description

The generation request failed because the Gemini API project/model quota was
exhausted. No model answer was produced.

### Evidence

These traces contain:

- `[no answer]`
- `Grounded: None`

The generation failure was a `429 RESOURCE_EXHAUSTED` error associated with
the Gemini free-tier generation request quota.

The API reported:

```text
generate_content_free_tier_requests
limit: 20
model: gemini-3.6-flash