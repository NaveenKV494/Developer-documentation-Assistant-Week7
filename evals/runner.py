from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.llm.generator import generate_answer
from app.llm.prompts import REFUSAL, build_rag_prompt
from app.retrieval.retriever import retrieve_relevant_chunks
from evals.assertions import run_rule_assertions
from evals.judge import evaluate_with_judge


# Strict/conservative baseline prompt (simulating Week 5 pre-fix behavior)
BASELINE_SYSTEM_PROMPT = f"""
You are a developer documentation assistant.
Rules:
1. Answer ONLY using verbatim or near-verbatim facts from the supplied documentation context.
2. If the user query does not match the exact wording or if you cannot find a direct literal match, refuse immediately.
3. Do NOT synthesize, connect, or combine separate sections or multiple context items.
4. If the context does not contain an exact verbatim statement, set grounded=false, set answer to: {REFUSAL!r}, and return empty citations.
""".strip()


def build_baseline_prompt(query: str, retrieved_docs: list[dict]) -> str:
    context_parts = []
    for index, doc in enumerate(retrieved_docs, 1):
        context_parts.append(
            f"""[CONTEXT {index}]
chunk_id: {doc.get('chunk_id', 'unknown')}
source_file: {doc.get('source_file', 'unknown')}
page_id: {doc.get('page_id', 'unknown')}
section: {doc.get('section', '')}
content:
{doc.get('text', '')}
[END CONTEXT {index}]"""
        )
    return f"""{BASELINE_SYSTEM_PROMPT}

DOCUMENTATION CONTEXT:
{chr(10).join(context_parts) if context_parts else '[NO RETRIEVED CONTEXT]'}

USER QUESTION:
{query}
"""


import hashlib

RUN_CACHE_FILE = Path(__file__).parent / ".run_cache.json"


