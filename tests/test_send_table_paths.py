"""Path-resolution tests for send_table: workspace files + data/ nesting fix."""

from __future__ import annotations

import types

import pytest

from atria.core.modules import data_copilot_paths as dcp


def _write(path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_resolve_confined_strips_redundant_data_prefix(tmp_path):
    root = dcp.data_copilot_root("1", str(tmp_path))
    _write(root / "data" / "foo.csv", "a\n1\n")
    # Both 'foo.csv' and 'data/foo.csv' resolve to <root>/data/foo.csv.
    p1 = dcp._resolve_confined("1", str(tmp_path), "foo.csv")
    p2 = dcp._resolve_confined("1", str(tmp_path), "data/foo.csv")
    assert p1 == p2 == (root / "data" / "foo.csv").resolve()


def test_read_session_csv_accepts_data_prefixed_name(tmp_path):
    root = dcp.data_copilot_root("1", str(tmp_path))
    _write(root / "data" / "r.csv", "x,y\n1,2\n")
    out = dcp.read_session_csv("1", str(tmp_path), "data/r.csv")
    assert [c["name"] for c in out["columns"]] == ["x", "y"]
    assert out["rows"] == [{"x": "1", "y": "2"}]


def test_read_workspace_csv_reads_module_data_dir(tmp_path):
    # File lives in a module data dir, outside the data_copilot root but inside wd.
    _write(tmp_path / "modules" / "data_copilot" / "data" / "sales.csv", "Month,Rev\nJan,100\n")
    out = dcp.read_workspace_csv(str(tmp_path), "modules/data_copilot/data/sales.csv")
    assert [c["name"] for c in out["columns"]] == ["Month", "Rev"]
    assert out["rows"] == [{"Month": "Jan", "Rev": "100"}]


def test_read_workspace_csv_blocks_traversal(tmp_path):
    with pytest.raises(ValueError):
        dcp.read_workspace_csv(str(tmp_path), "../escape.csv")


def test_read_csv_flexible_prefers_data_copilot_then_workspace(tmp_path):
    # Only in the workspace (module dir) → flexible read still finds it.
    _write(tmp_path / "modules" / "m" / "data" / "w.csv", "a\n9\n")
    out = dcp.read_csv_flexible("1", str(tmp_path), "modules/m/data/w.csv")
    assert out["rows"] == [{"a": "9"}]

    # Present in the data_copilot root → that one wins over a same-named wd file.
    root = dcp.data_copilot_root("1", str(tmp_path))
    _write(root / "data" / "dup.csv", "a\n1\n")
    _write(tmp_path / "dup.csv", "a\n2\n")
    out2 = dcp.read_csv_flexible("1", str(tmp_path), "dup.csv")
    assert out2["rows"] == [{"a": "1"}]


def test_send_table_reads_workspace_file_via_fallback(tmp_path):
    from atria.core.context_engineering.tools.implementations.send_table_tool import (
        SendTableHandler,
    )

    _write(
        tmp_path / "modules" / "data_copilot" / "data" / "sales_data.csv",
        "Month,Revenue\nJan,100\nFeb,200\n",
    )

    captured: dict = {}

    class _UICallback:
        def on_data(self, payload):
            captured.update(payload)

    class _Session:
        id = "7"
        working_directory = str(tmp_path)

    class _SessionManager:
        async def get_current_session(self):
            return _Session()

    context = types.SimpleNamespace(
        ui_callback=_UICallback(), session_manager=_SessionManager()
    )

    handler = SendTableHandler()
    result = handler.send(
        {"file": "modules/data_copilot/data/sales_data.csv", "title": "Sales"}, context
    )

    assert result["success"] is True, result
    assert [c["name"] for c in result["data_payload"]["columns"]] == ["Month", "Revenue"]
    assert len(result["data_payload"]["rows"]) == 2
    assert captured["chart_id"]
