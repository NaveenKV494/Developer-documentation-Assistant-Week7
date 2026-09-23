from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

from google import genai
from google.genai import types

from app.agent.limits import BudgetLimits
from app.agent.state import AgentMemory, AgentStep, AgentTrace
from app.agent.tools import AVAILABLE_TOOLS, TOOL_DESCRIPTIONS
from app.config import GENERATION_MODEL, require_api_key
from app.models.response import Citation, RAGResponse


REACT_SYSTEM_PROMPT = """You are an expert Developer Documentation AI Agent.
Your task is to investigate the user's technical question using developer documentation tools, reason about findings, and synthesize a complete, accurately cited technical answer.

Available Tools:
{tool_descriptions}

Follow the ReAct (Reason + Act) loop strictly:

Thought: Consider what information is needed to answer the user's question, what has been discovered so far, and whether further searches or section inspections are necessary.
Action: The name of the tool to use (must be one of: {tool_names}) OR 'FINISH' if you have gathered sufficient documentation evidence.
Action Input: A valid JSON dictionary of keyword arguments for the tool. E.g. {{"query": "dependency injection configuration"}} or {{"section": "Authentication"}}.
Observation: (This will be provided to you after executing the tool)

Rules:
1. Always formulate specific search queries based on developer keywords.
2. If a search result mentions relevant sections or concepts that need elaboration, use `inspect_section` or a targeted `search_docs` to drill down.
3. When you have sufficient evidence to answer the question, output:
   Action: FINISH
   Action Input: {{"summary": "Evidence gathered"}}
4. Only rely on facts present in the documentation context. If the documentation does not contain the answer, conclude that it is unavailable.
5. Provide concise Thoughts explaining your technical rationale at each step.
"""

SYNTHESIS_PROMPT = """You are a technical documentation assistant. Answer the user's question using ONLY the provided documentation evidence gathered during the agent investigation.

Documentation Evidence Gathered:
{evidence}

User Question:
{question}

Instructions:
1. Provide a clear, technically precise answer directly addressing the question.
2. Ground your answer strictly in the gathered evidence. Do not hallucinate.
3. If the documentation does not contain enough information, set grounded=false and state clearly what is missing.
4. Include accurate citations referencing the chunk_id, filename, section, and page for every referenced statement.
"""


def _parse_react_response(text: str) -> tuple[str, str, dict[str, Any]]:
    """
    Parse LLM ReAct output into (thought, action, action_input).
    Handles edge cases with markdown formatting or malformed JSON.
    """
    thought = ""
    action = "FINISH"
    action_input: dict[str, Any] = {}

    # Extract Thought
    thought_match = re.search(r"Thought:\s*(.*?)(?=Action:|$)", text, re.DOTALL | re.IGNORECASE)
    if thought_match:
        thought = thought_match.group(1).strip()

    # Extract Action
    action_match = re.search(r"Action:\s*([a-zA-Z_]+)", text, re.IGNORECASE)
    if action_match:
        action = action_match.group(1).strip()

    # Extract Action Input
    input_match = re.search(r"Action Input:\s*(\{.*?\}|\[.*?\]|`.*?`|[^\n]+)", text, re.DOTALL | re.IGNORECASE)
    if input_match:
        raw_input = input_match.group(1).strip()
        raw_input = re.sub(r"^```json\s*|\s*```$", "", raw_input).strip()
        try:
            action_input = json.loads(raw_input)
        except Exception:
            # Fallback: if it's a raw string or key-value format
            if "{" in raw_input and "}" in raw_input:
                try:
                    bracketed = raw_input[raw_input.find("{"):raw_input.rfind("}") + 1]
                    action_input = json.loads(bracketed)
                except Exception:
                    action_input = {"query": raw_input}
            else:
                action_input = {"query": raw_input.strip("\"' ")}

    if not thought and not action_match:
        # LLM answered directly without ReAct headers
        thought = "Direct response generated."
        action = "FINISH"
        action_input = {"direct_answer": text}

    return thought, action, action_input


def _build_agent_prompt(question: str, steps_scratchpad: str) -> str:
    tool_names = ", ".join(list(AVAILABLE_TOOLS.keys()) + ["FINISH"])
    system = REACT_SYSTEM_PROMPT.format(
        tool_descriptions=TOOL_DESCRIPTIONS,
        tool_names=tool_names,
    )
    
    prompt = f"""{system}

Question: {question}

Scratchpad of previous steps:
{steps_scratchpad if steps_scratchpad else '(No steps executed yet)'}

Next step:
"""
    return prompt


