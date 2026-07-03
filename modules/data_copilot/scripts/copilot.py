#!/usr/bin/env python
"""data_copilot CLI.

Subcommands:
  health   — check the configured LLM endpoint(s) are reachable.
  ingest   — copy/convert a dataset into the module data/ dir (for editable
             tables + analysis).
  datasets — list datasets ingested into the module data/ dir.
  profile  — print a dataset profile as JSON.
  analyze  — run the full generate → execute → repair → verify → report loop.
  audit    — print recent audit-trail events.

The loop is a clean reimplementation of .reference/data-agent/langgraph_agent.
"""

from __future__ import annotations

import argparse
import csv as _csv
import json
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit  # type: ignore[import-not-found]
import charts as charts_mod  # type: ignore[import-not-found]
import generate  # type: ignore[import-not-found]
import ingest as ingest_mod  # type: ignore[import-not-found]
import guardrails  # type: ignore[import-not-found]
import paths as paths_mod  # type: ignore[import-not-found]
import profile as profile_mod  # type: ignore[import-not-found]
import report as report_mod  # type: ignore[import-not-found]
import sandbox  # type: ignore[import-not-found]
import verify as verify_mod  # type: ignore[import-not-found]
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


def _gen_and_run(
    question: str,
    prof: dict,
    out_dir: str,
    codegen_fn: Callable,
    guard_fn: Callable,
    exec_fn: Callable,
    prior_error: Optional[str],
    hypotheses: Optional[str],
    timeout: float,
    max_output: int,
) -> tuple[str, Dict[str, object]]:
    """Generate code, screen it, and (if allowed) execute it once."""
    code = codegen_fn(question, prof, prior_error, hypotheses)
    guard = guard_fn(code)
    if not guard["allowed"]:
        return code, {
            "status": "error",
            "stdout": "",
            "stderr": "GUARDRAIL: " + "; ".join(guard["reasons"]),
            "figures": [],
            "returncode": None,
        }
    return code, exec_fn(code, out_dir, timeout, max_output)


def run_analysis(
    dataset: str,
    question: str,
    *,
    out_dir: str,
    max_repair: int,
    max_verify: int,
    codegen_fn: Callable,
    verify_fn: Callable,
    report_fn: Callable,
    profile_fn: Callable = profile_mod.profile_dataset,
    guard_fn: Callable = guardrails.check_code,
    exec_fn: Callable = sandbox.run_code,
    timeout: float = 30.0,
    max_output: int = 20000,
) -> Dict[str, object]:
    """Run the full analysis loop and append an audit event.

    Args:
        dataset: Path to the dataset.
        question: Natural-language question.
        out_dir: Directory for the run (code + figures).
        max_repair: Max execution-error repair attempts.
        max_verify: Max semantic-revision rounds.
        codegen_fn: ``(question, profile, prior_error, hypotheses) -> code``.
        verify_fn: ``(question, code, output) -> {"status","hypotheses"}``.
        report_fn: ``(question, output, figures, verified=) -> markdown``.
        profile_fn, guard_fn, exec_fn: injectable dependencies (defaults wired
            to the module functions).
        timeout, max_output: sandbox bounds.

    Returns:
        A summary dict (see Interfaces block in the plan).
    """
    # Resolve to an absolute path: the sandbox runs generated code with cwd set
    # to out_dir, so a relative dataset path would not resolve at execution time.
    dataset = str(Path(dataset).resolve())
    prof = profile_fn(dataset)
    prior_error: Optional[str] = None
    hypotheses: Optional[str] = None
    verify_round = 0
    repairs = 0
    verdict = {"status": "REVISE", "hypotheses": ""}
    code = ""
    result = {"status": "error", "stdout": "", "stderr": "", "figures": [], "returncode": None}
    unverified = True

    while True:
        code, result = _gen_and_run(
            question,
            prof,
            out_dir,
            codegen_fn,
            guard_fn,
            exec_fn,
            prior_error,
            hypotheses,
            timeout,
            max_output,
        )
        prior_error = None
        hypotheses = None
        while result["status"] == "error" and repairs < max_repair:
            repairs += 1
            code, result = _gen_and_run(
                question,
                prof,
                out_dir,
                codegen_fn,
                guard_fn,
                exec_fn,
                result["stderr"],
                None,
                timeout,
                max_output,
            )
        if result["status"] == "error":
            verdict = {
                "status": "REVISE",
                "hypotheses": "code could not be made to run: " + result["stderr"],
            }
            unverified = True
            break
        verdict = verify_fn(question, code, result["stdout"])
        if verdict["status"] == "OK":
            unverified = False
            break
        verify_round += 1
        if verify_round > max_verify:
            unverified = True
            break
        hypotheses = verdict["hypotheses"]

    report_output = result["stdout"]
    if result["status"] == "error":
        report_output = (result["stdout"] + "\n\n[execution error]\n" + result["stderr"]).strip()
    report_md = report_fn(question, report_output, result["figures"], verified=not unverified)

    # Persist the result table (if the generated code wrote result.csv) and derive
    # heuristic chart suggestions so the agent can push an interactive table/chart.
    result_table_path: Optional[str] = None
    suggestions: List[dict] = []
    loaded = _load_result_table(out_dir)
    if loaded is not None:
        columns, rows = loaded
        suggestions = charts_mod.detect_suggestions(columns, rows)
        meta = {"columns": columns, "suggestions": suggestions}
        (Path(out_dir) / "result.meta.json").write_text(
            json.dumps(meta, default=str), encoding="utf-8"
        )
        result_table_path = str((Path(out_dir) / "result.csv").resolve())

    audit.append_event(
        {
            "type": "analyze",
            "dataset": dataset,
            "question": question,
            "verified": not unverified,
            "status": result["status"],
            "repairs": repairs,
            "verify_rounds": verify_round,
            "code": code,
            "verdict": verdict,
            "figures": result["figures"],
        }
    )
    return {
        "dataset": dataset,
        "question": question,
        "code": code,
        "status": result["status"],
        "verified": not unverified,
        "verdict": verdict,
        "figures": result["figures"],
        "report": report_md,
        "repairs": repairs,
        "verify_rounds": verify_round,
        "result_table": result_table_path,
        "suggestions": suggestions,
    }


