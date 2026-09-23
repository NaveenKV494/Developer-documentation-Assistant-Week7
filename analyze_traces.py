"""Create a human-review sheet for Week 5 trace analysis."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def load(path: Path):
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="traces/raw/traces.jsonl")
    p.add_argument("--output", default="traces/analysis/open_coding.md")
    args = p.parse_args()
    rows = load(Path(args.input))
    if not rows:
        raise SystemExit("No traces found. Run python run_week5_traces.py first.")
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write("# Week 5 — Open Coding Notes\n\n")
        f.write("Read every trace. Write the observation before assigning a category.\n\n")
        for i, t in enumerate(rows, 1):
            f.write(f"## Trace {i:02d} — `{t['trace_id']}`\n\n")
            f.write(f"**Question:** {t['question']}\n\n")
            f.write(f"**Retrieval:** {t['retrieval_strategy']} / Top-K {t['top_k']}\n\n")
            f.write("### Retrieved evidence\n\n")
            for r in t.get("retrieved_chunks", []):
                f.write(f"- Rank {r['rank']} | score={r.get('score')} | {r.get('source_file')} | {r.get('section')} | `{r.get('chunk_id')}`\n")
            f.write("\n### Final answer\n\n" + (t.get("answer") or "[no answer]") + "\n\n")
            f.write(f"**Grounded:** {t.get('grounded')}\n\n")
            f.write("### Open-code observation\n\n- Observation: TODO\n- Evidence: TODO\n- User impact: TODO\n\n")
            f.write("### Consolidated coding\n\n- Problem group: TODO\n- Severity (1–5): TODO\n- Correctness: TODO\n\n---\n\n")
    inv = out.parent / "trace_inventory.md"
    with inv.open("w", encoding="utf-8") as f:
        f.write("# Trace Inventory\n\n")
        f.write(f"Total traces: **{len(rows)}**\n\n")
        f.write("| # | Trace | Question | Chunks | Answer | Grounded | Error |\n|---:|---|---|---:|---|---|---|\n")
        for i, t in enumerate(rows, 1):
            f.write(f"| {i} | `{t['trace_id']}` | {t['question']} | {len(t.get('retrieved_chunks', []))} | {'yes' if t.get('answer') else 'no'} | {t.get('grounded')} | {t.get('error') or ''} |\n")
    print(f"Wrote {len(rows)} review sections to {out}")

if __name__ == "__main__":
    main()
