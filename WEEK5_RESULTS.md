# Week 5 — Evals & Error Analysis

## Module
**Week 5 · Module 3 · Evals & Error Analysis**

## Assignment
### The Core — Error Analysis: Reading Traces Like a Professional

---

# 1. What Was Required

The Week 5 assignment required a practical error-analysis exercise on the Developer Documentation RAG application.

The objective was to:

- Collect approximately 20 real answers from the application.
- Read every trace completely.
- Write a short, honest note about each failure.
- Use open coding before grouping failures.
- Group similar failures into named problem categories.
- Rank problem categories by frequency and severity.
- Distinguish application/RAG problems from infrastructure problems.
- Choose one problem to fix next.
- Write a prediction before making the change.
- Make an intervention.
- Validate whether the intervention actually helped.

> Read the traces first. Name the problems from the evidence. Then decide what to fix.

---

# 2. Application Under Evaluation

The application is a local Developer Documentation RAG assistant.

Current corpus:

- `app-lifecycle.md`
- `grid.md`
- `dependency-injection.md`
- `fundamentals-get-started.md`

Pipeline:

```text
Markdown documentation
        ↓
Document loading
        ↓
Metadata extraction
        ↓
Chunking
        ↓
Gemini Embedding 2
        ↓
ChromaDB
        ↓
Cosine similarity retrieval
        ↓
Top-K context
        ↓
Gemini generation
        ↓
Pydantic structured response
        ↓
Answer + grounded flag + citations
```

Technology:

- Gemini `gemini-embedding-2`
- Gemini `gemini-3.6-flash`
- ChromaDB
- Streamlit
- Pydantic

---

# 3. Trace Instrumentation

Trace-level observability was added before collecting the Week 5 traces.

Each trace records:

- User question
- Retrieved chunks
- Retrieval scores
- Source file
- Page/section metadata
- Generation model
- Final answer
- Grounded status
- Citations
- Errors

Trace records are stored as JSONL.

This allowed us to inspect not only the final answer, but also what evidence was retrieved and supplied to the generator.

---

# 4. Trace Collection

A reproducible runner was created:

```text
run_week5_traces.py
```

The test set contains 20 questions:

- 12 answerable/paraphrased questions
- 8 unsupported/refusal probes

This intentionally tests both:

```text
Can the system answer when evidence exists?
```

and:

```text
Can the system refuse when evidence does not exist?
```

---

# 5. Initial Database Issue

The clean Week 5 project package excluded the local ChromaDB database.

After extraction, the application initially had no indexed vectors.

The database was rebuilt using:

```powershell
python build_db.py --strategy structure --reset
```

Result:

```text
104 structure-aware chunks indexed
```

After rebuilding, retrieval returned relevant documentation chunks.

This was a setup issue, not a RAG quality failure.

---

# 6. Initial Trace Execution

The 20-trace evaluation was executed with:

```powershell
python run_week5_traces.py
```

The first run contained entries such as:

```text
ERROR
[no answer]
Grounded=None
```

This initially looked like possible RAG failures.

Inspection of the trace and generator behavior showed that `[no answer]` with `Grounded=None` can mean the generation request failed before a response was produced.

It does **not** necessarily mean that the model generated a refusal.

This distinction became important during the analysis.

---

# 7. Gemini Quota / Infrastructure Failure

The generator initially called Gemini directly without retry handling.

A bounded retry mechanism with backoff was added.

Retry behavior was confirmed through logs such as:

```text
Gemini request failed (attempt 1/4).
Retrying in 2.0s...
```

Eventually the provider returned:

```text
HTTP status 429
RESOURCE_EXHAUSTED
```

The relevant quota was:

```text
GenerateRequestsPerDayPerProjectPerModel-FreeTier
quotaValue: 20
```

Affected model:

```text
gemini-3.6-flash
```

After the quota was exhausted, the remaining trace requests could not produce generated answers.

---

# 8. Infrastructure vs Application Errors

Quota failures were not treated as RAG-quality failures.

A quota failure means:

```text
The application could not obtain a model response.
```

It does not mean:

```text
The RAG system produced an incorrect answer.
```

Therefore traces 14–20 were classified as:

> Generation infrastructure / quota failure

rather than:

> Generation quality failure

This prevented an external API limitation from being incorrectly treated as the main RAG defect.

---

# 9. Final Trace Distribution

| Result | Count |
|---|---:|
| Acceptable generated responses | 10 |
| False refusal despite sufficient evidence | 1 |
| Retrieval Top-K / ranking failure | 1 |
| Correct unsupported-question refusal | 1 |
| Generation infrastructure / quota failures | 7 |
| **Total** | **20** |

