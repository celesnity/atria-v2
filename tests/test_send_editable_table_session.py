"""Tests that send_editable_table binds to a session data_copilot file."""

from types import SimpleNamespace

from atria.core.context_engineering.tools.implementations.send_editable_table_tool import (
    SendEditableTableHandler,
)


class _CB:
    def __init__(self):
        self.payloads = []

    def on_data(self, p):
        self.payloads.append(p)


def test_editable_session_source(tmp_path, monkeypatch):
    from atria.core.modules import data_copilot_paths as dcp

    dcp.write_session_csv("sEdit", str(tmp_path), "grid.csv", [{"name": "a"}], [{"a": "1"}])
    h = SendEditableTableHandler()
    monkeypatch.setattr(h, "_resolve_session", lambda ctx: ("sEdit", str(tmp_path)))
    cb = _CB()
    res = h.send({"file": "grid.csv", "title": "Grid"}, SimpleNamespace(ui_callback=cb))
    assert res["success"] is True
    p = cb.payloads[0]
    assert p["editable"] is True
    assert p["source"] == {"session": "sEdit", "file": "grid.csv"}
