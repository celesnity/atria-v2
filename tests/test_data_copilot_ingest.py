"""Tests for the data_copilot `ingest` command — bringing datasets into the
module's data/ dir so they become addressable by send_editable_table + analyze."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

# The module scripts use flat, sys.path-relative imports (import audit, etc.),
# mirroring how copilot.py runs them. Add the scripts dir so we can import ingest.
_SCRIPTS = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import ingest as ingest_mod  # type: ignore[import-not-found]  # noqa: E402

from atria.core.modules import store  # noqa: E402


def _make_xlsx(sheets: dict[str, list[list]]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _module_root(tmp_path: Path) -> Path:
    """Create a minimal data_copilot module (needs SKILL.md for the store)."""
    (tmp_path / "data_copilot").mkdir()
    (tmp_path / "data_copilot" / "SKILL.md").write_text("---\nname: data_copilot\n---\n")
    return tmp_path


def test_slug_sanitizes_name():
    assert ingest_mod._slug("My Sales 2026!") == "my-sales-2026"
    assert ingest_mod._slug("") == "dataset"


def test_to_csv_files_csv_passthrough(tmp_path):
    src = tmp_path / "raw.csv"
    src.write_bytes(b"a,b\n1,2\n")
    out = ingest_mod.to_csv_files(src, "sales")
    assert out == [("sales.csv", b"a,b\n1,2\n")]


def test_to_csv_files_xlsx_multisheet(tmp_path):
    src = tmp_path / "book.xlsx"
    src.write_bytes(_make_xlsx({"One": [["x"], [1]], "Two": [["y"], [2]]}))
    out = ingest_mod.to_csv_files(src, "book")
    names = sorted(fname for fname, _ in out)
    assert names == ["book__one.csv", "book__two.csv"]


def test_to_csv_files_rejects_unsupported(tmp_path):
    src = tmp_path / "notes.txt"
    src.write_text("hi")
    with pytest.raises(ValueError, match="unsupported file type"):
        ingest_mod.to_csv_files(src, "notes")


def test_ingest_csv_writes_into_module_data_dir(tmp_path):
    root = _module_root(tmp_path)
    src = tmp_path / "demo.csv"
    src.write_bytes(b"region,revenue\nNorth,100\n")

    result = ingest_mod.ingest(str(src), root=root)

    assert result["module"] == "data_copilot"
    assert len(result["files"]) == 1
    entry = result["files"][0]
    # `file` is the data/-relative form for send_editable_table.
    assert entry["file"] == "demo.csv"
    # `path` is the absolute copy for analyze/profile and exists on disk.
    assert Path(entry["path"]).is_file()
    assert (root / "data_copilot" / "data" / "demo.csv").read_bytes() == src.read_bytes()

    # Round-trips through the same store API send_editable_table uses.
    data = store.read_dataset(root, "data_copilot", "demo.csv")
    assert [c["name"] for c in data["columns"]] == ["region", "revenue"]
    assert data["rows"][0] == {"region": "North", "revenue": "100"}


def test_ingest_respects_name_override(tmp_path):
    root = _module_root(tmp_path)
    src = tmp_path / "demo.csv"
    src.write_bytes(b"a\n1\n")
    result = ingest_mod.ingest(str(src), name="Q1 Sales", root=root)
    assert result["files"][0]["file"] == "q1-sales.csv"


def test_ingest_missing_source_raises(tmp_path):
    root = _module_root(tmp_path)
    with pytest.raises(FileNotFoundError):
        ingest_mod.ingest(str(tmp_path / "nope.csv"), root=root)


def test_list_datasets_empty_when_no_data_dir(tmp_path):
    root = _module_root(tmp_path)
    assert ingest_mod.list_datasets(root=root) == []


def test_list_datasets_reports_files_and_columns(tmp_path):
    root = _module_root(tmp_path)
    src = tmp_path / "demo.csv"
    src.write_bytes(b"region,revenue,date\nNorth,100,2026-01-01\n")
    ingest_mod.ingest(str(src), root=root)

    listed = ingest_mod.list_datasets(root=root)
    assert len(listed) == 1
    entry = listed[0]
    assert entry["file"] == "demo.csv"
    assert entry["columns"] == ["region", "revenue", "date"]
    assert entry["size"] > 0
    assert Path(entry["path"]).is_file()


def test_list_datasets_excludes_bak_files(tmp_path):
    root = _module_root(tmp_path)
    data_dir = root / "data_copilot" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "a.csv").write_text("x\n1\n")
    (data_dir / "a.csv.bak").write_text("x\n0\n")
    files = [e["file"] for e in ingest_mod.list_datasets(root=root)]
    assert files == ["a.csv"]
