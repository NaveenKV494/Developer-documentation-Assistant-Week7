from __future__ import annotations

import sys
from app.agent.agent import run_agent
from app.workflow.fixed_workflow import run_fixed_workflow


def main():
    test_question = "How should I configure dependency injection in this project, and what lifetime should I use for a service that maintains state?"
    print(f"=== Testing Fixed Workflow ===")
    wf_trace = run_fixed_workflow(test_question)
    print(f"Fixed Workflow Completed in {wf_trace.total_latency_seconds:.2f}s | Steps: {wf_trace.total_steps} | Tool calls: {wf_trace.total_tool_calls} | LLM calls: {wf_trace.total_llm_calls}")
    if wf_trace.final_response:
        print(f"Answer snippet: {wf_trace.final_response.answer[:150]}...")
        print(f"Grounded: {wf_trace.final_response.grounded} | Citations: {len(wf_trace.final_response.citations)}")

    print("\n=== Testing Autonomous Agent ===")
    def on_step(step):
        print(f"[Step {step.step_number}] Action: {step.tool_name} | Thought: {step.thought[:60]}... ({step.duration_ms:.0f}ms)")
        
    agent_trace = run_agent(test_question, step_callback=on_step)
    print(f"Agent Completed in {agent_trace.total_latency_seconds:.2f}s | Steps: {agent_trace.total_steps} | Tool calls: {agent_trace.total_tool_calls} | LLM calls: {agent_trace.total_llm_calls}")
    print(f"Stopped safely: {agent_trace.stopped_safely} | Reason: {agent_trace.stop_reason}")
    if agent_trace.final_response:
        print(f"Answer snippet: {agent_trace.final_response.answer[:150]}...")
        print(f"Grounded: {agent_trace.final_response.grounded} | Citations: {len(agent_trace.final_response.citations)}")


if __name__ == "__main__":
    main()
