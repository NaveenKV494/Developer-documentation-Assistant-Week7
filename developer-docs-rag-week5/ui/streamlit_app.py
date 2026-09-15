import json
from pathlib import Path
import sys
import time

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))

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
from app.llm.generator import generate_answer
from app.llm.prompts import build_rag_prompt
from app.observability.trace import RetrievedChunkTrace, Trace, save_trace
from app.retrieval.retriever import retrieve_relevant_chunks
from app.retrieval.vector_store import get_client_mode


st.set_page_config(
    page_title="Document AI Assistant",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for rich visual styling
st.markdown(
    """
    <style>
    /* Metric & Badge styling */
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
    
    /* Citation card */
    .citation-card {
        border-left: 4px solid #3b82f6;
        background-color: rgba(59, 130, 246, 0.05);
        border-radius: 0 8px 8px 0;
        padding: 10px 14px;
        margin: 6px 0;
    }
    
    /* Scope Banner */
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
    
    /* Relevance score pill */
    .score-high { background-color: rgba(34, 197, 94, 0.15); color: #15803d; padding: 2px 8px; border-radius: 12px; font-weight: 600; font-size: 0.8rem; }
    .score-med { background-color: rgba(59, 130, 246, 0.15); color: #1d4ed8; padding: 2px 8px; border-radius: 12px; font-weight: 600; font-size: 0.8rem; }
    .score-low { background-color: rgba(249, 115, 22, 0.15); color: #c2410c; padding: 2px 8px; border-radius: 12px; font-weight: 600; font-size: 0.8rem; }
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


def get_score_badge(score: float) -> str:
    pct = max(0.0, min(100.0, score * 100))
    if score >= 0.70:
        cls_name = "score-high"
    elif score >= 0.50:
        cls_name = "score-med"
    else:
        cls_name = "score-low"
    return f'<span class="{cls_name}">{pct:.1f}% Match ({score:.3f})</span>'


# ----------------- SIDEBAR -----------------
with st.sidebar:
    st.markdown("## 📚 **Document AI**")
    
    # Connection Mode Badge
    chroma_mode = get_client_mode()
    mode_icon = {"cloud": "☁️", "http": "🌐", "local": "💾"}.get(chroma_mode, "💾")
    st.caption(f"Vector Store: **{mode_icon} {chroma_mode.upper()}** | `{CHROMA_COLLECTION_NAME}`")
    st.divider()

    # Document Upload Section
    st.markdown("### 📤 Upload Documents")
    uploaded_files = st.file_uploader(
        "Drop files here",
        type=["pdf", "docx", "md", "txt"],
        accept_multiple_files=True,
        help="Upload PDF, DOCX, Markdown, or Plain Text files.",
        label_visibility="collapsed",
    )

    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        upload_btn = st.button("⚡ Upload & Index", type="primary", use_container_width=True)
    with col_btn2:
        seed_btn = st.button("🌱 Seed Samples", use_container_width=True, help="Index sample .NET MAUI docs")

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
    st.markdown(f"### 📑 Document Library ({len(indexed_docs)})")

    if not indexed_docs:
        st.info("No documents indexed yet. Upload a file above or click **Seed Samples**.")
    else:
        for doc in indexed_docs:
            with st.container():
                col_info, col_act = st.columns([5, 1])
                with col_info:
                    st.markdown(
                        f"{get_badge_html(doc.file_type)} **{doc.filename}**  \n"
                        f"<small style='opacity:0.75;'>{format_bytes(doc.file_size)} · {doc.chunk_count} chunks · ID: <code>{doc.document_id}</code></small>",
                        unsafe_allow_html=True,
                    )
                with col_act:
                    if st.button("🗑️", key=f"del_{doc.document_id}", help=f"Delete {doc.filename}"):
                        delete_document(doc.document_id)
                        st.toast(f"Deleted {doc.filename}")
                        st.rerun()

        # Document Inspector Drawer
        with st.expander("🔍 Inspect Document Chunks", expanded=False):
            doc_to_inspect = st.selectbox(
                "Select document to preview chunks:",
                options=[d.filename for d in indexed_docs],
                key="inspect_doc_selector",
            )
            target_doc = next((d for d in indexed_docs if d.filename == doc_to_inspect), None)
            if target_doc:
                chunks = get_document_chunks(target_doc.document_id)
                st.caption(f"Showing **{len(chunks)} chunks** for `{target_doc.filename}`")
                for c in chunks[:5]:
                    sec_text = f" | *{c['section']}*" if c.get('section') else ""
                    st.markdown(f"**Chunk {c['chunk_index']}** (Page {c['page']}{sec_text}):")
                    st.code(c["text"][:300] + ("..." if len(c["text"]) > 300 else ""), language="markdown")
                if len(chunks) > 5:
                    st.caption(f"... and {len(chunks) - 5} more chunks.")

    st.divider()

    # Retrieval & Pipeline Settings
    st.markdown("### ⚙️ Retrieval Settings")
    strategy = st.selectbox("Chunking Strategy", ["structure", "baseline"], index=0)
    top_k = st.slider("Top-K Retrieved Chunks", min_value=1, max_value=12, value=min(DEFAULT_TOP_K, 12))
    
    with st.expander("🛠️ Advanced Maintenance", expanded=False):
        st.caption(f"Active collection: `{CHROMA_COLLECTION_NAME}`")
        if st.button("⚠️ Clear All Documents", type="secondary", use_container_width=True):
            cleared = clear_all_documents()
            st.toast(f"Cleared {cleared} documents and wiped index.")
            st.rerun()


# ----------------- MAIN VIEW -----------------
col_title, col_ctrl = st.columns([4, 1])
with col_title:
    st.title("📚 Document AI Assistant")
    st.caption("Ask questions strictly grounded in your multi-format documentation with verified citations.")
with col_ctrl:
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# Document Selector (Multi-Doc vs Single-Doc Isolation)
doc_options = ["🌐 All Documents (Global Search)"]
doc_mapping: dict[str, str | None] = {"🌐 All Documents (Global Search)": None}

for d in indexed_docs:
    label = f"📄 {d.filename} ({d.file_type.upper()})"
    doc_options.append(label)
    doc_mapping[label] = d.document_id

col_scope_sel, col_scope_info = st.columns([2, 3])
with col_scope_sel:
    selected_scope_label = st.selectbox(
        "Search Scope",
        options=doc_options,
        index=0,
        help="Choose 'All Documents' to query across all files, or isolate query to a specific document.",
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

# Suggested Questions Pills
if indexed_docs:
    st.markdown("<small style='opacity:0.8;'>💡 <b>Suggested Questions:</b></small>", unsafe_allow_html=True)
    suggested_cols = st.columns(4)
    preset_questions = [
        "What are the app lifecycle states?",
        "How is dependency injection registered?",
        "What are the Grid column properties?",
        "What is the annual leave entitlement?",
    ]
    triggered_question = None
    for idx, q in enumerate(preset_questions):
        with suggested_cols[idx % 4]:
            if st.button(f"📌 {q}", key=f"sugg_{idx}", use_container_width=True):
                triggered_question = q

# Chat history initialization
if "messages" not in st.session_state:
    st.session_state.messages = []

# Render past chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        if message["role"] == "assistant":
            # Groundedness Badge
            if message.get("grounded") is True:
                st.markdown(
                    '<div class="status-grounded">🟢 Grounded in Documentation (Verified)</div>',
                    unsafe_allow_html=True,
                )
            elif message.get("grounded") is False:
                st.markdown(
                    '<div class="status-ungrounded">🟡 Refusal / Insufficient Evidence in Context</div>',
                    unsafe_allow_html=True,
                )

            # Verified Citations Cards
            if message.get("citations"):
                with st.expander("🔍 Verified Sources & Citations", expanded=True):
                    for cit in message["citations"]:
                        fn = cit.get("filename") or cit.get("source_file", "document")
                        sec = cit.get("section") or "General"
                        pg = cit.get("page") or cit.get("page_id") or "1"
                        cid = cit.get("chunk_id", "")
                        st.markdown(
                            f'<div class="citation-card">'
                            f'<b>📄 {fn}</b> — <i>{sec}</i> (Page {pg})<br>'
                            f'<small><code>chunk_id: {cid}</code></small>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

            # Retrieved Chunks & Scores
            if message.get("retrieved_chunks"):
                with st.expander("🔎 Retrieved Chunks & Similarity Breakdown", expanded=False):
                    for rank, chunk in enumerate(message["retrieved_chunks"], 1):
                        score = chunk.get("score", 0.0)
                        fn = chunk.get("filename") or chunk.get("source_file", "doc")
                        sec = chunk.get("section") or "Section"
                        pg = chunk.get("page") or 1
                        st.markdown(
                            f"**{rank}. {fn}** (Page {pg}, *{sec}*) · {get_score_badge(score)}",
                            unsafe_allow_html=True,
                        )
                        st.code(chunk.get("text", "")[:400] + ("..." if len(chunk.get("text", "")) > 400 else ""), language="markdown")

            # Observability & Trace Details
            if message.get("trace"):
                trace_data = message["trace"]
                with st.expander("📊 Observability & Trace Details", expanded=False):
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("⏱️ Latency", f"{trace_data.get('latency_ms', 0):.0f} ms")
                    m2.metric("📄 Chunks Retrieved", len(trace_data.get("retrieved_chunks", [])))
                    m3.metric("🎯 Scope", "Isolated" if trace_data.get("document_ids") else "Global")
                    m4.metric("🤖 Model", GENERATION_MODEL)
                    
                    st.download_button(
                        label="📥 Download Trace JSON",
                        data=json.dumps(trace_data, indent=2),
                        file_name=f"trace_{trace_data.get('trace_id', 'unknown')}.json",
                        mime="application/json",
                        key=f"dl_{trace_data.get('trace_id')}",
                    )

# Input handling (from chat_input or suggested button)
user_query = st.chat_input("Ask a question about your indexed documents...")
if triggered_question:
    user_query = triggered_question

if user_query:
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        with st.spinner("Searching documents and generating verified answer..."):
            target_doc_names = [selected_scope_label] if selected_document_id else [d.filename for d in indexed_docs]
            target_doc_ids = [selected_document_id] if selected_document_id else []

            # Create enhanced trace
            trace = Trace.new(
                question=user_query,
                strategy=strategy,
                top_k=top_k,
                document_ids=target_doc_ids,
                document_names=target_doc_names,
                retrieval_query=user_query,
            )

            try:
                # Retrieve relevant chunks with isolation
                retrieved_docs = retrieve_relevant_chunks(
                    query=user_query,
                    n_results=top_k,
                    strategy=strategy,
                    document_id=selected_document_id,
                )

                trace.retrieval_scores = [round(float(doc.get("score", 0.0)), 4) for doc in retrieved_docs]
                for rank, doc in enumerate(retrieved_docs, 1):
                    trace.retrieved_chunks.append(
                        RetrievedChunkTrace(
                            rank=rank,
                            score=doc.get("score"),
                            distance=doc.get("distance"),
                            chunk_id=doc.get("chunk_id"),
                            document_id=doc.get("document_id"),
                            filename=doc.get("filename"),
                            source_file=doc.get("source_file"),
                            page=doc.get("page"),
                            page_id=doc.get("page_id"),
                            section=doc.get("section"),
                            sdk_version=doc.get("sdk_version"),
                            page_type=doc.get("page_type"),
                            text=doc.get("text", ""),
                        )
                    )

                prompt = build_rag_prompt(user_query, retrieved_docs)
                result = generate_answer(prompt)

                trace.generation_model = GENERATION_MODEL
                trace.answer = result.answer
                trace.grounded = result.grounded
                trace.citations = [c.model_dump() for c in result.citations]

            except Exception as exc:
                trace.set_error(f"{type(exc).__name__}: {exc}")
                save_trace(trace)
                st.error(f"Error answering question: {exc}")
                raise

            finally:
                save_trace(trace)

        # Render Assistant Answer
        st.markdown(result.answer)

        # Grounded badge
        if result.grounded:
            st.markdown(
                '<div class="status-grounded">🟢 Grounded in Documentation (Verified)</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="status-ungrounded">🟡 Refusal / Insufficient Evidence in Context</div>',
                unsafe_allow_html=True,
            )

        # Citations Cards
        citations = [c.model_dump() for c in result.citations]
        if citations:
            with st.expander("🔍 Verified Sources & Citations", expanded=True):
                for cit in citations:
                    fn = cit.get("filename") or cit.get("source_file", "document")
                    sec = cit.get("section") or "General"
                    pg = cit.get("page") or cit.get("page_id") or "1"
                    cid = cit.get("chunk_id", "")
                    st.markdown(
                        f'<div class="citation-card">'
                        f'<b>📄 {fn}</b> — <i>{sec}</i> (Page {pg})<br>'
                        f'<small><code>chunk_id: {cid}</code></small>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        # Retrieved Chunks with Score Meters
        with st.expander("🔎 Retrieved Chunks & Similarity Breakdown", expanded=False):
            if not retrieved_docs:
                st.write("No matching chunks retrieved.")
            for rank, doc in enumerate(retrieved_docs, 1):
                score = doc.get("score", 0.0)
                fn = doc.get("filename") or doc.get("source_file", "doc")
                sec = doc.get("section") or "Section"
                pg = doc.get("page") or 1
                st.markdown(
                    f"**{rank}. {fn}** (Page {pg}, *{sec}*) · {get_score_badge(score)}",
                    unsafe_allow_html=True,
                )
                st.code(doc["text"][:400] + ("..." if len(doc["text"]) > 400 else ""), language="markdown")

        # Observability & Trace Details
        with st.expander("📊 Observability & Trace Details", expanded=False):
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("⏱️ Latency", f"{trace.latency_ms:.0f} ms")
            m2.metric("📄 Chunks Retrieved", len(trace.retrieved_chunks))
            m3.metric("🎯 Scope", "Isolated" if selected_document_id else "Global")
            m4.metric("🤖 Model", GENERATION_MODEL)

            st.download_button(
                label="📥 Download Trace JSON",
                data=json.dumps(trace.to_dict(), indent=2),
                file_name=f"trace_{trace.trace_id}.json",
                mime="application/json",
                key=f"dl_live_{trace.trace_id}",
            )

    # Persist message to session state
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": result.answer,
            "grounded": result.grounded,
            "citations": citations,
            "retrieved_chunks": [
                {
                    "score": doc.get("score", 0.0),
                    "filename": doc.get("filename") or doc.get("source_file", "doc"),
                    "section": doc.get("section", ""),
                    "page": doc.get("page", 1),
                    "text": doc.get("text", ""),
                }
                for doc in retrieved_docs
            ],
            "trace": trace.to_dict(),
        }
    )
