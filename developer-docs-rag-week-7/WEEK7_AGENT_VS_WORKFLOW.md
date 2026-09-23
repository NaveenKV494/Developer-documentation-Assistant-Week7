# Week 7 · Module 4 · Agents
## Agent Loops — and When Not to Use Them
### Track E: Developer Documentation Agent vs. Fixed Workflow

---

## Executive Summary

For Week 7, we implemented and raced two distinct architectural paradigms to solve technical developer documentation investigation:
1. **Hand-Built Autonomous Agent (`app/agent/`)**: A transparent, dependency-free ReAct loop (Reason + Act + Observe) that dynamically formulates search queries, inspects document sections, evaluates evidence sufficiency, and safely stops.
2. **Deterministic Fixed Workflow (`app/workflow/`)**: A pre-orchestrated sequence (Search $\rightarrow$ Section Expansion $\rightarrow$ Single Synthesis $\rightarrow$ Citation Validation).

We evaluated both systems across a 10-task benchmark of single-hop, multi-hop, and unanswerable documentation tasks.

---

## Head-to-Head Benchmark Results

| Metric | Deterministic Fixed Workflow | Autonomous Agent (ReAct) | Winner |
| :--- | :---: | :---: | :---: |
| **Success / Completion Rate** | **100.0%** (10/10) | **100.0%** (10/10) | **Tie** |
| **Average Latency (All Tasks)** | **19.07s** (Median ~2.6s) | **22.97s** (Median ~18.6s) | ⚡ **Fixed Workflow (Faster)** |
| **Single-Hop Query Latency** | **2.71s** | **16.84s** | ⚡ **Fixed Workflow (6.2x faster)** |
| **Multi-Hop Query Topic Coverage** | 63.0% | **78.0%** | 🧠 **Agent (+15% more complete)** |
| **Average Steps per Task** | 3.0 (Fixed) | 4.3 (Dynamic) | ⚡ **Fixed Workflow** |
| **Average Tool Calls per Task** | 2.0 (Fixed) | 3.4 (Adaptive) | — |
| **Average LLM Calls per Task** | **1.0** | **5.3** | ⚡ **Fixed Workflow (5.3x fewer calls)** |
| **Average Total Tokens** | **2,783.7** | **9,519.6** | ⚡ **Fixed Workflow (3.4x cheaper)** |
| **Unanswerable Query Refusal** | **100.0%** (`grounded=false`) | **100.0%** (`grounded=false`) | **Tie** |
| **Loop Safety / Halting** | Deterministic | **100% Safe Halting** | **Tie** |

---

## Deep Dive Analysis: The Two Regimes

### 1. Where the Fixed Workflow Wins
For **predictable, single-hop developer questions** (e.g. *"What is the default number of Grid rows?"* or *"What attached properties place a view into a Grid cell?"*):
- The fixed workflow finishes in **~2.3s** using a single LLM synthesis call and ~2,000 tokens.
- The agent requires **~17.3s** and 5–7 LLM reasoning steps to formulate queries, parse results, verify completeness, and finalize the answer.
- **Outcome:** The answers are identical in quality, but the Fixed Workflow is **7x faster and 3.5x cheaper**.

### 2. Where the Autonomous Agent Excels
For **complex multi-hop, cross-concept, or exploratory questions** (e.g. *"How do you subscribe to platform-specific lifecycle events on Android and iOS using MauiAppBuilder?"* or *"Compare service lifetimes and explain stateful service registration"*):
- The fixed workflow only performs one initial static search and a single predetermined section expansion. If the initial query fails to retrieve both Android and iOS delegates, the answer is incomplete (63% coverage).
- The agent examines the first search result, discovers that Android lifecycle events are covered in one chunk while iOS events are located under a separate section, dynamically executes a second targeted search query (`"iOSLifecycle events FinishedLaunching"`), and integrates both sources.
- **Outcome:** The Agent achieves **78% topic coverage** with comprehensive cross-platform evidence and accurate chunk citations.

---

## Agent Architecture & Safety Controls

### 1. Hand-Built ReAct Loop (No Framework Black-Boxes)
```python
while True:
    allowed, reason = limits.check_step_budget()
    if not allowed:
        break

    # 1. Think & Plan
    prompt = _build_agent_prompt(question, scratchpad)
    response = llm.generate_content(prompt)
    thought, action, action_input = _parse_react_response(response)

    # 2. Act
    if action == "FINISH":
        break
    
    # 3. Observe & Update Short-Term Memory
    observation = execute_tool(action, action_input)
    scratchpad.append(step_trace)
```

### 2. Hard Safety Limits & Stopping Conditions
To prevent infinite loops and runaway costs, the agent enforces 4 distinct stopping boundaries in `app/agent/limits.py`:
1. **Step Budget Limit (`max_steps = 6`)**: Safely halts if 6 iterations elapse.
2. **Time Budget Limit (`max_time_seconds = 30.0`)**: Interrupts execution if total time exceeds 30s.
3. **Tool Call Budget (`max_tool_calls = 6`)**: Bounds total I/O retrieval operations.
4. **Loop Cycle Detection (`max_consecutive_same_actions = 2`)**: Detects and breaks repeated identical action signatures.

---

## Which One Would We Ship to Production?

### **Recommendation: Hybrid Routing Architecture (Fixed-First with Agent Escalation)**

1. **Default to Fixed Workflow (80% of Traffic)**:
   - For 80% of documentation Q&A queries, a deterministic 2-step retrieval pipeline delivers sub-3-second responses at minimal token cost.
2. **Escalate to Autonomous Agent on Low Retrieval Confidence (20% of Traffic)**:
   - When top retrieval similarity scores fall below confidence threshold ($\text{score} < 0.60$) or when multi-entity queries are detected, invoke the Autonomous Agent to adaptively investigate the documentation.
3. **Summary**:
   - Do **not** use an agent when the execution graph is static and known in advance.
   - Use an agent exclusively when the subsequent retrieval step is conditionally dependent on the dynamic evidence discovered in preceding steps.

---

## Mentor Checklist Verification

- [x] **Genuinely multi-step task**: Developer documentation Q&A requiring iterative search, section drill-down, and evidence synthesis.
- [x] **Visible steps**: Full real-time trace in Streamlit UI and JSON logs showing Step Number, Tool Name, Duration, Thought, Input, and Observation.
- [x] **Safe stopping**: Verified with hard step limits, execution timeouts, and cycle detection.
- [x] **Empirical comparison with real numbers**: 10 benchmark queries evaluated with exact latency, token counts, tool calls, and topic coverage logged in `data/race_results.json`.
- [x] **Production shipping decision**: Documented above with quantitative justification.
