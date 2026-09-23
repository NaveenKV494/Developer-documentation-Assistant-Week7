# Week 6 — Evals & Error Analysis Report
## Track E: Developer Documentation (The Core)

> **Objective:** Build automatic tests that score every change, validate the LLM judge against human grading, capture Week 5 regression failures, and measure before/after score deltas per problem type.

---

## 1. Executive Summary

- **One-Command Test Runner:** `python run_evals.py`
- **Total Test Cases Evaluated:** 16
- **Judge Validation Status:** `VALIDATED (Substantial Agreement)`
- **Human-Judge Agreement Rate:** `100.0%` (Cohen's $\kappa = 1.0000$)
- **Overall Pipeline Score (Baseline -> Improved):** `0.682` -> `0.961` (**Delta: +0.279**)

---

## 2. Judge Validation (Human Agreement Benchmark)

Before trusting an AI judge to score the application, we validated it against 12 human-graded calibration examples representing accurate answers, hallucinations, false refusals, and correct refusals.

| Metric | Value | Target Benchmark | Assessment |
| :--- | :---: | :---: | :--- |
| **Observed Agreement** | **100.0%** | $\ge 80\%$ | **Pass** |
| **Cohen's Kappa ($\kappa$)** | **1.0000** | $\ge 0.65$ | **Substantial Agreement** |
| **Precision** | **1.000** | $\ge 0.80$ | Zero false positives on bad answers |
| **Recall** | **1.000** | $\ge 0.80$ | High identification of correct responses |
| **F1 Score** | **1.000** | $\ge 0.80$ | Robust balanced performance |

### Confusion Matrix

- **True Positives (TP):** 7 (Human: Pass, Judge: Pass)
- **True Negatives (TN):** 5 (Human: Fail, Judge: Fail)
- **False Positives (FP):** 0 (Human: Fail, Judge: Pass)
- **False Negatives (FN):** 0 (Human: Pass, Judge: Fail)

---

## 3. Before vs After Score Delta per Problem Type

We compared the **Baseline** configuration (conservative literal prompt + Top-5 retrieval) against the **Improved** configuration (synthesis-aware prompt + structure-aware chunks + Top-8 context).

| Problem Type | Tests | Baseline Score | Improved Score | Score Delta ($\Delta$) | Status |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `false_refusal_regression` | 2 | 0.458 | 0.812 | **+0.355** | Improved |
| `retrieval_ranking_regression` | 2 | 0.812 | 1.000 | **+0.188** | Improved |
| `supported_fact_extraction` | 6 | 0.688 | 0.958 | **+0.271** | Improved |
| `unsupported_refusal` | 4 | 1.000 | 1.000 | 0.000 | Maintained |
| `multi_chunk_synthesis` | 2 | 0.125 | 1.000 | **+0.875** | Improved |
| **OVERALL COMPOSITE** | **16** | **0.682** | **0.961** | **+0.279** | **PROVEN IMPROVEMENT** |

---

## 4. Regression Tests from Week 5 Real Failures

### Regression 1: False Refusal on Window Lifecycle Visibility (Week 5 Trace 10)
- **Question:** *'When does a MAUI window become no longer visible in the lifecycle?'*
- **Week 5 Failure:** The baseline model falsely refused with *'I couldn't find that information in the provided documentation'* even though context contained the Stopped state mapping to `VisibilityChanged`.
- **Week 6 Result:**
  - **Baseline:** Refusal triggered (Score: 0.25)
  - **Improved:** Correctly answered: *'A .NET MAUI window transitions to the Stopped state when it is no longer visible, corresponding to VisibilityChanged on Windows.'* (Score: 1.00, Delta: **+0.75**)

### Regression 2: Retrieval Top-K Miss for Default Row/Column Count (Week 5 Trace 11)
- **Question:** *'How many rows and columns does Grid have if none are declared?'*
- **Week 5 Failure:** Top-5 retrieval returned 5 general Grid layout chunks, missing chunk 0 containing *'By default, a Grid contains one row and one column.'*
- **Week 6 Result:**
  - **Baseline:** Default chunk missing from Top-5 context -> model refuses or answers vaguely.
  - **Improved:** Enhanced retrieval context (Top-K=8) captures chunk 0 -> model provides the verified fact *'By default, a Grid contains one row and one column'* with full citation (Score: 1.00).

---

## 5. Mentor Review Checklist Verification

- [x] **Does the test set run with a single command?**  
  Yes: `python run_evals.py` runs the entire suite automatically.
- [x] **Are last week's real failures included as tests?**  
  Yes: Both Trace 10 (false refusal) and Trace 11 (ranking default value) are permanent tests (`REG-10`, `REG-11`).
- [x] **Did you check the AI judge agrees with human grading before trusting it?**  
  Yes: Tested on 12 human-labeled items yielding 100.0% agreement and Cohen's $\kappa = 1.0000$.
- [x] **Is there a before-and-after score proving the change helped?**  
  Yes: Demonstrated a +0.279 overall delta with breakdown across all 5 problem types.