def _synthesize_final_answer(
    client: genai.Client,
    question: str,
    memory: AgentMemory,
) -> tuple[RAGResponse, int, int]:
    """
    Generate structured final answer with citations from all accumulated evidence.
    """
    evidence_blocks: list[str] = []
    for idx, chunk in enumerate(memory.accumulated_context):
        cid = chunk.get("chunk_id", f"chunk_{idx}")
        fname = chunk.get("filename", "doc")
        sec = chunk.get("section", "General")
        page = chunk.get("page", 1)
        text = chunk.get("content", "") or chunk.get("text", "")
        evidence_blocks.append(
            f"[Source: {fname} | Section: {sec} | Page: {page} | Chunk ID: {cid}]\n{text}"
        )

    evidence_text = "\n\n---\n\n".join(evidence_blocks) if evidence_blocks else "No documentation found."

    prompt = SYNTHESIS_PROMPT.format(
        evidence=evidence_text,
        question=question,
    )

    try:
        response = client.models.generate_content(
            model=GENERATION_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RAGResponse,
                temperature=0,
            ),
        )
        
        prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) if hasattr(response, "usage_metadata") else 0
        comp_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) if hasattr(response, "usage_metadata") else 0

        parsed = (
            RAGResponse.model_validate(response.parsed)
            if getattr(response, "parsed", None) is not None
            else RAGResponse.model_validate_json(response.text)
        )
        return parsed, prompt_tokens or 0, comp_tokens or 0
    except Exception as exc:
        # Fallback if synthesis schema fails
        fallback_resp = RAGResponse(
            answer=f"Could not synthesize response: {exc}",
            grounded=False,
            citations=memory.citations_pool[:4],
        )
        return fallback_resp, 0, 0