This should **not** be described as `13/20 successful quality evaluations`.

The accurate interpretation is:

```text
13 traces reached the generation/evaluation stage.
7 traces failed because the Gemini generation quota was exhausted.
```

Among the 13 generated/evaluated traces:

- 10 were acceptable
- 1 was a false refusal
- 1 exposed a retrieval Top-K problem
- 1 was a correct unsupported-question refusal

---

# 10. Trace-by-Trace Findings

## Traces 1–9

### Result
Acceptable generated answers.

### Observation
Relevant documentation was retrieved and the generated responses were consistent with the supplied evidence.

### Classification
No demonstrated failure.

---

## Trace 10 — False Refusal

### Question

```text
When does a MAUI window become no longer visible in the lifecycle?
```

### Result

The model returned:

```text
I couldn't find that information in the provided documentation.
```

with:

```text
grounded = false
citations = []
```

### Classification

> False refusal despite sufficient retrieved evidence

### Retrieval Investigation

The original Top-5 retrieval contained relevant lifecycle chunks covering:

- App lifecycle states
- Cross-platform lifecycle events
- Windows lifecycle behavior
- `OnVisibilityChanged`
- The `Stopped` state

A retrieved lifecycle mapping connects:

```text
Stopped
    ↓
Windows: VisibilityChanged
```

Therefore the supplied context contained enough evidence to answer through semantic synthesis.

### Why This Is a Failure

The question uses:

```text
no longer visible
```

while the documentation uses concepts such as:

```text
Stopped
VisibilityChanged
OnVisibilityChanged
```

The model needed to synthesize these related facts.

The evidence was present, but the model refused.

Therefore this was classified as a generation/grounding decision failure rather than a retrieval failure.

---

# 11. Prompt Intervention for Trace 10

The system instruction was strengthened to explicitly require:

- Treating paraphrases and synonyms as valid matches.
- Inspecting all supplied context before refusing.
- Answering whenever sufficient evidence exists.
- Not refusing merely because wording differs from the documentation.
- Matching citations to supplied chunks.
- Refusing unsupported questions.
- Avoiding invented facts.

The intended decision boundary was:

```text
Relevant evidence present
        ↓
Answer with evidence

Relevant evidence absent
        ↓
Refuse
```

---

# 12. Intervention Validation

A new API key was obtained because the previous key had exhausted its generation quota.

A targeted Trace 10 generation test then successfully reached Gemini.

However, the model still returned:

```json
{
  "answer": "I couldn't find that information in the provided documentation.",
  "grounded": false,
  "citations": []
}
```

Therefore:

```text
Infrastructure problem: resolved for this validation
Prompt intervention: executed
Trace 10 behavior: NOT YET FIXED
```

The first prompt intervention did not resolve Trace 10.

We deliberately did not claim success without validation evidence.

---

# 13. Current Trace 10 Hypothesis

The original hypothesis was:

> The grounding prompt is too conservative about paraphrased questions.

The prompt was changed to explicitly allow paraphrases.

The failure still occurred.

Therefore the hypothesis needs refinement.

A stronger hypothesis is:

> The model may still be failing to synthesize the relationship between multiple retrieved lifecycle facts, even though the supplied context contains enough evidence.

The next controlled experiment should test generation using a minimal, highly focused context and an explicit synthesis instruction.

---

# 14. Trace 11 — Retrieval Top-K / Ranking Failure

### Question

```text
How many rows and columns does Grid have if none are declared?
```

### Original Top-5 Retrieval

The Top-5 results discussed Grid properties, rows, columns, and examples.

However, the exact default behavior was not included in the original Top-5.

### Retrieval Investigation

The same query was tested with:

```text
n_results = 10
```

The missing relevant chunk appeared:

```text
grid-current-structure-0
```

It explicitly states:

```text
By default, a Grid contains one row and one column.
```

Another relevant chunk also appeared:

```text
grid-current-structure-3
```

which contains the same default behavior.

Therefore:

```text
Relevant evidence exists in the vector database.
```

but:

```text
Relevant evidence did not reach the original Top-5 context.
```

### Classification

> Retrieval Top-K / ranking failure

This is **not** a generation false refusal.

---

# 15. What Trace 11 Taught Us

The original setting was:

```text
Top-K = 5
```

The relevant answer existed in the indexed corpus but ranked below the first five results.

The failure path was:

```text
Correct document exists
        ↓
Correct chunk exists
        ↓
Embedding search finds it
        ↓
Ranking places it outside Top-K
        ↓
Generator never sees it
```

Increasing Top-K to 10 exposed the relevant chunk.

