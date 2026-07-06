#!/usr/bin/env python
"""data_copilot CLI.

Subcommands:
  health   — check the configured LLM endpoint(s) are reachable.
  ingest   — copy/convert a dataset into the module data/ dir (for editable
             tables + analysis).
  datasets — list datasets ingested into the module data/ dir.
  profile  — print a dataset profile as JSON.
  run      — start the LangGraph analysis loop; stops at the human-review
             interrupt and persists the checkpoint.
  resume   — reopen a `run`'s checkpoint with the human's feedback and drive
             the graph to the next interrupt (or to completion).
  audit    — print recent audit-trail events.

The graph (state/kernel/gates/report_generator/prompts/nodes/graph) is a clean
reimplementation of .reference/data-agent/langgraph_agent.
"""

from __future__ import annotations

import argparse
import csv as _csv
import json
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit  # type: ignore[import-not-found]
import charts as charts_mod  # type: ignore[import-not-found]
import ingest as ingest_mod  # type: ignore[import-not-found]
import paths as paths_mod  # type: ignore[import-not-found]
import profile as profile_mod  # type: ignore[import-not-found]
from client import RoleClient  # type: ignore[import-not-found]
from config import load_config  # type: ignore[import-not-found]


def _infer_type(values: List[str]) -> str:
    """Return ``number`` if every non-empty value parses as float, else ``string``."""
    saw = False
    for v in values:
        if v is None or v == "":
            continue
        saw = True
        try:
            float(v)
        except (TypeError, ValueError):
            return "string"
    return "number" if saw else "string"


def _load_result_table(out_dir: str):
    """Read ``result.csv`` from *out_dir* → ``(columns, rows)`` or ``None``.

    ``columns`` is ``[{"name", "type"}]``; numeric cells are coerced to float so
    the chart renderer plots numbers rather than strings.
    """
    path = Path(out_dir) / "result.csv"
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = list(_csv.reader(fh))
    if not reader:
        return None
    header = [h.strip() or f"column_{i + 1}" for i, h in enumerate(reader[0])]
    body = reader[1:]
    rows: List[dict] = [
        {header[i]: (r[i] if i < len(r) else "") for i in range(len(header))} for r in body
    ]
    columns: List[dict] = []
    for name in header:
        col_vals = [r.get(name, "") for r in rows]
        columns.append({"name": name, "type": _infer_type(col_vals)})
    for col in columns:
        if col["type"] == "number":
            for r in rows:
                try:
                    r[col["name"]] = float(r[col["name"]])
                except (TypeError, ValueError):
                    r[col["name"]] = None
    return columns, rows