def run_agent(
    question: str,
    document_id: str | None = None,
    max_steps: int = 6,
    max_time_seconds: float = 30.0,
    collection_name: str | None = None,
    step_callback: Callable[[AgentStep], None] | None = None,
) -> AgentTrace:
    """
    Run the hand-built ReAct agent loop for developer documentation investigation.
    """
    client = genai.Client(api_key=require_api_key())
    limits = BudgetLimits(max_steps=max_steps, max_time_seconds=max_time_seconds)
    memory = AgentMemory()
    trace = AgentTrace(question=question, mode="agent")
    
    scratchpad_entries: list[str] = []
    total_prompt_tokens = 0
    total_comp_tokens = 0
    llm_calls = 0

    while True:
        # 1. Check budget limits before starting next step
        allowed, stop_reason = limits.check_step_budget()
        if not allowed:
            trace.stopped_safely = True
            trace.stop_reason = stop_reason
            break

        step_num = limits.current_steps + 1
        step_start_time = time.time()
        step = AgentStep(step_number=step_num)

        # 2. Build ReAct Prompt
        scratchpad_str = "\n\n".join(scratchpad_entries)
        prompt = _build_agent_prompt(question, scratchpad_str)

        # 3. Call LLM for reasoning and next action
        try:
            llm_calls += 1
            response = client.models.generate_content(
                model=GENERATION_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                ),
            )
            
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                total_prompt_tokens += getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                total_comp_tokens += getattr(response.usage_metadata, "candidates_token_count", 0) or 0

            response_text = response.text or ""
        except Exception as exc:
            step.status = "error"
            step.error_message = f"LLM generation failed: {exc}"
            step.duration_ms = (time.time() - step_start_time) * 1000
            trace.steps.append(step)
            trace.stopped_safely = False
            trace.stop_reason = f"LLM error: {exc}"
            if step_callback:
                step_callback(step)
            break

        # 4. Parse ReAct output
        thought, action, action_input = _parse_react_response(response_text)
        step.thought = thought
        step.tool_name = action
        step.tool_input = action_input

        # Check for loop repetition with action signature
        sig = f"{action}:{json.dumps(action_input, sort_keys=True)}"
        loop_ok, loop_reason = limits.record_step(action_signature=sig)
        if not loop_ok:
            step.status = "budget_exceeded"
            step.error_message = loop_reason
            step.duration_ms = (time.time() - step_start_time) * 1000
            trace.steps.append(step)
            trace.stopped_safely = True
            trace.stop_reason = loop_reason
            if step_callback:
                step_callback(step)
            break

        # 5. Check if Agent decided to FINISH
        if action.upper() == "FINISH" or action not in AVAILABLE_TOOLS:
            step.observation = "Agent completed research and moved to final answer synthesis."
            step.duration_ms = (time.time() - step_start_time) * 1000
            trace.steps.append(step)
            if step_callback:
                step_callback(step)
            break

        # 6. Execute selected Tool
        tool_allowed, tool_limit_reason = limits.record_tool_call()
        if not tool_allowed:
            step.status = "budget_exceeded"
            step.error_message = tool_limit_reason
            step.duration_ms = (time.time() - step_start_time) * 1000
            trace.steps.append(step)
            trace.stopped_safely = True
            trace.stop_reason = tool_limit_reason
            if step_callback:
                step_callback(step)
            break

        tool_func = AVAILABLE_TOOLS[action]
        try:
            # Pass document_id / collection_name if applicable
            tool_args = dict(action_input)
            if "document_id" not in tool_args and document_id:
                tool_args["document_id"] = document_id
            if collection_name:
                tool_args["collection_name"] = collection_name

            tool_result = tool_func(**tool_args)
            step.tool_output = tool_result

            # Process observations & update memory
            obs_lines: list[str] = []
            if action == "search_docs":
                res_items = tool_result.get("results", [])
                query_str = tool_result.get("query", "")
                memory.queried_terms.append(query_str)
                obs_lines.append(f"Found {len(res_items)} relevant document chunks for query '{query_str}':")
                for r in res_items:
                    memory.accumulated_context.append(r)
                    memory.citations_pool.append(Citation(
                        chunk_id=r["chunk_id"],
                        document_id=r["document_id"],
                        filename=r["filename"],
                        page=r["page"],
                        section=r["section"],
                    ))
                    obs_lines.append(f"- [{r['filename']} | {r['section']} | Score: {r['similarity_score']}]: {r['content'][:250]}...")
            
            elif action == "inspect_section":
                ins_items = tool_result.get("items", [])
                sec_name = tool_args.get("section") or tool_args.get("chunk_id") or "Section"
                memory.inspected_sections.append(sec_name)
                obs_lines.append(f"Inspected {len(ins_items)} chunks for '{sec_name}':")
                for item in ins_items:
                    memory.accumulated_context.append(item)
                    memory.citations_pool.append(Citation(
                        chunk_id=item["chunk_id"],
                        document_id=item["document_id"],
                        filename=item["filename"],
                        page=item["page"],
                        section=item["section"],
                    ))
                    obs_lines.append(f"- [{item['filename']} | {item['section']}]: {item['content'][:250]}...")

            step.observation = "\n".join(obs_lines) if obs_lines else json.dumps(tool_result)[:300]
        except Exception as exc:
            step.status = "error"
            step.error_message = f"Tool execution failed: {exc}"
            step.observation = f"Error executing tool '{action}': {exc}"

        step.duration_ms = (time.time() - step_start_time) * 1000
        trace.steps.append(step)
        if step_callback:
            step_callback(step)

        # Append to scratchpad for next iteration
        scratchpad_entry = f"Step {step_num}:\nThought: {step.thought}\nAction: {step.tool_name}\nAction Input: {json.dumps(step.tool_input)}\nObservation: {step.observation}"
        scratchpad_entries.append(scratchpad_entry)

    # 7. Synthesize final answer
    synth_start = time.time()
    final_resp, synth_prompt_tok, synth_comp_tok = _synthesize_final_answer(client, question, memory)
    llm_calls += 1
    total_prompt_tokens += synth_prompt_tok
    total_comp_tokens += synth_comp_tok

    # Assemble trace metadata
    trace.final_response = final_resp
    trace.total_steps = len(trace.steps)
    trace.total_tool_calls = limits.current_tool_calls
    trace.total_llm_calls = llm_calls
    trace.total_latency_seconds = limits.elapsed_seconds()
    trace.estimated_prompt_tokens = total_prompt_tokens
    trace.estimated_completion_tokens = total_comp_tokens

    return trace