However, increasing Top-K is not automatically the final solution.

Possible future investigations include:

- Increasing Top-K
- Improving retrieval ranking
- Query rewriting
- Metadata/section-aware ranking
- Reranking

No final retrieval fix has been declared yet.

---

# 16. Trace 12

### Result
Acceptable answer.

### Classification
No demonstrated failure.

---

# 17. Trace 13 — Correct Unsupported Refusal

### Question

```text
What is the maximum number of concurrent API requests supported?
```

### Retrieval

The retrieved results were weak/unrelated to the requested fact.

The corpus does not document a maximum number of concurrent API requests.

### Result

The model correctly returned:

```text
I couldn't find that information in the provided documentation.
```

with:

```text
grounded = false
```

and no citations.

### Classification

> Correct unsupported-question refusal

This is desirable behavior and should be preserved.

---

# 18. Traces 14–20 — Quota Failures

The following traces failed because the Gemini generation quota was exhausted:

```text
Trace 14
Trace 15
Trace 16
Trace 17
Trace 18
Trace 19
Trace 20
```

The questions included topics such as:

- Monthly price
- Official SLA
- Maximum memory
- Recommended database
- Guaranteed response time
- Simultaneous users
- Production uptime guarantee

The API returned:

```text
429 RESOURCE_EXHAUSTED
```

with the free-tier daily generation quota reported as:

```text
20
```

These traces do not provide evidence about answer quality.

They provide evidence about generation infrastructure and the evaluation environment.

---

# 19. Open Coding

The traces were reviewed individually before grouping them.

| Trace | Observation |
|---|---|
| 1 | Answer supported by retrieved documentation |
| 2 | Answer supported by retrieved documentation |
| 3 | Answer supported by retrieved documentation |
| 4 | Answer supported by retrieved documentation |
| 5 | Answer supported by retrieved documentation |
| 6 | Answer supported by retrieved documentation |
| 7 | Answer supported by retrieved documentation |
| 8 | Answer supported by retrieved documentation |
| 9 | Answer supported by retrieved documentation |
| 10 | Relevant evidence retrieved, but model refused |
| 11 | Exact answer chunk exists but missed by Top-5 |
| 12 | Answer acceptable |
| 13 | Unsupported question correctly refused |
| 14 | Generation failed because of quota |
| 15 | Generation failed because of quota |
| 16 | Generation failed because of quota |
| 17 | Generation failed because of quota |
| 18 | Generation failed because of quota |
| 19 | Generation failed because of quota |
| 20 | Generation failed because of quota |

The grouping was performed only after these individual observations were made.

---

# 20. Error Taxonomy

## 1. Generation Infrastructure / Quota Failure

Traces:

```text
14–20
```

Frequency:

```text
7
```

Severity:

```text
3 / 5
```

Impact:

The application cannot generate an answer when the provider quota is exhausted.

Classification:

> Operational/infrastructure problem rather than RAG quality problem.

---

## 2. False Refusal Despite Sufficient Retrieved Evidence

Trace:

```text
10
```

Frequency:

```text
1
```

Severity:

```text
4 / 5
```

Impact:

The system refuses a question that the supplied documentation can answer.

Priority:

> **Chosen application-level problem to fix next.**

---

## 3. Retrieval Top-K / Ranking Failure

Trace:

```text
11
```

Frequency:

```text
1
```

Severity:

```text
4 / 5
```

Impact:

The correct answer exists in the corpus/database but does not reach the generator within Top-5 retrieval.

Priority:

> Investigate next.

---

## 4. Correct Unsupported-Question Refusal

Trace:

```text
13
```

Frequency:

```text
1
```

Severity:

```text
2 / 5
```

Impact:

None.

Priority:

> Preserve.

---

## 5. Citation / Grounding Failure

Frequency:

```text
0 demonstrated failures
```

No citation or grounding mismatch was demonstrated in the reviewed generated answers.

Priority:

> No demonstrated issue in this sample.

---

## 6. Other

Frequency:

```text
0
```

No additional meaningful failure category emerged from the 20 traces.

---

# 21. Ranked Taxonomy

| Rank | Problem Group | Frequency | Severity | Score | Priority |
|---:|---|---:|---:|---:|---|
| 1 | Generation infrastructure / quota failure | 7 | 3/5 | 21 | Monitor / operational fix |
| 2 | False refusal despite sufficient evidence | 1 | 4/5 | 4 | **Fix next** |
| 3 | Retrieval Top-K / ranking failure | 1 | 4/5 | 4 | Investigate next |
| 4 | Correct unsupported-question refusal | 1 | 2/5 | 2 | Preserve |
| 5 | Citation / grounding failure | 0 | 4/5 | 0 | No demonstrated issue |
| 6 | Other | 0 | 2/5 | 0 | No demonstrated issue |

