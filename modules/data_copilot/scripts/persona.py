"""Persona pipeline orchestrator.

Mirrors copilot.run_analysis: profile -> generate clustering code -> run in the
sandbox -> repair on execution error -> extract + verify personas -> persist
persona.json + a narrative report. All external steps are injectable so the loop
is unit-testable without an LLM or a subprocess. The loop stays dynamic (no
hard-coded control flow steering the model).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional

import audit  # type: ignore[import-not-found]
import charts as charts_mod  # type: ignore[import-not-found]
import guardrails  # type: ignore[import-not-found]
import persona_schema  # type: ignore[import-not-found]
import profile as profile_mod  # type: ignore[import-not-found]
import sandbox  # type: ignore[import-not-found]


def _load_result_table(out_dir: str):
    """Read result.csv from *out_dir* into (columns, rows) or None.

    Delegates to copilot._load_result_table to avoid duplicating the CSV/typing
    logic (DRY).
    """
    import copilot  # type: ignore[import-not-found]

    return copilot._load_result_table(out_dir)


def _gen_and_run(
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
):
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


def run_persona(
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
    domain: Optional[str] = None,
    k: Optional[int] = None,
    timeout: float = 30.0,
    max_output: int = 20000,
) -> Dict[str, object]:
    """Run the persona clustering loop and append an audit event.

    Args:
        dataset: Path to (or resolved name of) the dataset.
        question: The user's segmentation request.
        out_dir: Per-run output directory (persona.json/result.csv land here).
        max_repair: Max execution-error repair attempts.
        max_verify: Max verifier REVISE rounds.
        codegen_fn: ``(question, profile, prior_error, hypotheses) -> code``.
        verify_fn: ``(question, code, stdout, personas) -> verdict``.
        report_fn: ``(personas, question, verified) -> markdown``.
        profile_fn: dataset profiler.
        guard_fn: code guardrail screen.
        exec_fn: sandbox executor.
        domain: Optional domain pack name (threaded to audit/summary).
        k: Optional fixed cluster count (codegen_fn closes over it).
        timeout: sandbox wall-clock bound.
        max_output: sandbox output-char bound.

    Returns:
        The persona summary dict (see the plan's Interfaces block).
    """
    dataset = str(Path(dataset).resolve())
    prof = profile_fn(dataset)
    prior_error: Optional[str] = None
    hypotheses: Optional[str] = None
    verify_round = 0
    repairs = 0
    verdict: Dict[str, object] = {"status": "REVISE", "hypotheses": "", "warnings": []}
    code = ""
    result = {"status": "error", "stdout": "", "stderr": "", "figures": [], "returncode": None}
    personas: List[dict] = []
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
                "warnings": [],
            }
            unverified = True
            break
        personas = persona_schema.extract_personas(result["stdout"]) or []
        verdict = verify_fn(question, code, result["stdout"], personas)
        if verdict["status"] == "OK":
            unverified = False
            break
        verify_round += 1
        if verify_round > max_verify:
            unverified = True
            break
        hypotheses = str(verdict.get("hypotheses", ""))

    persona_json_path: Optional[str] = None
    report_md = ""
    if not unverified and personas:
        try:
            persona_schema.validate(personas)
            path = Path(out_dir) / "persona.json"
            path.write_text(json.dumps(personas, ensure_ascii=False, indent=2), encoding="utf-8")
            persona_json_path = str(path.resolve())
            report_md = report_fn(personas, question, verified=True)
        except ValueError as exc:
            unverified = True
            verdict = {
                "status": "REVISE",
                "hypotheses": f"schema invalid: {exc}",
                "warnings": verdict.get("warnings", []),
            }
    if unverified:
        report_md = (
            report_fn(personas, question, verified=False)
            if personas
            else "> ⚠️ **UNVERIFIED** — no valid persona output was produced."
        )

    result_table_path: Optional[str] = None
    suggestions: List[dict] = []
    loaded = _load_result_table(out_dir)
    if loaded is not None:
        columns, rows = loaded
        suggestions = charts_mod.detect_suggestions(columns, rows)
        (Path(out_dir) / "result.meta.json").write_text(
            json.dumps({"columns": columns, "suggestions": suggestions}, default=str),
            encoding="utf-8",
        )
        result_table_path = str((Path(out_dir) / "result.csv").resolve())

    audit.append_event(
        {
            "type": "persona",
            "dataset": dataset,
            "question": question,
            "domain": domain,
            "verified": not unverified,
            "status": result["status"],
            "repairs": repairs,
            "verify_rounds": verify_round,
            "n_personas": len(personas),
            "verdict": verdict,
            "figures": result["figures"],
        }
    )
    return {
        "dataset": dataset,
        "question": question,
        "domain": domain,
        "code": code,
        "status": result["status"],
        "verified": not unverified,
        "verdict": verdict,
        "personas": personas,
        "persona_json": persona_json_path,
        "report": report_md,
        "figures": result["figures"],
        "result_table": result_table_path,
        "suggestions": suggestions,
        "repairs": repairs,
        "verify_rounds": verify_round,
    }
