import importlib.util, sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    mod = importlib.util.module_from_spec(spec); sys.modules[sentinel] = mod
    spec.loader.exec_module(mod); return mod


def _rg():
    # compose() does bare `from config import ...` / `import report as _report`,
    # so the scripts dir needs to be on sys.path (mirrors test_data_copilot_persona_report.py).
    sys.path.insert(0, str(_MOD))
    _load("report_schema", "report_schema")
    _load("report", "report")
    return _load("report_generator", "dc_rg")


def test_catalogs_present_verbatim():
    rg = _rg()
    assert "Thu thập thêm dữ liệu hành vi" in rg.ROADMAP_METADATA
    assert rg.ROADMAP_METADATA["Thu thập thêm dữ liệu hành vi"]["owner"] == "Data Team"


def test_compose_falls_back_when_no_persona_json():
    rg = _rg()
    calls = {}
    class RC:
        def chat(self, role, messages, **kw):
            calls["role"] = role
            return "# Generic report\nGrounded."
    out = rg.compose("total revenue: 100", rc=RC(), question="total revenue?")
    assert "Generic report" in out
    assert calls["role"] == "report"


def test_compose_uses_persona_composer_when_json_present(monkeypatch):
    rg = _rg()
    monkeypatch.setattr(rg.ReportGenerator, "generate_markdown_report",
                        lambda self, raw: "# BÁO CÁO\n(6-section)")
    class RC:
        def chat(self, role, messages, **kw):
            return "unused"
    out = rg.compose("[JSON_START_PERSONA][]" "[JSON_END_PERSONA]", rc=RC(), question="segment")
    assert "BÁO CÁO" in out
