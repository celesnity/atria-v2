"""Offline eval harness over the Public_Evaluation fixture."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"
_ACCESS = _MOD.parent / "access"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_load_cases_reads_fixture():
    ev = _load("evaluate", "ek_eval_load")
    cases = ev.load_cases(str(_ACCESS / "public_evaluation.csv"))
    assert len(cases) >= 4
    assert cases[0]["expected_permission"] in ("Allow", "Deny")


def test_run_case_scores_permission_and_recall():
    ev = _load("evaluate", "ek_eval_run")

    # Fake query_fn: Allow-with-expected-doc returns that doc; Deny returns no hits.
    def query_fn(question, user_id):
        if user_id == "U001":
            return {"hits": [{"doc_id": "DOC007"}]}
        return {"hits": []}

    allow_case = {
        "question_id": "P010",
        "user_id": "U001",
        "expected_permission": "Allow",
        "expected_document_id": "DOC007",
        "question_vi": "?",
    }
    deny_case = {
        "question_id": "P009",
        "user_id": "U004",
        "expected_permission": "Deny",
        "expected_document_id": "DOC007",
        "question_vi": "?",
    }
    r_allow = ev.run_case(allow_case, query_fn)
    r_deny = ev.run_case(deny_case, query_fn)
    assert r_allow["permission_ok"] and r_allow["doc_recall_hit"]
    assert r_deny["permission_ok"] and not r_deny["doc_recall_hit"]


def test_summarize_counts_regressions():
    ev = _load("evaluate", "ek_eval_sum")
    results = [
        {"permission_ok": True, "doc_recall_hit": True},
        {"permission_ok": False, "doc_recall_hit": False},
    ]
    s = ev.summarize(results)
    assert s["total"] == 2 and s["permission_regressions"] == 1 and s["recall_hits"] == 1
