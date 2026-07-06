import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"

# The module scripts use flat, sys.path-relative imports (import gates, etc.), so
# the scripts dir needs to be on sys.path (mirrors test_data_copilot_nodes.py).
if str(_MOD) not in sys.path:
    sys.path.insert(0, str(_MOD))


def _load(n, s):
    spec = importlib.util.spec_from_file_location(s, _MOD / f"{n}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[s] = m
    spec.loader.exec_module(m)
    return m


def _graph():
    for dep in (
        "state",
        "verdict",
        "prompts",
        "generate",
        "guardrails",
        "gates",
        "report_schema",
        "report",
        "report_generator",
        "persona_schema",
        "nodes",
    ):
        _load(dep, dep)
    return _load("graph", "dc_graph")


def test_after_execute_routes():
    g = _graph()
    assert g._after_execute({"exe_sign": "text"}) == "semantic_verify"
    assert g._after_execute({"exe_sign": "error", "syntax_attempts": 0}) == "repair_code"
    assert g._after_execute({"exe_sign": "error", "syntax_attempts": 4}) == "generate_report"


def test_after_verify_routes():
    g = _graph()
    assert (
        g._after_verify({"verdict": {"status": "ACCEPT"}, "semantic_attempts": 0})
        == "generate_report"
    )
    assert (
        g._after_verify({"verdict": {"status": "REVISE"}, "semantic_attempts": 0}) == "semantic_fix"
    )
    assert (
        g._after_verify({"verdict": {"status": "REVISE"}, "semantic_attempts": 5})
        == "generate_report"
    )


def test_after_classify_routes():
    g = _graph()
    assert g._after_classify({"review_status": "APPROVE"}) == "generate_code"
    assert g._after_classify({"review_status": "REJECT"}) == "generate_plan"


def test_build_graph_compiles_with_langgraph_1x():
    g = _graph()

    class _DummyCtx:
        rc = None
        kernel = None

    from langgraph.checkpoint.memory import MemorySaver

    compiled = g.build_graph(_DummyCtx(), MemorySaver())
    assert compiled is not None
    # Compiled graphs expose get_graph() in both 0.2.x and 1.x LangGraph APIs.
    node_names = set(compiled.get_graph().nodes.keys())
    assert "generate_plan" in node_names
    assert "generate_report" in node_names
