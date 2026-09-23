from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any

from app.agent.agent import run_agent
from app.workflow.fixed_workflow import run_fixed_workflow

ROOT_DIR = Path(__file__).resolve().parent
BENCHMARK_FILE = ROOT_DIR / "evals" / "week7_benchmark.json"
OUTPUT_FILE = ROOT_DIR / "data" / "race_results.json"


def evaluate_topic_coverage(answer: str, expected_topics: list[str]) -> float:
    """Calculate the fraction of expected technical concepts/keywords mentioned in answer."""
    if not expected_topics:
        return 1.0
    ans_lower = answer.lower()
    matches = sum(1 for topic in expected_topics if topic.lower() in ans_lower)
    return matches / len(expected_topics)


def run_race(benchmark_path: Path = BENCHMARK_FILE) -> dict[str, Any]:
    with open(benchmark_path, "r", encoding="utf-8") as f:
        questions = json.load(f)

    print(f"==================================================================")
    print(f"   STARTING WEEK 7 RACE: FIXED WORKFLOW vs AUTONOMOUS AGENT       ")
    print(f"   Evaluating {len(questions)} Technical Documentation Tasks     ")
    print(f"==================================================================\n")

    results: list[dict[str, Any]] = []

    for idx, item in enumerate(questions, 1):
        qid = item.get("id", f"q{idx}")
        category = item.get("category", "general")
        question = item["question"]
        expected_topics = item.get("expected_topics", [])

        print(f"[{idx}/{len(questions)}] ({category.upper()}) Question: {question[:70]}...")

        # 1. Run Fixed Workflow
        print("  -> Running Fixed Workflow...", end=" ", flush=True)
        wf_start = time.time()
        try:
            wf_trace = run_fixed_workflow(question)
            wf_elapsed = wf_trace.total_latency_seconds
            wf_ans = wf_trace.final_response.answer if wf_trace.final_response else ""
            wf_grounded = wf_trace.final_response.grounded if wf_trace.final_response else False
            wf_citations = len(wf_trace.final_response.citations) if wf_trace.final_response else 0
            wf_coverage = evaluate_topic_coverage(wf_ans, expected_topics)
            wf_success = True
            print(f"Done ({wf_elapsed:.2f}s, {wf_trace.total_steps} steps, {wf_trace.total_llm_calls} LLM call)")
        except Exception as exc:
            wf_elapsed = time.time() - wf_start
            wf_ans = ""
            wf_grounded = False
            wf_citations = 0
            wf_coverage = 0.0
            wf_success = False
            wf_trace = None
            print(f"Failed ({exc})")

        # 2. Run Autonomous Agent
        print("  -> Running Autonomous Agent...", end=" ", flush=True)
        ag_start = time.time()
        try:
            ag_trace = run_agent(question, max_steps=6, max_time_seconds=30.0)
            ag_elapsed = ag_trace.total_latency_seconds
            ag_ans = ag_trace.final_response.answer if ag_trace.final_response else ""
            ag_grounded = ag_trace.final_response.grounded if ag_trace.final_response else False
            ag_citations = len(ag_trace.final_response.citations) if ag_trace.final_response else 0
            ag_coverage = evaluate_topic_coverage(ag_ans, expected_topics)
            ag_success = ag_trace.stopped_safely
            print(f"Done ({ag_elapsed:.2f}s, {ag_trace.total_steps} steps, {ag_trace.total_tool_calls} tools, {ag_trace.total_llm_calls} LLM calls)")
        except Exception as exc:
            ag_elapsed = time.time() - ag_start
            ag_ans = ""
            ag_grounded = False
            ag_citations = 0
            ag_coverage = 0.0
            ag_success = False
            ag_trace = None
            print(f"Failed ({exc})")

        results.append({
            "id": qid,
            "category": category,
            "question": question,
            "expected_topics": expected_topics,
            "workflow": {
                "success": wf_success,
                "latency_sec": round(wf_elapsed, 2),
                "steps": wf_trace.total_steps if wf_trace else 0,
                "tool_calls": wf_trace.total_tool_calls if wf_trace else 0,
                "llm_calls": wf_trace.total_llm_calls if wf_trace else 0,
                "prompt_tokens": wf_trace.estimated_prompt_tokens if wf_trace else 0,
                "completion_tokens": wf_trace.estimated_completion_tokens if wf_trace else 0,
                "total_tokens": (wf_trace.estimated_prompt_tokens + wf_trace.estimated_completion_tokens) if wf_trace else 0,
                "grounded": wf_grounded,
                "citations_count": wf_citations,
                "topic_coverage": round(wf_coverage, 2),
                "answer_snippet": wf_ans[:200] + "..." if len(wf_ans) > 200 else wf_ans,
            },
            "agent": {
                "success": ag_success,
                "stop_reason": ag_trace.stop_reason if ag_trace else "error",
                "latency_sec": round(ag_elapsed, 2),
                "steps": ag_trace.total_steps if ag_trace else 0,
                "tool_calls": ag_trace.total_tool_calls if ag_trace else 0,
                "llm_calls": ag_trace.total_llm_calls if ag_trace else 0,
                "prompt_tokens": ag_trace.estimated_prompt_tokens if ag_trace else 0,
                "completion_tokens": ag_trace.estimated_completion_tokens if ag_trace else 0,
                "total_tokens": (ag_trace.estimated_prompt_tokens + ag_trace.estimated_completion_tokens) if ag_trace else 0,
                "grounded": ag_grounded,
                "citations_count": ag_citations,
                "topic_coverage": round(ag_coverage, 2),
                "answer_snippet": ag_ans[:200] + "..." if len(ag_ans) > 200 else ag_ans,
            }
        })
        time.sleep(1)  # Mild pause between benchmark iterations

    # Aggregate summaries
    wf_latencies = [r["workflow"]["latency_sec"] for r in results if r["workflow"]["success"]]
    ag_latencies = [r["agent"]["latency_sec"] for r in results if r["agent"]["success"]]

    wf_tokens = [r["workflow"]["total_tokens"] for r in results]
    ag_tokens = [r["agent"]["total_tokens"] for r in results]

    wf_coverage = [r["workflow"]["topic_coverage"] for r in results]
    ag_coverage = [r["agent"]["topic_coverage"] for r in results]

    single_hop_results = [r for r in results if r["category"] == "single_hop"]
    multi_hop_results = [r for r in results if r["category"] == "multi_hop"]

    summary = {
        "total_questions": len(questions),
        "workflow": {
            "success_rate": sum(1 for r in results if r["workflow"]["success"]) / len(results),
            "avg_latency_sec": round(sum(wf_latencies) / max(len(wf_latencies), 1), 2),
            "avg_steps": round(sum(r["workflow"]["steps"] for r in results) / len(results), 1),
            "avg_tool_calls": round(sum(r["workflow"]["tool_calls"] for r in results) / len(results), 1),
            "avg_llm_calls": round(sum(r["workflow"]["llm_calls"] for r in results) / len(results), 1),
            "avg_total_tokens": round(sum(wf_tokens) / len(results), 1),
            "avg_topic_coverage": round(sum(wf_coverage) / len(results), 2),
        },
        "agent": {
            "success_rate": sum(1 for r in results if r["agent"]["success"]) / len(results),
            "avg_latency_sec": round(sum(ag_latencies) / max(len(ag_latencies), 1), 2),
            "avg_steps": round(sum(r["agent"]["steps"] for r in results) / len(results), 1),
            "avg_tool_calls": round(sum(r["agent"]["tool_calls"] for r in results) / len(results), 1),
            "avg_llm_calls": round(sum(r["agent"]["llm_calls"] for r in results) / len(results), 1),
            "avg_total_tokens": round(sum(ag_tokens) / len(results), 1),
            "avg_topic_coverage": round(sum(ag_coverage) / len(results), 2),
        },
        "breakdown": {
            "single_hop": {
                "count": len(single_hop_results),
                "wf_avg_latency": round(sum(r["workflow"]["latency_sec"] for r in single_hop_results) / max(len(single_hop_results), 1), 2),
                "ag_avg_latency": round(sum(r["agent"]["latency_sec"] for r in single_hop_results) / max(len(single_hop_results), 1), 2),
                "wf_avg_coverage": round(sum(r["workflow"]["topic_coverage"] for r in single_hop_results) / max(len(single_hop_results), 1), 2),
                "ag_avg_coverage": round(sum(r["agent"]["topic_coverage"] for r in single_hop_results) / max(len(single_hop_results), 1), 2),
            },
            "multi_hop": {
                "count": len(multi_hop_results),
                "wf_avg_latency": round(sum(r["workflow"]["latency_sec"] for r in multi_hop_results) / max(len(multi_hop_results), 1), 2),
                "ag_avg_latency": round(sum(r["agent"]["latency_sec"] for r in multi_hop_results) / max(len(multi_hop_results), 1), 2),
                "wf_avg_coverage": round(sum(r["workflow"]["topic_coverage"] for r in multi_hop_results) / max(len(multi_hop_results), 1), 2),
                "ag_avg_coverage": round(sum(r["agent"]["topic_coverage"] for r in multi_hop_results) / max(len(multi_hop_results), 1), 2),
            }
        },
        "results": results,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n==================================================================")
    print("                       RACE RESULTS SUMMARY                       ")
    print("==================================================================")
    print(f"Metric                  | Fixed Workflow     | Autonomous Agent  ")
    print(f"------------------------+--------------------+-------------------")
    print(f"Success Rate            | {summary['workflow']['success_rate']*100:.1f}%              | {summary['agent']['success_rate']*100:.1f}%")
    print(f"Avg Latency             | {summary['workflow']['avg_latency_sec']}s               | {summary['agent']['avg_latency_sec']}s")
    print(f"Avg Steps               | {summary['workflow']['avg_steps']}                  | {summary['agent']['avg_steps']}")
    print(f"Avg Tool Calls          | {summary['workflow']['avg_tool_calls']}                  | {summary['agent']['avg_tool_calls']}")
    print(f"Avg LLM Calls           | {summary['workflow']['avg_llm_calls']}                  | {summary['agent']['avg_llm_calls']}")
    print(f"Avg Tokens              | {summary['workflow']['avg_total_tokens']}              | {summary['agent']['avg_total_tokens']}")
    print(f"Topic Coverage Score    | {summary['workflow']['avg_topic_coverage']*100:.1f}%              | {summary['agent']['avg_topic_coverage']*100:.1f}%")
    print("==================================================================")
    print(f"Results saved to: {OUTPUT_FILE}\n")

    return summary


if __name__ == "__main__":
    run_race()
