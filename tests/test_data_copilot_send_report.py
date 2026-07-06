"""Tests for the read-only send_report tool."""

from types import SimpleNamespace

from atria.core.context_engineering.tools.implementations import send_report_tool as t
from atria.core.context_engineering.tools.implementations.send_report_tool import (
    SendReportHandler,
)


class _CB:
    def __init__(self):
        self.payloads = []

    def on_data(self, payload):
        self.payloads.append(payload)


def test_build_payload_reads_report(monkeypatch, tmp_path):
    monkeypatch.setattr(t.dcp, "read_report", lambda s, w, r: {"report": "# R"})

    payload = t._build_payload(session_id="1", working_dir=str(tmp_path), run_dir="runs/run-x")

    assert payload["type"] == "report"
    assert payload["report"] == "# R"
    assert payload["run_dir"] == "runs/run-x"


def test_send_report_emits_payload(monkeypatch, tmp_path):
    from atria.core.modules import data_copilot_paths as dcp

    root = dcp.data_copilot_root("sessZ", str(tmp_path))
    run = root / "runs" / "run-x"
    run.mkdir(parents=True)
    (run / "report.md").write_text("# Report\n\nBody", encoding="utf-8")

    cb = _CB()
    handler = SendReportHandler()
    monkeypatch.setattr(handler, "_resolve_session", lambda context: ("sessZ", str(tmp_path)))
    ctx = SimpleNamespace(ui_callback=cb)

    res = handler.send({"run_dir": "runs/run-x"}, ctx)

    assert res["success"] is True
    p = cb.payloads[0]
    assert p["type"] == "report"
    assert p["report"] == "# Report\n\nBody"
    assert p["run_dir"] == "runs/run-x"
    assert res["data_payload"] == p


def test_send_report_requires_run_dir():
    handler = SendReportHandler()
    ctx = SimpleNamespace(ui_callback=SimpleNamespace(on_data=lambda p: None))
    assert handler.send({}, ctx)["success"] is False


def test_send_report_missing_report_file(monkeypatch, tmp_path):
    handler = SendReportHandler()
    monkeypatch.setattr(handler, "_resolve_session", lambda context: ("sessZ", str(tmp_path)))
    ctx = SimpleNamespace(ui_callback=_CB())

    res = handler.send({"run_dir": "runs/missing"}, ctx)

    assert res["success"] is False
    assert "not found" in res["error"]


def test_send_report_requires_ui_callback(tmp_path):
    handler = SendReportHandler()
    ctx = SimpleNamespace(ui_callback=None)
    assert handler.send({"run_dir": "runs/run-x"}, ctx)["success"] is False
