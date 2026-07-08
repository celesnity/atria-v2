"""Upload authorization + secure retrieval."""
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
    src = tmp_path / "note.md"
    src.write_text("# Ghi chú\nNội dung mật.\n", encoding="utf-8")
    return src


def cli(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = workspace.main(list(argv))
    return code, json.loads(buf.getvalue())


def test_employee_cannot_upload(env):
    code, out = cli("add-document", "--user", "U004", "--file", str(env),
                    "--classification", "Confidential")
    assert code == 1 and out["uploaded"] is False
    assert "Manager" in out["reason"]


def test_manager_upload_sets_department_from_account(env):
    code, out = cli("add-document", "--user", "U005", "--file", str(env),
                    "--classification", "Confidential", "--title", "Ghi chú vận hành")
    assert code == 0 and out["uploaded"] is True
    assert out["department"] == "OPS"  # U005's department, not from input
    assert out["doc_id"] == "DOC041"


def test_invalid_classification_rejected(env):
    code, out = cli("add-document", "--user", "U005", "--file", str(env),
                    "--classification", "TopSecret")
    assert code == 1 and out["uploaded"] is False


def test_uploaded_confidential_is_department_scoped(env):
    _, up = cli("add-document", "--user", "U005", "--file", str(env),
                "--classification", "Confidential")
    doc_id = up["doc_id"]
    # same-department member can open and read content
    _, allow = cli("read-document", "--user", "U013", "--doc", doc_id)  # U013 = OPS
    assert allow["allowed"] is True and "Nội dung mật" in allow["content"]
    # other-department employee is denied
    _, deny = cli("read-document", "--user", "U004", "--doc", doc_id)  # ENG
    assert deny["allowed"] is False


def test_upload_docx_extracts_text(env, tmp_path):
    docx = pytest.importorskip("docx")
    path = tmp_path / "sla.docx"
    doc = docx.Document()
    doc.add_paragraph("Quy định SLA vận hành nội bộ")
    doc.save(str(path))

    code, up = cli("add-document", "--user", "U005", "--file", str(path),
                   "--classification", "Internal", "--title", "SLA")
    assert code == 0 and up["uploaded"] is True
    assert up["extracted_chars"] > 0  # text was parsed out of the .docx

    # an OPS member can read the extracted text of the binary document
    _, opened = cli("read-document", "--user", "U005", "--doc", up["doc_id"])
    assert opened["allowed"] is True
    assert "SLA vận hành" in opened["content"]


def test_upload_via_base64_stdin(env, monkeypatch, tmp_path):
    # Simulate the dashboard path: binary bytes sent as base64 over stdin.
    import base64
    import io

    payload = base64.b64encode("# Ghi chú\nNội dung base64.".encode("utf-8")).decode()
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(payload.encode())))
    code, up = cli("add-document", "--user", "U005", "--stdin", "--base64",
                   "--filename", "note.md", "--classification", "Internal")
    assert code == 0 and up["uploaded"] is True