def _role_chat(rc: RoleClient, role: str) -> Callable:
    """Return a ``messages -> text`` callable bound to *role*."""
    return lambda messages: rc.chat(role, messages)


def _cmd_health() -> int:
    rc = RoleClient(load_config())
    try:
        rc.chat("codegen", [{"role": "user", "content": "ping"}], max_tokens=1)
        print(json.dumps({"codegen": "ok"}, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 - health must never raise
        print(json.dumps({"codegen": f"error: {exc}"}, indent=2))
        return 1


def _cmd_ingest(source: str, name: Optional[str]) -> int:
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


def _cmd_analyze(
    dataset: str, question: Optional[str], out_dir: str, max_repair: int, max_verify: int
) -> int:
    if not question or not question.strip():
        print(
            json.dumps(
                {
                    "error": "a question is required: "
                    'analyze "<dataset path or name>" "<your question>"'
                },
                indent=2,
            )
        )
        return 1
    try:
        dataset = ingest_mod.resolve_dataset(dataset)
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1
    rc = RoleClient(load_config())
    summary = run_analysis(
        dataset,
        question,
        out_dir=out_dir,
        max_repair=max_repair,
        max_verify=max_verify,
        codegen_fn=lambda q, p, pe=None, hy=None: generate.generate_code(
            q, p, _role_chat(rc, "codegen"), pe, hy
        ),
        verify_fn=lambda q, c, o: verify_mod.verify(q, c, o, _role_chat(rc, "verify")),
        report_fn=lambda q, o, f, verified=True: report_mod.generate_report(
            q, o, f, _role_chat(rc, "report"), verified=verified
        ),
    )
    print(json.dumps(summary, indent=2, default=str))
    return 0


def _cmd_audit(limit: int) -> int:
    events = audit.read_events()
    if limit and limit > 0:
        events = events[-limit:]
    print(json.dumps({"events": events}, indent=2, default=str))
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
    p_ing.add_argument("source", help="Path to a CSV/Excel/Parquet file.")
    p_ing.add_argument(
        "--name", default=None, help="Base name for the stored CSV (default: source stem)."
    )
    sub.add_parser("datasets", help="List datasets ingested into the module data/ dir.")
    p_prof = sub.add_parser("profile", help="Print a dataset profile as JSON.")
    p_prof.add_argument("dataset")
    p_an = sub.add_parser("analyze", help="Run the full analysis loop.")
    p_an.add_argument("dataset")
    # Optional at the argparse level so a missing question yields a clean JSON
    # error (the contract callers parse) instead of an argparse exit-2 usage dump.
    p_an.add_argument("question", nargs="?", default=None)
    p_an.add_argument("--out", default=None, help="Run output dir (default: runs/latest).")
    p_an.add_argument("--max-repair", type=int, default=3)
    p_an.add_argument("--max-verify", type=int, default=2)
    p_aud = sub.add_parser("audit", help="Show recent audit-trail events.")
    p_aud.add_argument("--limit", type=int, default=50)
    return parser


def _default_out_dir() -> str:
    return str(paths_mod.new_run_dir())


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point.

    Returns:
        ``0`` on success, ``1`` when a health probe fails. An unknown or missing
        subcommand is rejected by argparse, which prints usage and exits with
        code ``2`` (the trailing ``return 2`` is an unreachable safety net).
    """
    args = build_parser().parse_args(argv)
    if args.command == "health":
        return _cmd_health()
    if args.command == "ingest":
        return _cmd_ingest(args.source, args.name)
    if args.command == "datasets":
        return _cmd_datasets()
    if args.command == "profile":
        return _cmd_profile(args.dataset)
    if args.command == "analyze":
        return _cmd_analyze(
            args.dataset,
            args.question,
            args.out or _default_out_dir(),
            args.max_repair,
            args.max_verify,
        )
    if args.command == "audit":
        return _cmd_audit(args.limit)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