def _cmd_health() -> int:
    rc = RoleClient(load_config())
    try:
        rc.chat("codegen", [{"role": "user", "content": "ping"}], max_tokens=1)
        print(json.dumps({"codegen": "ok"}, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 - health must never raise
        print(json.dumps({"codegen": f"error: {exc}"}, indent=2))
        return 1


def _cmd_ingest(source: Optional[str], name: Optional[str]) -> int:
    if not source:
        print(
            json.dumps(
                {
                    "error": "no source given: pass a file path as the first argument, "
                    'e.g. `ingest "<path>"` (or `--csv <path>`).'
                },
                indent=2,
            )
        )
        return 1
    try:
        result = ingest_mod.ingest(source, name)
    except FileNotFoundError as exc:
        # ModuleNotFound is a FileNotFoundError whose str is just the module name;
        # label it so the failure is legible rather than a bare "data_copilot".
        msg = f"module not found: {exc}" if type(exc).__name__ == "ModuleNotFound" else str(exc)
        print(json.dumps({"error": msg}, indent=2))
        return 1
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


def _cmd_datasets() -> int:
    print(json.dumps({"datasets": ingest_mod.list_datasets()}, indent=2, default=str))
    return 0


def _cmd_profile(dataset: str) -> int:
    try:
        path = ingest_mod.resolve_dataset(dataset)
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1
    print(json.dumps(profile_mod.profile_dataset(path), indent=2, default=str))
    return 0


def _cmd_audit(limit: int) -> int:
    events = audit.read_events()
    if limit and limit > 0:
        events = events[-limit:]
    print(json.dumps({"events": events}, indent=2, default=str))
    return 0


def _new_thread_id(out_dir: str) -> str:
    """Stable thread id derived from the run dir name (unique per run)."""
    return Path(out_dir).name


def run_graph(
    dataset: str,
    question: str,
    *,
    out_dir: str,
    domain: Optional[str],
    k: Optional[int],
    thread_id: str,
    resume_feedback: Optional[str] = None,
) -> Dict[str, Any]:
    """Start or resume the compiled LangGraph against a durable checkpoint.

    Args:
        dataset: Resolved (absolute) dataset path.
        question: The natural-language task (``user_task``).
        out_dir: Run directory — the kernel's cwd and where figures land.
        domain: Optional domain hint threaded into semantic verification.
        k: Optional fixed cluster count threaded into state (unused by the
            core graph nodes; kept for parity with the persona pipeline).
        thread_id: LangGraph checkpoint thread id (stable per run).
        resume_feedback: ``None`` to start a fresh run; otherwise the human's
            reply to the pending plan-review interrupt.

    Returns:
        ``{"status": "awaiting_review", "thread_id", "plan"}`` when the graph
        pauses at the human-review interrupt, otherwise the final summary
        ``{"status": "done", "thread_id", "dataset", "question", "run_dir",
        "report", "verdict", "figures", "result_table", "suggestions"}``.
        ``run_dir`` is the session-root-relative form (``runs/<name>``) expected
        by ``send_report``/``read_report``. The report is also persisted to
        ``<out_dir>/report.md`` on a best-effort basis. ``result_table`` is the
        absolute path to ``<out_dir>/result.csv`` (or ``None`` if the generated
        code did not write one); ``suggestions`` are heuristic chart specs
        derived from it (empty list when there is no result table). Both are
        also persisted to ``<out_dir>/result.meta.json`` alongside the columns.
    """
    from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore[import-not-found]
    from langgraph.types import Command  # type: ignore[import-not-found]

    import graph as graph_mod  # type: ignore[import-not-found]
    import kernel as kernel_mod  # type: ignore[import-not-found]

    dataset = str(Path(dataset).resolve())
    prof = profile_mod.profile_dataset(dataset)
    rc = RoleClient(load_config())
    krn = kernel_mod.CodeKernel(out_dir)
    ctx = types.SimpleNamespace(
        rc=rc, kernel=krn, profile=prof, dataset=dataset, domain=domain, k=k
    )
    cfg = {"configurable": {"thread_id": thread_id}}
    checkpoint_db = paths_mod.checkpoint_db()
    checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
    try:
        with SqliteSaver.from_conn_string(str(checkpoint_db)) as saver:
            compiled = graph_mod.build_graph(ctx, saver)
            if resume_feedback is None:
                init = {
                    "user_task": question,
                    "dataset": dataset,
                    "run_dir": out_dir,
                    "domain": domain,
                    "k": k,
                    "executed_cells": [],
                    "review_history": [],
                    "syntax_attempts": 0,
                    "semantic_attempts": 0,
                }
                stream = compiled.stream(init, config=cfg)
            else:
                prior = compiled.get_state(cfg).values.get("executed_cells", [])
                krn.replay(prior)
                stream = compiled.stream(Command(resume=resume_feedback), config=cfg)
            interrupted = None
            for step in stream:
                if "__interrupt__" in step:
                    interrupted = step["__interrupt__"][0].value
            snap = compiled.get_state(cfg)
            if interrupted:
                return {
                    "status": "awaiting_review",
                    "thread_id": thread_id,
                    "plan": interrupted.get("plan", ""),
                }
            vals = snap.values
            report = vals.get("final_report", "")
            try:
                (Path(out_dir) / "report.md").write_text(report, encoding="utf-8")
            except OSError:
                # Persisting the report is best-effort: a write failure (e.g. a
                # read-only or vanished run dir) must not fail an otherwise
                # successful run — the report is still returned in the payload.
                pass
            loaded = _load_result_table(out_dir)
            result_table = None
            suggestions: list = []
            if loaded is not None:
                columns, rows = loaded
                suggestions = charts_mod.detect_suggestions(columns, rows)
                (Path(out_dir) / "result.meta.json").write_text(
                    json.dumps({"columns": columns, "suggestions": suggestions}, default=str),
                    encoding="utf-8",
                )
                result_table = str((Path(out_dir) / "result.csv").resolve())
            return {
                "status": "done",
                "thread_id": thread_id,
                "dataset": dataset,
                "question": question,
                "run_dir": f"runs/{Path(out_dir).name}",
                "report": report,
                "verdict": vals.get("verdict", {}),
                "figures": vals.get("figures", []),
                "result_table": result_table,
                "suggestions": suggestions,
            }
    finally:
        krn.shutdown()


def _resume_context(thread_id: str) -> Dict[str, Any]:
    """Read the persisted ``dataset``/``run_dir``/``domain``/``k``/``user_task``.

    Only reads the checkpoint (no kernel/LLM stood up) so ``resume`` can accept
    just ``--thread``/``--feedback`` and rebuild the rest from what ``run``
    stored in the initial state.

    Raises:
        ValueError: No checkpoint exists for ``thread_id``.
    """
    from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore[import-not-found]

    import graph as graph_mod  # type: ignore[import-not-found]

    cfg = {"configurable": {"thread_id": thread_id}}
    placeholder_ctx = types.SimpleNamespace(rc=None, kernel=None, domain=None)
    with SqliteSaver.from_conn_string(str(paths_mod.checkpoint_db())) as saver:
        compiled = graph_mod.build_graph(placeholder_ctx, saver)
        snap = compiled.get_state(cfg)
    if not snap.values or "dataset" not in snap.values:
        raise ValueError(f"no checkpointed run found for thread {thread_id!r}")
    return snap.values


def _cmd_run(
    dataset: Optional[str],
    question: Optional[str],
    out_dir: str,
    domain: Optional[str],
    k: Optional[int],
    thread_id: Optional[str],
) -> int:
    if not dataset or not str(dataset).strip():
        print(
            json.dumps(
                {"error": 'a dataset is required: run "<dataset path or name>" "<your question>"'},
                indent=2,
            )
        )
        return 1
    if not question or not question.strip():
        print(
            json.dumps(
                {"error": 'a question is required: run "<dataset path or name>" "<your question>"'},
                indent=2,
            )
        )
        return 1
    try:
        dataset = ingest_mod.resolve_dataset(dataset)
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1
    thread_id = thread_id or _new_thread_id(out_dir)
    try:
        result = run_graph(
            dataset, question, out_dir=out_dir, domain=domain, k=k, thread_id=thread_id
        )
    except Exception as exc:  # noqa: BLE001 - surface any loop/LLM failure as clean JSON
        # The caller parses stdout as JSON; an uncaught traceback (e.g. an LLM
        # rate-limit/network error) would break that contract.
        print(json.dumps({"error": f"run failed: {exc}"}, indent=2))
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


def _cmd_resume(thread_id: Optional[str], feedback: Optional[str]) -> int:
    if not thread_id or not str(thread_id).strip():
        print(
            json.dumps(
                {"error": 'a thread id is required: resume --thread <id> --feedback "<text>"'},
                indent=2,
            )
        )
        return 1
    if not feedback or not str(feedback).strip():
        print(
            json.dumps(
                {"error": 'feedback is required: resume --thread <id> --feedback "<text>"'},
                indent=2,
            )
        )
        return 1
    try:
        state = _resume_context(thread_id)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1
    try:
        result = run_graph(
            state["dataset"],
            state.get("user_task", ""),
            out_dir=state["run_dir"],
            domain=state.get("domain"),
            k=state.get("k"),
            thread_id=thread_id,
            resume_feedback=feedback,
        )
    except Exception as exc:  # noqa: BLE001 - surface any loop/LLM failure as clean JSON
        print(json.dumps({"error": f"resume failed: {exc}"}, indent=2))
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(prog="data_copilot", description="Data Copilot CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health", help="Check the configured LLM endpoint is reachable.")
    p_ing = sub.add_parser(
        "ingest",
        help="Copy/convert a dataset into the module data/ dir (for editable tables + analysis).",
    )
    # source is positional, but we also accept --csv/--file/--source as aliases and
    # leave the positional optional so a missing/misflagged source yields a clean JSON
    # error (the contract callers parse) rather than an argparse exit-2 usage dump.
    # This makes the CLI tolerant of the common agent mistake of passing a flag.
    p_ing.add_argument("source", nargs="?", default=None, help="Path to a CSV/Excel/Parquet file.")
    p_ing.add_argument(
        "--csv",
        "--file",
        "--source",
        dest="source_opt",
        default=None,
        help="Source file path (alias for the positional source).",
    )
    p_ing.add_argument(
        "--name", default=None, help="Base name for the stored CSV (default: source stem)."
    )
    sub.add_parser("datasets", help="List datasets ingested into the module data/ dir.")
    p_prof = sub.add_parser("profile", help="Print a dataset profile as JSON.")
    p_prof.add_argument("dataset")
    p_run = sub.add_parser(
        "run", help="Start the LangGraph analysis loop (stops at the human-review interrupt)."
    )
    # dataset + question are positional, but left optional at the argparse level so a
    # missing one yields a clean JSON error (the contract callers parse) rather than
    # an argparse exit-2 usage dump. Mirrors the old analyze/persona tolerance.
    p_run.add_argument("dataset", nargs="?", default=None)
    p_run.add_argument("question", nargs="?", default=None)
    p_run.add_argument("--domain", default=None, help="Optional domain pack (e.g. telecom).")
    p_run.add_argument("--k", type=int, default=None, help="Optional fixed cluster count.")
    p_run.add_argument(
        "--out", default=None, help="Run output dir (default: a fresh runs/run-<timestamp> dir)."
    )
    p_run.add_argument(
        "--thread", default=None, help="Checkpoint thread id (default: derived from --out)."
    )
    p_res = sub.add_parser(
        "resume", help="Resume a run's checkpoint with human feedback on the plan."
    )
    p_res.add_argument("--thread", default=None, help="Checkpoint thread id from `run`.")
    p_res.add_argument("--feedback", default=None, help="Human reply to the pending plan review.")
    p_aud = sub.add_parser("audit", help="Show recent audit-trail events.")
    p_aud.add_argument("--limit", type=int, default=50)
    return parser


def _default_out_dir() -> str:
    # A fresh dir per run so successive runs never overwrite each other's
    # figures/kernel workdir. Pass --out explicitly to reuse a fixed dir.
    return str(paths_mod.new_unique_run_dir())


def main(argv: Optional[list] = None) -> int:
    """CLI entry point.

    Returns:
        ``0`` on success, ``1`` on a handled failure (clean JSON error printed
        to stdout). An unknown or missing subcommand is rejected by argparse,
        which prints usage and exits with code ``2`` (the trailing ``return 2``
        is an unreachable safety net).
    """
    args = build_parser().parse_args(argv)
    if args.command == "health":
        return _cmd_health()
    if args.command == "ingest":
        return _cmd_ingest(args.source or args.source_opt, args.name)
    if args.command == "datasets":
        return _cmd_datasets()
    if args.command == "profile":
        return _cmd_profile(args.dataset)
    if args.command == "run":
        out_dir = args.out or _default_out_dir()
        return _cmd_run(args.dataset, args.question, out_dir, args.domain, args.k, args.thread)
    if args.command == "resume":
        return _cmd_resume(args.thread, args.feedback)
    if args.command == "audit":
        return _cmd_audit(args.limit)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
