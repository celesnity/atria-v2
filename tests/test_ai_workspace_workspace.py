"""Department workspace + folders filtering (server-side access)."""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "modules" / "ai_workspace" / "scripts"
_TOOLS = Path(__file__).resolve().parent.parent / "modules" / "ai_workspace" / "tools"
for _p in (str(_SCRIPTS), str(_TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import seed_db  # noqa: E402
import workspace  # noqa: E402


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("AIW_DB_PATH", str(tmp_path / "aiw.db"))
    monkeypatch.setenv("AIW_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("AIW_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    seed_db.seed()


def cli(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = workspace.main(list(argv))
    return code, json.loads(buf.getvalue())


def test_executive_sees_all_documents(env):
    _, out = cli("workspace", "--user", "U007")
    assert out["total_visible"] == 40


def test_employee_sees_fewer_and_no_other_dept_confidential(env):
    _, out = cli("workspace", "--user", "U004")  # ENG Employee
    assert out["total_visible"] < 40
    ids = {d["doc_id"] for d in out["documents"]}
    assert "DOC007" not in ids  # HR Confidential — other department
    assert "DOC009" not in ids  # HR Internal — other department (isolated)
    # A non-executive employee only sees Company docs + their own department's docs.
    for d in out["documents"]:
        if d["classification"] == "Restricted":
            raise AssertionError("Restricted leaked to Employee")
        assert d["department"] in ("COMP", "ENG"), f"leaked {d['doc_id']} ({d['department']})"


def test_owner_department_sees_own_confidential(env):
    _, out = cli("workspace", "--user", "U001")  # HR Employee
    ids = {d["doc_id"] for d in out["documents"]}
    assert "DOC007" in ids  # HR Confidential — own department


def test_folders_grid_locks_and_counts(env):
    _, out = cli("folders", "--user", "U004")  # ENG Employee
    by = {f["dept_code"]: f for f in out["folders"]}
    assert len(by) == 8
    assert by["ENG"]["is_own"] is True and by["ENG"]["locked"] is False
    assert by["HR"]["locked"] is True
    assert by["EXEC"]["visible_count"] == 0  # all EXEC docs are Restricted
    assert out["can_upload"] is False


def test_folders_executive_unlocked(env):
    _, out = cli("folders", "--user", "U007")
    for f in out["folders"]:
        assert f["locked"] is False