The raw frequency × severity score places quota failure first.

However, quota exhaustion is an infrastructure constraint and not the application-level RAG behavior selected for improvement.

Therefore the selected application-level target is:

> **False refusal despite sufficient retrieved evidence — Trace 10**

---

# 22. Why Trace 10 Was Selected

Trace 10 was selected because:

1. The documentation contains the required underlying information.
2. Retrieval returned relevant lifecycle evidence.
3. The model still refused.
4. The failure directly affects the core purpose of the RAG application.
5. It is a generation/grounding decision rather than an external infrastructure problem.
6. It is potentially addressable through prompt/model/context design.

---

# 23. Prediction Before Intervention

The initial prediction was:

> If the system prompt explicitly tells the model to treat paraphrases and synonyms as valid matches, inspect all supplied context before refusing, and answer whenever sufficient evidence exists, then Trace 10 should stop being incorrectly refused.

Expected:

```text
Question:
"When does a MAUI window become no longer visible in the lifecycle?"

Evidence:
Stopped
VisibilityChanged
OnVisibilityChanged

Expected result:
Grounded answer with citation
```

rather than:

```text
I couldn't find that information in the provided documentation.
```

---

# 24. Intervention

The RAG system instruction was strengthened with rules covering:

- Paraphrase handling
- Synonym matching
- Complete context inspection
- Evidence-based refusal
- Citation correctness
- No invented facts
- Multi-part question handling

The prompt was designed to preserve refusal behavior for genuinely unsupported questions.

---

# 25. What We Learned About Retrieval

Trace 11 demonstrated that retrieval quality cannot be judged only by asking:

> Did the database contain the answer?

We also need to ask:

> Did the correct evidence reach the generator?

The sequence is:

```text
Corpus contains answer
        ≠
Retriever returns answer
        ≠
Generator receives answer
        ≠
Generator uses answer correctly
```

Trace 11 specifically demonstrated a Top-K/ranking failure.

---

# 26. What We Learned About Generation

Trace 10 demonstrated that even good retrieval does not guarantee a correct answer.

The pipeline can fail after retrieval:

```text
Correct evidence retrieved
        ↓
Evidence supplied to LLM
        ↓
LLM refuses
```

Therefore RAG evaluation must separately inspect:

- Retrieval relevance
- Context sufficiency
- Generation behavior
- Grounding/refusal behavior
- Citations

---

# 27. What We Learned About Refusal Behavior

Trace 13 demonstrated that refusal is not automatically an error.

### Correct refusal

```text
Evidence absent
        ↓
Refuse
```

This is desirable.

### False refusal

```text
Evidence present
        ↓
Refuse
```

This is a quality failure.

Therefore refusal evaluation must always be performed together with retrieval/context inspection.

---

# 28. What We Learned About Infrastructure

Quota failures demonstrated that evaluation infrastructure can affect an application's apparent quality.

Without inspecting the trace details, they could have been incorrectly counted as RAG failures.

Trace instrumentation allowed us to distinguish:

```text
No model response
```

from:

```text
Model generated an incorrect response
```

This distinction is essential for meaningful evaluation.

---

# 29. What We Learned About Observability

A useful RAG trace should allow us to answer:

```text
What did the user ask?
        ↓
What did retrieval return?
        ↓
What scores did the chunks receive?
        ↓
What context reached the model?
        ↓
What did the model answer?
        ↓
Was it grounded?
        ↓
What citations were returned?
        ↓
Did anything fail before generation?
```

Without this information, error analysis becomes guesswork.

---

# 30. What We Learned About Error Taxonomy

A UI result such as:

```text
No answer
```

could mean:

```text
Correct refusal
False refusal
API failure
Quota failure
```

These are fundamentally different problems.

The trace review allowed them to be separated.

The final taxonomy was therefore based on observed behavior rather than assumptions.

---

# 31. Benchmark vs Application

A benchmark may ask questions about:

- Pricing
- SLA
- Infrastructure limits
- Concurrency
- Uptime guarantees
- Product capabilities

But if those facts are intentionally absent from our application's documentation corpus, the correct behavior for our RAG application is refusal.

Therefore:

```text
Benchmark question ≠ automatically valid application question
```

Evaluation must consider the actual scope of the application.

---

# 32. Main Failure Modes Identified

The 20 traces exposed three meaningful application/operational issues:

### Infrastructure

```text
Gemini quota exhaustion
```

