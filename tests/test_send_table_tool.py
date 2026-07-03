"""Tests for the read-only send_table tool."""

from types import SimpleNamespace

from atria.core.context_engineering.tools.implementations.send_table_tool import (
    SendTableHandler,
)


class _CB:
    def __init__(self):
        self.payloads = []

    def on_data(self, payload):
        self.payloads.append(payload)


def test_send_table_emits_readonly_payload(tmp_path, monkeypatch):
    from atria.core.modules import data_copilot_paths as dcp

    root = dcp.data_copilot_root("sessZ", str(tmp_path))
    run = root / "runs" / "latest"
    run.mkdir(parents=True)
    (run / "result.csv").write_text("region,rev\nN,10\nS,20\n", encoding="utf-8")

    cb = _CB()
    handler = SendTableHandler()
    monkeypatch.setattr(handler, "_resolve_session", lambda context: ("sessZ", str(tmp_path)))
    ctx = SimpleNamespace(ui_callback=cb)
    res = handler.send(
        {
            "file": str(run / "result.csv"),
            "title": "Rev",
            "suggestions": [{"chart_type": "bar", "x": "region", "y": ["rev"], "title": "Rev"}],
        },
        ctx,
    )
    assert res["success"] is True
    p = cb.payloads[0]
    assert p["editable"] is False
    assert [c["name"] for c in p["columns"]] == ["region", "rev"]
    assert p["rows"][0]["region"] == "N"
    assert p["suggestions"][0]["chart_type"] == "bar"


def test_send_table_requires_file_and_title():
    handler = SendTableHandler()
    ctx = SimpleNamespace(ui_callback=SimpleNamespace(on_data=lambda p: None))
    assert handler.send({"title": "x"}, ctx)["success"] is False
    assert handler.send({"file": "x.csv"}, ctx)["success"] is False
