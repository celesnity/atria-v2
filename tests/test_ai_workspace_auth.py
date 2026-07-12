"""Persona login (module-level demo auth)."""
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

import repo  # noqa: E402
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


def test_password_hash_roundtrip():
    stored = repo.hash_password("12345678")
    assert repo.verify_password("12345678", stored)
    assert not repo.verify_password("wrong", stored)


def test_authenticate_accepts_demo_password(env):
    user = repo.authenticate("U004", "12345678")
    assert user is not None and user.role == "Employee" and user.department == "ENG"


def test_authenticate_rejects_wrong_password(env):
    assert repo.authenticate("U004", "nope") is None
    assert repo.authenticate("UZZZ", "12345678") is None


def test_login_reports_upload_capability(env):
    code, emp = cli("login", "--user", "U004", "--password", "12345678")
    assert code == 0 and emp["authenticated"] is True and emp["can_upload"] is False

    code, mgr = cli("login", "--user", "U005", "--password", "12345678")
    assert code == 0 and mgr["authenticated"] is True and mgr["can_upload"] is True


def test_login_rejects_bad_password(env):
    code, out = cli("login", "--user", "U004", "--password", "bad")
    assert code == 1 and out["authenticated"] is False