### Retrieval

```text
Correct chunk ranked outside Top-K
```

### Generation

```text
False refusal despite sufficient retrieved evidence
```

It also confirmed one desirable behavior:

```text
Correct refusal when evidence is absent
```

---

# 33. Fix Priority

Practical priority:

```text
1. Fix false refusal / generation behavior
2. Investigate retrieval Top-K / ranking
3. Monitor and improve evaluation infrastructure/quota handling
4. Preserve correct refusal behavior
```

The first two are the main RAG-quality problems found in the sample.

---

# 34. Week 5 Deliverable Status

| Requirement | Status |
|---|---|
| Collect ~20 real traces | Complete |
| Read every trace | Complete |
| Open-code individual failures | Complete |
| Name problem groups | Complete |
| Rank problem groups | Complete |
| Separate infrastructure from RAG failures | Complete |
| Choose one problem to fix | Complete |
| Write prediction before intervention | Complete |
| Perform intervention | Complete |
| Validate intervention | Complete, but intervention did not yet fix Trace 10 |
| Document remaining uncertainty | Complete |

---

# 35. Final Findings

```text
20 traces collected
        ↓
13 reached generated-response evaluation
        ↓
10 acceptable
1 false refusal
1 retrieval Top-K failure
1 correct refusal
        +
7 infrastructure quota failures
```

The most important findings are:

### Generation
Trace 10 showed that the model can refuse even when relevant evidence is present.

### Retrieval
Trace 11 showed that the correct evidence can exist in the database but miss the generator because of Top-K ranking.

### Refusal
Trace 13 showed that unsupported questions can be correctly refused.

### Infrastructure
Traces 14–20 showed that API quota exhaustion must be separated from RAG quality evaluation.

---

# 36. Selected Problem

The selected problem for the next iteration is:

> **False refusal despite sufficient retrieved evidence — Trace 10**

Reason:

```text
Relevant evidence exists
        +
Evidence reaches the model
        +
API request succeeds
        ↓
Model still refuses
```

This is a direct application-level RAG quality problem.

---

# 37. Current Conclusion

The Week 5 exercise showed that evaluating a RAG system requires more than counting correct and incorrect answers.

The full chain must be inspected:

```text
Question
   ↓
Retrieval
   ↓
Ranking
   ↓
Context
   ↓
Generation
   ↓
Grounding
   ↓
Citation
```

The 20-trace analysis identified:

- One generation/grounding false refusal
- One retrieval ranking failure
- Seven infrastructure quota failures
- One correct refusal behavior that should be preserved

The first prompt intervention improved the instructions but did not resolve Trace 10.

Therefore the current conclusion is deliberately conservative:

> **Trace 10 remains unresolved and requires a deeper controlled generation experiment.**

This is preferable to claiming success without evidence.

---

# 38. Key Lessons From Week 5

## Lesson 1 — Read the trace, not just the answer

The final answer alone cannot tell us where a RAG system failed.

## Lesson 2 — Retrieval and generation are separate failure surfaces

A correct answer can fail because:

```text
retrieval missed the evidence
```

or because:

```text
generation ignored/refused available evidence
```

These require different fixes.

## Lesson 3 — Refusal is not always a failure

A refusal is correct when evidence is absent.

A refusal is incorrect when evidence is present.

## Lesson 4 — Infrastructure failures must be separated

Quota exhaustion should not be counted as model-quality failure.

## Lesson 5 — Top-K matters

Having the correct chunk in the database is not enough.

The generator must actually receive it.

## Lesson 6 — Prompt changes need validation

Changing a prompt is not a fix by itself.

The fix is only demonstrated if the targeted behavior changes in validation.

## Lesson 7 — Keep uncertainty explicit

When an intervention does not work, document that result.

Do not rewrite the conclusion to make the intervention look successful.

---

# 39. Next Step

The immediate next step is a controlled investigation of Trace 10.

The experiment will determine whether the false refusal is caused by:

```text
Context noise
        OR
Prompt structure
        OR
Multi-chunk synthesis difficulty
        OR
Model generation/grounding behavior
```

Only after that experiment should another prompt or retrieval change be declared the fix.

---

# Final Week 5 Status

**Week 5 analysis: substantially complete**

The required 20-trace review, open coding, taxonomy, ranking, target selection, prediction, intervention, and validation process has been completed.

The major remaining technical investigation is:

> **Resolve the Trace 10 false refusal despite sufficient retrieved lifecycle evidence.**

The second priority is:

> **Investigate the Trace 11 Top-K / retrieval ranking failure.**

The quota issue has been identified and separated from application-quality failures.
