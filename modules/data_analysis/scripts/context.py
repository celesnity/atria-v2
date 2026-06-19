#!/usr/bin/env python
"""Rolling-window context envelope for the agent loop.

The chat host sends the entire conversation history (every prior tool
output) to the LLM every turn. After a few SQL/chart roundtrips this
crosses 40k+ tokens and hits the context limit.

Solution: call `context.py envelope` once per turn to get a tight
JSON envelope (~1.5 kB / ~400 tokens) that contains:

  * the last K user/assistant exchanges verbatim
  * a compact catalog of every project artifact (id + question + cols)
  * a compact catalog of every project chart (id + title + kind)
  * the last K trace summaries
  * a memory block summarising older conversation turns

The host loop should replace the raw conversation history with this
envelope when feeding the next turn — anything that needs detail can
be re-fetched by id via `artifact.py show` / `sql.py run` etc.

Also exposes `conversation rollup` to physically truncate
`conversation.jsonl`: turns older than `--keep-last` are folded into a
memory.json block (one paragraph summary + retained user questions).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import workspace as ws  # noqa: E402


# ─── Token estimation ────────────────────────────────────────────────────

def _est_tokens(obj) -> int:
    """Cheap token estimate — 1 token ≈ 4 chars of UTF-8 JSON."""
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return max(1, len(s) // 4)


def _truncate_text(s: str, n: int) -> str:
    if not s or len(s) <= n:
        return s
    return s[: n - 1] + "…"


# ─── Envelope builder ────────────────────────────────────────────────────

def build_envelope(slug: str, keep_last: int, max_tokens: int) -> dict:
    proj = ws.require_project(slug)
    conv = ws.read_conversation(slug)
    datasets = ws.list_datasets(slug)
    artifacts = ws.list_artifacts(slug)
    charts = ws.list_charts(slug)
    traces = ws.list_traces(slug)

    # ── Recent dialogue (full text, but trimmed per-message).
    recent = []
    for msg in conv[-keep_last * 2:]:  # keep_last user + assistant pairs
        recent.append({
            "role": msg.get("role"),
            "content": _truncate_text(msg.get("content", ""), 400),
            "ts": msg.get("ts"),
        })

    # ── Older turns → memory block.
    older = conv[: max(0, len(conv) - keep_last * 2)]
    memory_lines: list[str] = []
    for m in older[-30:]:  # cap memory scan
        if m.get("role") == "user":
            memory_lines.append("Q: " + _truncate_text(m.get("content", ""), 120))

    # ── Catalogs (id + 1-line each — NEVER full data).
    ds_cat = [{
        "id": d["id"], "name": d["name"], "rows": d.get("rows"),
        "n_cols": len(d.get("columns", [])),
    } for d in datasets]

    art_cat = [{
        "id": a["id"],
        "title": _truncate_text(a.get("title", ""), 60),
        "question": _truncate_text(a.get("question", ""), 80),
        "row_count": a.get("row_count"),
        "cols": a.get("columns", [])[:6],
    } for a in artifacts]

    ch_cat = [{
        "id": c["id"], "title": _truncate_text(c.get("title", ""), 60),
        "kind": c.get("kind"), "artifact_id": c.get("artifact_id"),
    } for c in charts]

    tr_cat = [{
        "id": t["id"],
        "query": _truncate_text(t.get("query", ""), 100),
        "summary": _truncate_text(t.get("result_summary", ""), 140),
        "tools": t.get("tools_used", []),
    } for t in traces[-keep_last:]]

    envelope = {
        "project": {
            "slug": proj["slug"], "name": proj["name"],
            "updated_at": proj.get("updated_at"),
        },
        "memory": memory_lines,
        "catalog": {
            "datasets": ds_cat,
            "artifacts": art_cat,
            "charts": ch_cat,
        },
        "recent_traces": tr_cat,
        "recent_dialogue": recent,
        "hints": [
            "Refer to artifacts/charts by id — never re-read raw data.",
            "Use answer.py for new questions; it returns ≤ 400 bytes.",
            "Need detail? Re-fetch with artifact.py show or sql.py run --limit 10.",
        ],
        "tokens_est": 0,
    }

    # ── Token budgeting — strip from the bottom until under budget.
    while True:
        envelope["tokens_est"] = _est_tokens(envelope)
        if envelope["tokens_est"] <= max_tokens:
            break
        # Trim, in order: oldest memory line, oldest artifact, oldest dialogue.
        if envelope["memory"]:
            envelope["memory"].pop(0)
            continue
        if len(envelope["catalog"]["artifacts"]) > 5:
            envelope["catalog"]["artifacts"].pop(0)
            continue
        if len(envelope["recent_dialogue"]) > 2:
            envelope["recent_dialogue"].pop(0)
            continue
        # Last resort: truncate artifact questions further.
        for a in envelope["catalog"]["artifacts"]:
            a["question"] = _truncate_text(a.get("question", ""), 40)
            a["cols"] = a.get("cols", [])[:3]
        # One more loop attempt; if still too large, give up.
        envelope["tokens_est"] = _est_tokens(envelope)
        break

    return envelope


# ─── Conversation rollup ─────────────────────────────────────────────────

def rollup(slug: str, keep_last_pairs: int) -> dict:
    conv_path = ws.conversation_path(slug)
    if not conv_path.exists():
        return {"rolled": 0, "kept": 0}
    msgs = ws.read_conversation(slug)
    keep_n = keep_last_pairs * 2
    if len(msgs) <= keep_n:
        return {"rolled": 0, "kept": len(msgs)}

    older = msgs[:-keep_n]
    recent = msgs[-keep_n:]

    # Summarise older — pull user questions + assistant 1-liners.
    summary_lines: list[str] = []
    for m in older:
        if m.get("role") == "user":
            summary_lines.append("Q: " + _truncate_text(m.get("content", ""), 140))
        elif m.get("role") == "assistant":
            # Heuristic: only keep assistant turns that mention an artifact/chart id.
            content = m.get("content", "")
            if any(k in content for k in ("art_", "ch_", "tr_")):
                summary_lines.append("A: " + _truncate_text(content, 140))

    memory = {
        "summarised_at": ws.now(),
        "rolled_turns": len(older),
        "summary_lines": summary_lines[-50:],  # cap memory size
    }
    mem_path = conv_path.parent / "memory.jsonl"
    with mem_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(memory, ensure_ascii=False) + "\n")

    # Rewrite conversation.jsonl with only recent.
    with conv_path.open("w", encoding="utf-8") as fh:
        for m in recent:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")

    ws.touch_project(slug)
    return {"rolled": len(older), "kept": len(recent), "memory_at": str(mem_path)}


# ─── CLI ─────────────────────────────────────────────────────────────────

def cmd_envelope(args: argparse.Namespace) -> int:
    env = build_envelope(args.slug, keep_last=args.keep_last, max_tokens=args.max_tokens)
    print(json.dumps(env, ensure_ascii=False))
    return 0


def cmd_rollup(args: argparse.Namespace) -> int:
    result = rollup(args.slug, keep_last_pairs=args.keep_last)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_auto(args: argparse.Namespace) -> int:
    """Convenience: rollup if conversation > threshold, then emit envelope."""
    conv = ws.read_conversation(args.slug)
    rolled = {}
    if len(conv) > args.threshold:
        rolled = rollup(args.slug, keep_last_pairs=args.keep_last)
    env = build_envelope(args.slug, keep_last=args.keep_last, max_tokens=args.max_tokens)
    env["_rolled"] = rolled
    print(json.dumps(env, ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Rolling-window context envelope.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_env = sub.add_parser("envelope", help="emit compact context envelope as JSON")
    p_env.add_argument("--slug", required=True)
    p_env.add_argument("--keep-last", type=int, default=5,
                       help="recent user/assistant pairs to retain verbatim (default 5)")
    p_env.add_argument("--max-tokens", type=int, default=2000,
                       help="hard budget — trims oldest content until under (default 2000)")
    p_env.set_defaults(fn=cmd_envelope)

    p_ro = sub.add_parser("rollup", help="physically truncate conversation.jsonl to last N pairs")
    p_ro.add_argument("--slug", required=True)
    p_ro.add_argument("--keep-last", type=int, default=8)
    p_ro.set_defaults(fn=cmd_rollup)

    p_auto = sub.add_parser("auto", help="rollup if conversation > threshold, then emit envelope")
    p_auto.add_argument("--slug", required=True)
    p_auto.add_argument("--keep-last", type=int, default=5)
    p_auto.add_argument("--threshold", type=int, default=20,
                        help="trigger rollup if conversation has > N messages (default 20)")
    p_auto.add_argument("--max-tokens", type=int, default=2000)
    p_auto.set_defaults(fn=cmd_auto)

    args = parser.parse_args(argv[1:])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