def _load_run_cache() -> dict[str, dict]:
    if not RUN_CACHE_FILE.exists():
        return {}
    try:
        with open(RUN_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_run_cache(cache: dict[str, dict]) -> None:
    try:
        with open(RUN_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def run_pipeline_baseline(test_case: dict[str, Any], use_cache: bool = True) -> dict[str, Any]:
    """Execute baseline configuration (Top-K=5, conservative literal prompt)."""
    from app.models.response import RAGResponse

    query = test_case["question"]
    key = hashlib.sha256(f"baseline|||{query}".encode("utf-8")).hexdigest()

    if use_cache:
        cache = _load_run_cache()
        if key in cache:
            entry = cache[key]
            return {
                "response": RAGResponse.model_validate(entry["response"]),
                "retrieved_chunks": entry["retrieved_chunks"],
                "latency_ms": entry["latency_ms"],
            }

    start_t = time.perf_counter()

    # Baseline retrieval Top-K=5
    chunks = retrieve_relevant_chunks(query=query, n_results=5, strategy="structure")

    # Generate with baseline conservative prompt
    prompt = build_baseline_prompt(query, chunks)
    response = generate_answer(prompt)
    latency_ms = round((time.perf_counter() - start_t) * 1000, 1)

    result = {
        "response": response,
        "retrieved_chunks": chunks,
        "latency_ms": latency_ms,
    }

    if use_cache:
        cache = _load_run_cache()
        cache[key] = {
            "response": response.model_dump(),
            "retrieved_chunks": chunks,
            "latency_ms": latency_ms,
        }
        _save_run_cache(cache)

    return result


def run_pipeline_improved(test_case: dict[str, Any], use_cache: bool = True) -> dict[str, Any]:
    """Execute improved configuration (Top-K=8, synthesis-enabled prompt)."""
    from app.models.response import RAGResponse

    query = test_case["question"]
    key = hashlib.sha256(f"improved|||{query}".encode("utf-8")).hexdigest()

    if use_cache:
        cache = _load_run_cache()
        if key in cache:
            entry = cache[key]
            return {
                "response": RAGResponse.model_validate(entry["response"]),
                "retrieved_chunks": entry["retrieved_chunks"],
                "latency_ms": entry["latency_ms"],
            }

    start_t = time.perf_counter()

    # Improved retrieval Top-K=8 to capture default-value chunks and broader context
    chunks = retrieve_relevant_chunks(query=query, n_results=8, strategy="structure")

    # Generate with improved synthesis-aware prompt
    prompt = build_rag_prompt(query, chunks)
    response = generate_answer(prompt)
    latency_ms = round((time.perf_counter() - start_t) * 1000, 1)

    result = {
        "response": response,
        "retrieved_chunks": chunks,
        "latency_ms": latency_ms,
    }

    if use_cache:
        cache = _load_run_cache()
        cache[key] = {
            "response": response.model_dump(),
            "retrieved_chunks": chunks,
            "latency_ms": latency_ms,
        }
        _save_run_cache(cache)

    return result



def evaluate_single_run(
    test_case: dict[str, Any],
    run_output: dict[str, Any],
    skip_judge: bool = False,
) -> dict[str, Any]:
    """Grade a single execution with both rule assertions and the LLM judge."""
    response = run_output["response"]
    chunks = run_output["retrieved_chunks"]

    # 1. Rule assertions
    assertion_results = run_rule_assertions(test_case, response, chunks)

    # 2. LLM Judge
    context_text = "\n\n".join(
        f"[{c.get('source_file')} - {c.get('section', '')}]\n{c.get('text', '')}"
        for c in chunks
    )

    if skip_judge:
        judge_score = 1.0 if assertion_results["passed"] else 0.0
        judge_verdict = "PASS" if assertion_results["passed"] else "FAIL"
        judge_reasoning = "Judge skipped via flag."
        faithfulness = 1.0 if assertion_results["passed"] else 0.0
        relevancy = 1.0 if assertion_results["passed"] else 0.0
    else:
        judge_eval = evaluate_with_judge(
            question=test_case["question"],
            context=context_text,
            answer=response.answer,
        )
        judge_score = judge_eval.score
        judge_verdict = judge_eval.verdict
        judge_reasoning = judge_eval.reasoning
        faithfulness = judge_eval.faithfulness
        relevancy = judge_eval.relevancy

    # Combined composite score (50% rule assertions + 50% judge score)
    composite_score = round(0.5 * assertion_results["pass_rate"] + 0.5 * judge_score, 3)
    passed_overall = assertion_results["passed"] and (judge_verdict == "PASS")

    return {
        "answer": response.answer,
        "grounded": response.grounded,
        "citations_count": len(response.citations),
        "latency_ms": run_output["latency_ms"],
        "assertions": assertion_results,
        "judge": {
            "score": judge_score,
            "verdict": judge_verdict,
            "faithfulness": faithfulness,
            "relevancy": relevancy,
            "reasoning": judge_reasoning,
        },
        "composite_score": composite_score,
        "passed": passed_overall,
    }


def run_evaluation_suite(
    test_set_path: str | Path | None = None,
    skip_judge: bool = False,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Run full comparison across all test cases between Baseline and Improved.
    Computes before/after scores broken down per problem type.
    """
    if test_set_path is None:
        test_set_path = Path(__file__).parent / "data" / "eval_test_set.json"

    with open(test_set_path, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    if verbose:
        print(f"\n========================================================")
        print(f"      RUNNING WEEK 6 EVAL SUITE ({len(test_cases)} TEST CASES)       ")
        print(f"========================================================\n")

    case_results = []
    by_problem_type: dict[str, dict[str, list[float]]] = {}

    for idx, tc in enumerate(test_cases, 1):
        ptype = tc["problem_type"]
        if ptype not in by_problem_type:
            by_problem_type[ptype] = {"baseline_scores": [], "improved_scores": []}

        if verbose:
            print(f"[{idx:02d}/{len(test_cases):02d}] Testing {tc['id']} ({ptype})...")

        # Run Baseline (Before)
        base_out = run_pipeline_baseline(tc)
        base_eval = evaluate_single_run(tc, base_out, skip_judge=skip_judge)

        # Run Improved (After)
        imp_out = run_pipeline_improved(tc)
        imp_eval = evaluate_single_run(tc, imp_out, skip_judge=skip_judge)

        by_problem_type[ptype]["baseline_scores"].append(base_eval["composite_score"])
        by_problem_type[ptype]["improved_scores"].append(imp_eval["composite_score"])

        score_delta = round(imp_eval["composite_score"] - base_eval["composite_score"], 3)
        delta_str = f"+{score_delta:.3f}" if score_delta >= 0 else f"{score_delta:.3f}"

        if verbose:
            print(f"       Baseline Score : {base_eval['composite_score']:.3f} ({'PASS' if base_eval['passed'] else 'FAIL'})")
            print(f"       Improved Score : {imp_eval['composite_score']:.3f} ({'PASS' if imp_eval['passed'] else 'FAIL'})  [Delta: {delta_str}]")

        case_results.append({
            "id": tc["id"],
            "problem_type": ptype,
            "question": tc["question"],
            "baseline": base_eval,
            "improved": imp_eval,
            "delta": score_delta,
        })

    # Aggregate by problem type
    breakdown = {}
    all_base = []
    all_imp = []

    for ptype, scores in by_problem_type.items():
        avg_base = sum(scores["baseline_scores"]) / len(scores["baseline_scores"]) if scores["baseline_scores"] else 0.0
        avg_imp = sum(scores["improved_scores"]) / len(scores["improved_scores"]) if scores["improved_scores"] else 0.0
        diff = round(avg_imp - avg_base, 3)

        breakdown[ptype] = {
            "count": len(scores["baseline_scores"]),
            "baseline_avg": round(avg_base, 3),
            "improved_avg": round(avg_imp, 3),
            "delta": diff,
        }
        all_base.extend(scores["baseline_scores"])
        all_imp.extend(scores["improved_scores"])

    total_base_avg = round(sum(all_base) / len(all_base), 3) if all_base else 0.0
    total_imp_avg = round(sum(all_imp) / len(all_imp), 3) if all_imp else 0.0
    total_delta = round(total_imp_avg - total_base_avg, 3)

    return {
        "total_test_cases": len(test_cases),
        "overall": {
            "baseline_score": total_base_avg,
            "improved_score": total_imp_avg,
            "delta": total_delta,
        },
        "problem_type_breakdown": breakdown,
        "details": case_results,
    }
