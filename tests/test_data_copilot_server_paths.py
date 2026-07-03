"""Tests for the server-side session CSV read/write helpers."""

import pytest

from atria.core.modules import data_copilot_paths as dcp


def test_root_and_write_read_roundtrip(tmp_path):
    root = dcp.data_copilot_root("sess1", str(tmp_path))
    assert root == tmp_path / ".artifacts" / "data_copilot" / "sess1"
    out = dcp.write_session_csv(
        "sess1", str(tmp_path), "edited.csv",
        [{"name": "a"}, {"name": "b"}],
        [{"a": "1", "b": "x"}, {"a": "2", "b": "y"}],
    )
    assert out["rows"] == 2
    read = dcp.read_session_csv("sess1", str(tmp_path), "edited.csv")
    assert [c["name"] for c in read["columns"]] == ["a", "b"]
    assert read["rows"][0]["a"] == "1"


def test_read_absolute_path_inside_root(tmp_path):
    root = dcp.data_copilot_root("sess2", str(tmp_path))
    run = root / "runs" / "latest"
    run.mkdir(parents=True)
    (run / "result.csv").write_text("k,v\nx,1\n", encoding="utf-8")
    read = dcp.read_session_csv("sess2", str(tmp_path), str(run / "result.csv"))
    assert read["rows"][0]["k"] == "x"


def test_rejects_path_outside_root(tmp_path):
    with pytest.raises(ValueError):
        dcp.read_session_csv("sess3", str(tmp_path), "../../etc/passwd")


def test_write_rejects_non_csv(tmp_path):
    with pytest.raises(ValueError):
        dcp.write_session_csv("sess4", str(tmp_path), "notcsv.txt", [{"name": "a"}], [])
