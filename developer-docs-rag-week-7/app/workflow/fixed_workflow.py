from __future__ import annotations

import time
from typing import Any, Callable

from google import genai
from google.genai import types

from app.agent.state import AgentMemory, AgentStep, AgentTrace
from app.agent.tools import inspect_section, search_docs
from app.config import GENERATION_MODEL, require_api_key
from app.models.response import Citation, RAGResponse


SYNTHESIS_PROMPT = """You are a technical documentation assistant. Answer the user's question using ONLY the provided documentation context.

Documentation Context:
{evidence}

User Question:
{question}

Instructions:
1. Provide a clear, technically precise answer directly addressing the question.
2. Ground your answer strictly in the gathered context. Do not hallucinate.
3. If the documentation does not contain enough information, set grounded=false and state clearly what is missing.
4. Include accurate citations referencing the chunk_id, filename, section, and page for every referenced statement.
"""


def run_fixed_workflow(
    question: str,
    document_id: str | None = None,
    collection_name: str | None = None,
    step_callback: Callable[[AgentStep], None] | None = None,
) -> AgentTrace:
    """
    Run a deterministic fixed-sequence workflow for developer documentation Q&A:
    Step 1: Primary search (Top-5 chunks)
    Step 2: Context inspection on top section
    Step 3: Direct LLM generation & citation validation
    """
    start_time = time.time()
    trace = AgentTrace(question=question, mode="fixed_workflow")
    memory = AgentMemory()
    client = genai.Client(api_key=require_api_key())
    
    total_prompt_tokens = 0
    total_comp_tokens = 0
    llm_calls = 0
    tool_calls = 0

    # Step 1: Search Docs (Deterministic)
    step1_start = time.time()
    step1 = AgentStep(
        step_number=1,
        thought="Deterministic Step 1: Execute primary semantic search for the user question.",
        tool_name="search_docs",
        tool_input={"query": question, "top_k": 5},
    )
    tool_calls += 1
    
    search_res = search_docs(
        query=question,
        document_id=document_id,
        top_k=5,
        collection_name=collection_name,
    )
    step1.tool_output = search_res
    results = search_res.get("results", [])
    
    obs_lines: list[str] = [f"Retrieved {len(results)} chunks:"]
    top_section = None
    for r in results:
        memory.accumulated_context.append(r)
        memory.citations_pool.append(Citation(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            filename=r["filename"],
            page=r["page"],
            section=r["section"],
        ))
        obs_lines.append(f"- [{r['filename']} | {r['section']}]: {r['content'][:200]}...")
        if not top_section and r.get("section") and r.get("section") != "General":
            top_section = r.get("section")

    step1.observation = "\n".join(obs_lines)
    step1.duration_ms = (time.time() - step1_start) * 1000
    trace.steps.append(step1)
    if step_callback:
        step_callback(step1)

    # Step 2: Deterministic Context Expansion if a prominent section was detected
    step2_start = time.time()
    step2 = AgentStep(
        step_number=2,
        thought=f"Deterministic Step 2: Expand context for identified section '{top_section or 'General'}'.",
        tool_name="inspect_section",
        tool_input={"section": top_section, "document_id": document_id},
    )
    tool_calls += 1

    if top_section:
        insp_res = inspect_section(
            document_id=document_id,
            section=top_section,
            collection_name=collection_name,
        )
        step2.tool_output = insp_res
        items = insp_res.get("items", [])
        # Add new items not already in context
        existing_ids = {c.get("chunk_id") for c in memory.accumulated_context}
        for it in items:
            if it.get("chunk_id") not in existing_ids:
                memory.accumulated_context.append(it)
                memory.citations_pool.append(Citation(
                    chunk_id=it["chunk_id"],
                    document_id=it["document_id"],
                    filename=it["filename"],
                    page=it["page"],
                    section=it["section"],
                ))
        step2.observation = f"Inspected section '{top_section}' and added {len(items)} chunks to context."
    else:
        step2.observation = "No specific sub-section identified for expansion; proceeding with search results."

    step2.duration_ms = (time.time() - step2_start) * 1000
    trace.steps.append(step2)
    if step_callback:
        step_callback(step2)

    # Step 3: LLM Synthesis (Single LLM Call)
    step3_start = time.time()
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
        llm_calls += 1
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
        total_prompt_tokens += prompt_tokens or 0
        total_comp_tokens += comp_tokens or 0

        final_resp = (
            RAGResponse.model_validate(response.parsed)
            if getattr(response, "parsed", None) is not None
            else RAGResponse.model_validate_json(response.text)
        )
    except Exception as exc:
        final_resp = RAGResponse(
            answer=f"Could not synthesize response: {exc}",
            grounded=False,
            citations=memory.citations_pool[:4],
        )

    step3 = AgentStep(
        step_number=3,
        thought="Deterministic Step 3: Synthesized final grounded answer with citations.",
        tool_name="FINISH",
        observation="Response generated successfully.",
        duration_ms=(time.time() - step3_start) * 1000,
    )
    trace.steps.append(step3)
    if step_callback:
        step_callback(step3)

    # Assemble trace metadata
    trace.final_response = final_resp
    trace.total_steps = len(trace.steps)
    trace.total_tool_calls = tool_calls
    trace.total_llm_calls = llm_calls
    trace.total_latency_seconds = time.time() - start_time
    trace.estimated_prompt_tokens = total_prompt_tokens
    trace.estimated_completion_tokens = total_comp_tokens
    trace.stopped_safely = True
    trace.stop_reason = "completed"

    return trace
