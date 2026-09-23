import json
from pathlib import Path
import sys
import time

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.agent.agent import run_agent
from app.agent.state import AgentStep, AgentTrace
from app.config import (
    CHROMA_COLLECTION_NAME,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DEFAULT_TOP_K,
    GENERATION_MODEL,
)
from app.ingestion.uploader import (
    clear_all_documents,
    delete_document,
    format_bytes,
    get_document_chunks,
    list_documents,
    seed_existing_markdown_docs,
    upload_and_index_document,
)
from app.retrieval.vector_store import get_client_mode
from app.workflow.fixed_workflow import run_fixed_workflow


st.set_page_config(
    page_title="Developer Docs AI: Agent vs Fixed Workflow",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for rich visual styling
st.markdown(
    """
    <style>
    .stMetric {
        background-color: rgba(128, 128, 128, 0.06);
        border: 1px solid rgba(128, 128, 128, 0.15);
        border-radius: 10px;
        padding: 8px 12px;
    }
    .badge-pdf { background-color: #fee2e2; color: #991b1b; padding: 2px 7px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
    .badge-docx { background-color: #dbeafe; color: #1e40af; padding: 2px 7px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
    .badge-md { background-color: #f3e8ff; color: #6b21a8; padding: 2px 7px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
    .badge-txt { background-color: #f1f5f9; color: #334155; padding: 2px 7px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
    
    .status-grounded {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background-color: rgba(34, 197, 94, 0.12);
        color: #16a34a;
        border: 1px solid rgba(34, 197, 94, 0.3);
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-bottom: 8px;
    }
    .status-ungrounded {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background-color: rgba(234, 179, 8, 0.12);
        color: #ca8a04;
        border: 1px solid rgba(234, 179, 8, 0.3);
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-bottom: 8px;
    }
    
    .citation-card {
        border-left: 4px solid #3b82f6;
        background-color: rgba(59, 130, 246, 0.05);
        border-radius: 0 8px 8px 0;
        padding: 10px 14px;
        margin: 6px 0;
    }
    
    .step-card {
        border-left: 4px solid #8b5cf6;
        background-color: rgba(139, 92, 246, 0.05);
        border-radius: 0 8px 8px 0;
        padding: 10px 14px;
        margin: 8px 0;
    }
    
    .scope-banner {
        border-radius: 8px;
        padding: 8px 14px;
        margin-bottom: 16px;
        font-size: 0.9rem;
        font-weight: 500;
    }
    .scope-banner-all {
        background-color: rgba(59, 130, 246, 0.08);
        border: 1px solid rgba(59, 130, 246, 0.2);
        color: #2563eb;
    }
    .scope-banner-isolated {
        background-color: rgba(168, 85, 247, 0.08);
        border: 1px solid rgba(168, 85, 247, 0.2);
        color: #9333ea;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_badge_html(file_type: str) -> str:
    ext = file_type.lower()
    badge_class = {
        "pdf": "badge-pdf",
        "docx": "badge-docx",
        "doc": "badge-docx",
        "md": "badge-md",
        "markdown": "badge-md",
        "txt": "badge-txt",
    }.get(ext, "badge-txt")
    return f'<span class="{badge_class}">{ext.upper()}</span>'


# ----------------- SIDEBAR -----------------
with st.sidebar:
    st.markdown("## 🤖 **Week 7: AI Agents**")
    st.caption("Track E: Developer Documentation Agent vs. Fixed Workflow")
    
    chroma_mode = get_client_mode()
    mode_icon = {"cloud": "☁️", "http": "🌐", "local": "💾"}.get(chroma_mode, "💾")
    st.caption(f"Vector Store: **{mode_icon} {chroma_mode.upper()}**")
    st.divider()

    # Mode Selector
    st.markdown("### 🎛️ Execution Mode")
    exec_mode = st.radio(
        "Select Pipeline Mode",
        options=["🤖 Autonomous Agent (ReAct)", "⚡ Fixed Workflow", "🏁 Race (Head-to-Head)"],
        index=0,
        help="Choose how queries are processed: dynamically by an agent loop, through a fixed sequence, or both raced side-by-side.",
    )

    st.divider()

    # Agent Limits Configuration
    if "Agent" in exec_mode or "Race" in exec_mode:
        with st.expander("🛡️ Agent Safety Limits", expanded=False):
            max_steps = st.slider("Max Steps", min_value=2, max_value=10, value=6)
            max_time = st.slider("Max Time (sec)", min_value=10, max_value=60, value=30)
    else:
        max_steps, max_time = 6, 30

    # Document Upload Section
    st.markdown("### 📤 Upload Documents")
    uploaded_files = st.file_uploader(
        "Drop documentation files here",
        type=["pdf", "docx", "md", "txt"],
        accept_multiple_files=True,
        help="Upload PDF, DOCX, Markdown, or Plain Text files.",
        label_visibility="collapsed",
    )

    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        upload_btn = st.button("⚡ Upload & Index", type="primary", use_container_width=True)
    with col_btn2:
        seed_btn = st.button("🌱 Seed Docs", use_container_width=True, help="Index sample .NET MAUI docs")

    if upload_btn and uploaded_files:
        with st.status(f"Indexing {len(uploaded_files)} document(s)...", expanded=True) as status:
            total_chunks = 0
            for file in uploaded_files:
                st.write(f"Processing **{file.name}** ({format_bytes(len(file.getvalue()))})...")
                try:
                    meta = upload_and_index_document(
                        file_source=file,
                        filename=file.name,
                    )
                    total_chunks += meta.chunk_count
                    st.write(f"✓ **{file.name}** → `{meta.chunk_count}` chunks indexed")
                except Exception as exc:
                    st.error(f"Error on {file.name}: {exc}")
            status.update(label=f"✓ Indexed {len(uploaded_files)} files ({total_chunks} total chunks)", state="complete")
            time.sleep(1)
            st.rerun()

    if seed_btn:
        with st.status("Seeding sample developer documents...", expanded=True) as status:
            seeded = seed_existing_markdown_docs()
            if seeded:
                status.update(label=f"✓ Seeded {len(seeded)} documents!", state="complete")
            else:
                status.update(label="All sample documents are already indexed.", state="complete")
            time.sleep(1)
            st.rerun()

    st.divider()

    # Document Library Section
    indexed_docs = list_documents()
    st.markdown(f"### 📑 Indexed Documents ({len(indexed_docs)})")

    if not indexed_docs:
        st.info("No documents indexed yet. Upload files above or click **Seed Docs**.")
    else:
        for doc in indexed_docs:
            with st.container():
                col_info, col_act = st.columns([5, 1])
                with col_info:
                    st.markdown(
                        f"{get_badge_html(doc.file_type)} **{doc.filename}**  \n"
                        f"<small style='opacity:0.75;'>{format_bytes(doc.file_size)} · {doc.chunk_count} chunks</small>",
                        unsafe_allow_html=True,
                    )
                with col_act:
                    if st.button("🗑️", key=f"del_{doc.document_id}", help=f"Delete {doc.filename}"):
                        delete_document(doc.document_id)
                        st.toast(f"Deleted {doc.filename}")
                        st.rerun()

    st.divider()
    if st.button("⚠️ Clear All Documents", type="secondary", use_container_width=True):
        cleared = clear_all_documents()
        st.toast(f"Cleared {cleared} documents.")
        st.rerun()


# ----------------- MAIN TABS -----------------
tab_chat, tab_race_benchmark, tab_chunks = st.tabs([
    "💬 Interactive Q&A / Investigation",
    "🏁 Race Benchmark & Comparison",
    "🔍 Document Chunks Explorer",
])

# ----------------- TAB 1: INTERACTIVE CHAT -----------------
with tab_chat:
    col_title, col_ctrl = st.columns([4, 1])
    with col_title:
        st.title("📚 Developer Documentation AI")
        st.caption(f"Active Mode: **{exec_mode}** | LLM: `{GENERATION_MODEL}`")
    with col_ctrl:
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # Scope Selection
    doc_options = ["🌐 All Documents (Global Search)"]
    doc_mapping: dict[str, str | None] = {"🌐 All Documents (Global Search)": None}
    for d in indexed_docs:
        label = f"📄 {d.filename} ({d.file_type.upper()})"
        doc_options.append(label)
        doc_mapping[label] = d.document_id

    col_scope_sel, col_scope_info = st.columns([2, 3])
    with col_scope_sel:
        selected_scope_label = st.selectbox(
            "Documentation Scope",
            options=doc_options,
            index=0,
            help="Choose 'All Documents' or isolate to a specific file.",
        )
    selected_document_id = doc_mapping[selected_scope_label]

    with col_scope_info:
        if selected_document_id:
            st.markdown(
                f'<div class="scope-banner scope-banner-isolated">🔒 <b>Isolated Scope:</b> Searching strictly inside <code>{selected_scope_label}</code></div>',
                unsafe_allow_html=True,
            )
        else:
            doc_count = len(indexed_docs)
            st.markdown(
                f'<div class="scope-banner scope-banner-all">🌐 <b>Global Scope:</b> Cross-document retrieval across all <b>{doc_count}</b> indexed files</div>',
                unsafe_allow_html=True,
            )

    # Sample Questions
    st.markdown("<small style='opacity:0.8;'>💡 <b>Sample Developer Questions:</b></small>", unsafe_allow_html=True)
    sugg_cols = st.columns(3)
    sample_queries = [
        "How is dependency injection configured, and what lifetime should a stateful service use?",
        "What is the default number of rows and columns in a Grid if unspecified?",
        "What lifecycle events occur when a .NET MAUI app starts, sleeps, and resumes?",
    ]
    triggered_query = None
    for idx, sq in enumerate(sample_queries):
        with sugg_cols[idx]:
            if st.button(f"📌 {sq[:45]}...", key=f"sq_{idx}", use_container_width=True, help=sq):
                triggered_query = sq

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display Chat History
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

            # If Trace is attached
            if msg.get("trace"):
                t = msg["trace"]
                mode_name = t.get("mode", "agent")

                # Grounded badge
                resp = t.get("final_response") or {}
                grounded = resp.get("grounded", False)
                if grounded:
                    st.markdown('<div class="status-grounded">🟢 Grounded in Documentation</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="status-ungrounded">🟡 Refusal / Insufficient Evidence</div>', unsafe_allow_html=True)

                # Steps / ReAct Trace
                steps = t.get("steps", [])
                if steps:
                    with st.expander(f"🐾 Execution Steps ({len(steps)} steps | {t.get('total_latency_seconds', 0):.2f}s)", expanded=(mode_name == "agent")):
                        for s in steps:
                            st.markdown(
                                f'<div class="step-card">'
                                f'<b>Step {s.get("step_number")} — Tool: <code>{s.get("tool_name")}</code></b> '
                                f'<small style="opacity:0.7;">({s.get("duration_ms", 0):.0f}ms)</small><br>'
                                f'<i>💭 Thought:</i> {s.get("thought", "N/A")}<br>'
                                f'<i>⚙️ Input:</i> <code>{json.dumps(s.get("tool_input", {}))}</code><br>'
                                f'<i>👁️ Observation:</i> <pre style="white-space: pre-wrap; font-size: 0.8rem;">{s.get("observation", "")}</pre>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

                # Citations
                citations = resp.get("citations", [])
                if citations:
                    with st.expander(f"🔍 Verified Sources ({len(citations)})", expanded=False):
                        for cit in citations:
                            st.markdown(
                                f'<div class="citation-card">'
                                f'<b>📄 {cit.get("filename")}</b> — <i>{cit.get("section")}</i> (Page {cit.get("page")})<br>'
                                f'<small><code>chunk_id: {cit.get("chunk_id")}</code></small>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

                # Metrics Summary
                with st.expander("📊 Performance & Cost Metrics", expanded=False):
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("⏱️ Total Latency", f"{t.get('total_latency_seconds', 0):.2f} s")
                    m2.metric("🤖 LLM Calls", t.get("total_llm_calls", 0))
                    m3.metric("🛠️ Tool Calls", t.get("total_tool_calls", 0))
                    total_toks = t.get("estimated_prompt_tokens", 0) + t.get("estimated_completion_tokens", 0)
                    m4.metric("🪙 Estimated Tokens", total_toks)

    # Input Box
    user_query = st.chat_input("Ask a technical documentation question...")
    if triggered_query:
        user_query = triggered_query

    if user_query:
        st.session_state.messages.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)

        with st.chat_message("assistant"):
            if "Race" in exec_mode:
                st.markdown("### 🏁 Head-to-Head Race: Agent vs Fixed Workflow")
                col_wf, col_ag = st.columns(2)

                with col_wf:
                    st.markdown("#### ⚡ Fixed Workflow")
                    with st.spinner("Running deterministic workflow..."):
                        wf_trace = run_fixed_workflow(
                            question=user_query,
                            document_id=selected_document_id,
                        )
                    wf_ans = wf_trace.final_response.answer if wf_trace.final_response else "No answer"
                    st.markdown(wf_ans)
                    
                    wm1, wm2, wm3 = st.columns(3)
                    wm1.metric("⏱️ Latency", f"{wf_trace.total_latency_seconds:.2f}s")
                    wm2.metric("🛠️ Tool Calls", wf_trace.total_tool_calls)
                    wm3.metric("🤖 LLM Calls", wf_trace.total_llm_calls)

                with col_ag:
                    st.markdown("#### 🤖 Autonomous Agent")
                    step_container = st.empty()
                    live_steps = []

                    def on_step_race(step: AgentStep):
                        live_steps.append(step)
                        with step_container.container():
                            st.caption(f"✓ Step {step.step_number}: `{step.tool_name}` ({step.duration_ms:.0f}ms)")

                    with st.spinner("Agent planning and executing loop..."):
                        ag_trace = run_agent(
                            question=user_query,
                            document_id=selected_document_id,
                            max_steps=max_steps,
                            max_time_seconds=max_time,
                            step_callback=on_step_race,
                        )
                    ag_ans = ag_trace.final_response.answer if ag_trace.final_response else "No answer"
                    st.markdown(ag_ans)

                    am1, am2, am3 = st.columns(3)
                    am1.metric("⏱️ Latency", f"{ag_trace.total_latency_seconds:.2f}s")
                    am2.metric("🛠️ Tool Calls", ag_trace.total_tool_calls)
                    am3.metric("🤖 LLM Calls", ag_trace.total_llm_calls)

                # Persist Agent result to state
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"**[Race Comparison Completed]**\n\n**Agent Answer:**\n{ag_ans}\n\n---\n**Fixed Workflow Answer:**\n{wf_ans}",
                    "trace": ag_trace.model_dump(),
                })

            elif "Fixed" in exec_mode:
                with st.spinner("Running fixed workflow pipeline..."):
                    trace = run_fixed_workflow(
                        question=user_query,
                        document_id=selected_document_id,
                    )
                ans = trace.final_response.answer if trace.final_response else "No answer generated."
                st.markdown(ans)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": ans,
                    "trace": trace.model_dump(),
                })
                st.rerun()

            else:  # Autonomous Agent Mode
                step_placeholder = st.container()
                live_steps = []

                def on_step(step: AgentStep):
                    live_steps.append(step)
                    with step_placeholder:
                        st.markdown(
                            f'<div class="step-card">'
                            f'<b>Step {step.step_number} — Tool: <code>{step.tool_name}</code></b> ({step.duration_ms:.0f}ms)<br>'
                            f'<i>💭 Thought:</i> {step.thought}<br>'
                            f'<i>⚙️ Input:</i> <code>{json.dumps(step.tool_input)}</code>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                with st.spinner("🤖 Agent investigating documentation in ReAct loop..."):
                    trace = run_agent(
                        question=user_query,
                        document_id=selected_document_id,
                        max_steps=max_steps,
                        max_time_seconds=max_time,
                        step_callback=on_step,
                    )

                ans = trace.final_response.answer if trace.final_response else "No answer generated."
                st.markdown(ans)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": ans,
                    "trace": trace.model_dump(),
                })
                st.rerun()


# ----------------- TAB 2: RACE BENCHMARK & COMPARISON -----------------
with tab_race_benchmark:
    st.markdown("## 🏁 Week 7 Evaluation: Agent vs. Fixed Workflow")
    st.markdown(
        """
        In Week 7, we evaluate when an **Autonomous Agent** (dynamic planning loop) is superior 
        vs. when a **Fixed Workflow** (predetermined sequence) is the right choice for production.
        """
    )

    race_file = Path(__file__).resolve().parent.parent / "data" / "race_results.json"
    
    col_run_bench, col_bench_info = st.columns([1, 3])
    with col_run_bench:
        if st.button("🚀 Run Full 10-Task Benchmark", type="primary", use_container_width=True):
            with st.status("Executing 10 Benchmark Tasks across both pipelines...", expanded=True) as status:
                from race_agent_vs_workflow import run_race
                summary = run_race()
                status.update(label="✓ Benchmark completed successfully!", state="complete")
                time.sleep(1)
                st.rerun()

    if race_file.exists():
        with open(race_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        st.markdown("### 📊 Head-to-Head Summary Metrics")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("⚡ Avg Workflow Latency", f"{data['workflow']['avg_latency_sec']}s", delta=f"-{(data['agent']['avg_latency_sec'] - data['workflow']['avg_latency_sec']):.2f}s vs Agent")
        c2.metric("🤖 Avg Agent Latency", f"{data['agent']['avg_latency_sec']}s")
        c3.metric("🪙 Workflow Avg Tokens", f"{data['workflow']['avg_total_tokens']:.0f}")
        c4.metric("🪙 Agent Avg Tokens", f"{data['agent']['avg_total_tokens']:.0f}")

        st.markdown("### 📈 Single-Hop vs Multi-Hop Query Breakdown")
        bd = data.get("breakdown", {})
        if bd:
            col_sh, col_mh = st.columns(2)
            with col_sh:
                st.markdown("#### 🎯 Single-Hop Tasks (Predictable)")
                st.info(
                    f"• **Workflow Latency:** `{bd['single_hop']['wf_avg_latency']}s`  \n"
                    f"• **Agent Latency:** `{bd['single_hop']['ag_avg_latency']}s`  \n"
                    f"• **Workflow Topic Match:** `{bd['single_hop']['wf_avg_coverage']*100:.0f}%`  \n"
                    f"• **Agent Topic Match:** `{bd['single_hop']['ag_avg_coverage']*100:.0f}%`  \n\n"
                    "👉 **Verdict:** *Fixed Workflow wins.* Much faster and cheaper with identical accuracy."
                )
            with col_mh:
                st.markdown("#### 🧠 Multi-Hop / Comparative Tasks (Adaptive)")
                st.success(
                    f"• **Workflow Latency:** `{bd['multi_hop']['wf_avg_latency']}s`  \n"
                    f"• **Agent Latency:** `{bd['multi_hop']['ag_avg_latency']}s`  \n"
                    f"• **Workflow Topic Match:** `{bd['multi_hop']['wf_avg_coverage']*100:.0f}%`  \n"
                    f"• **Agent Topic Match:** `{bd['multi_hop']['ag_avg_coverage']*100:.0f}%`  \n\n"
                    "👉 **Verdict:** *Agent wins on completeness.* Adapts queries and drills down into related sections."
                )

        st.markdown("### 📋 Detailed Benchmark Task Log")
        for r in data.get("results", []):
            with st.expander(f"Task {r['id']} ({r['category'].upper()}): {r['question'][:75]}...", expanded=False):
                st.markdown(f"**Full Question:** {r['question']}")
                col_wf_card, col_ag_card = st.columns(2)
                with col_wf_card:
                    st.markdown("##### ⚡ Fixed Workflow")
                    st.write(f"• **Latency:** `{r['workflow']['latency_sec']}s` | **Steps:** `{r['workflow']['steps']}` | **LLM calls:** `{r['workflow']['llm_calls']}`")
                    st.write(f"• **Tokens:** `{r['workflow']['total_tokens']}` | **Topic Match:** `{r['workflow']['topic_coverage']*100:.0f}%`")
                    st.caption(r['workflow']['answer_snippet'])
                with col_ag_card:
                    st.markdown("##### 🤖 Autonomous Agent")
                    st.write(f"• **Latency:** `{r['agent']['latency_sec']}s` | **Steps:** `{r['agent']['steps']}` | **Tool calls:** `{r['agent']['tool_calls']}`")
                    st.write(f"• **Tokens:** `{r['agent']['total_tokens']}` | **Topic Match:** `{r['agent']['topic_coverage']*100:.0f}%`")
                    st.caption(r['agent']['answer_snippet'])
    else:
        st.info("Click **Run Full 10-Task Benchmark** above to run the evaluation suite and generate the comparison dataset.")


# ----------------- TAB 3: DOCUMENT CHUNKS EXPLORER -----------------
with tab_chunks:
    st.markdown("### 🔍 Document Chunks & Vector Store Explorer")
    if not indexed_docs:
        st.info("No documents indexed. Upload files or click Seed Docs.")
    else:
        sel_doc_chunk = st.selectbox(
            "Select document to inspect:",
            options=[d.filename for d in indexed_docs],
            key="tab_chunks_doc_selector",
        )
        target_doc = next((d for d in indexed_docs if d.filename == sel_doc_chunk), None)
        if target_doc:
            chunks = get_document_chunks(target_doc.document_id)
            st.caption(f"Showing **{len(chunks)} chunks** for `{target_doc.filename}`")
            for c in chunks:
                sec_title = f" | Section: *{c['section']}*" if c.get("section") else ""
                st.markdown(f"**Chunk ID:** `...{c['chunk_id'][-12:]}` (Page {c['page']}{sec_title})")
                st.code(c["text"], language="markdown")
