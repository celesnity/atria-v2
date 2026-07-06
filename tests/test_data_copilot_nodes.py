import importlib.util
import sys
import types
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"

# The module scripts use flat, sys.path-relative imports (import gates, etc.), so
# the scripts dir needs to be on sys.path (mirrors test_data_copilot_gates.py).
if str(_MOD) not in sys.path:
    sys.path.insert(0, str(_MOD))


def _load(n, s):
    spec = importlib.util.spec_from_file_location(s, _MOD / f"{n}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[s] = m
    spec.loader.exec_module(m)
    return m


def _ctx(**kw):
    return types.SimpleNamespace(**kw)


def test_code_critic_pass_sets_verdict_true():
    for dep in (
        "verdict",
        "prompts",
        "generate",
        "guardrails",
        "gates",
        "report_schema",
        "report",
        "report_generator",
        "persona_schema",
    ):
        _load(dep, dep)
    nodes = _load("nodes", "dc_nodes")

    class RC:
        def chat(self, role, messages, **kw):
            return "PASS"

    out = nodes.code_critic({"generated_code": "print(1)"}, _ctx(rc=RC()))
    assert out["critic_verdict"] is True


def test_code_critic_fail_sets_verdict_false():
    nodes = _load("nodes", "dc_nodes2")

    class RC:
        def chat(self, role, messages, **kw):
            return "FAIL missing plot"

    out = nodes.code_critic({"generated_code": "x=1"}, _ctx(rc=RC()))
    assert out["critic_verdict"] is False


def test_execute_code_records_cell_and_status():
    nodes = _load("nodes", "dc_nodes3")

    class K:
        def run(self, code):
            return {"status": "text", "stdout": "42", "figures": []}

    out = nodes.execute_code(
        {"generated_code": "print(42)", "executed_cells": []}, _ctx(kernel=K())
    )
    assert out["exe_sign"] == "text"
    assert out["executed_cells"] == ["print(42)"]


def test_semantic_verify_accepts_non_business():
    for dep in ("verdict", "gates", "persona_schema"):
        _load(dep, dep)
    nodes = _load("nodes", "dc_nodes4")
    out = nodes.semantic_verify(
        {"user_task": "df.head()", "generated_code": "c", "exe_result": "ok"}, _ctx(domain=None)
    )
    assert out["verdict"]["status"] == "ACCEPT"
