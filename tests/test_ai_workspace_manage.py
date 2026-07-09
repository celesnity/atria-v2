"""Management commands: manage, delete, stats, Executive cross-dept upload, render."""
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
    # Keep hermetic: stub the EK indexing hook (no Qdrant/embeddings in tests).
    monkeypatch.setattr(workspace.ek_index, "index_document", lambda **kw: True)
    monkeypatch.setattr(workspace.ek_index, "remove_document", lambda **kw: True)
    return tmp_path


def cli(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = workspace.main(list(argv))
    return code, json.loads(buf.getvalue())


def test_manage_scope(env):
    _, mgr = cli("manage", "--user", "U005")  # Manager OPS
    assert mgr["scope"] == "OPS"
    assert all(d["department"] == "OPS" for d in mgr["documents"])
    # metadata present for the columns
    assert {"size_bytes", "uploaded_by_name", "created_at", "mime_type"} <= set(mgr["documents"][0])

    _, exec_all = cli("manage", "--user", "U007")  # Executive
    assert exec_all["total"] == 40
    _, exec_hr = cli("manage", "--user", "U007", "--department", "HR")
    assert all(d["department"] == "HR" for d in exec_hr["documents"])

    code, emp = cli("manage", "--user", "U004")  # Employee
    assert code == 1 and "error" in emp


def test_delete_authorization_and_effect(env):
    (env / "x.md").write_text("noi dung", encoding="utf-8")
    _, up = cli("add-document", "--user", "U005", "--file", str(env / "x.md"),
                "--classification", "Internal")
    doc_id = up["doc_id"]

    # Employee cannot delete
    code, d1 = cli("delete-document", "--user", "U004", "--doc", doc_id)
    assert code == 1 and d1["deleted"] is False
    # Manager of another department cannot delete an OPS doc
    code, d2 = cli("delete-document", "--user", "U002", "--doc", doc_id)  # FIN Manager
    assert code == 1 and d2["deleted"] is False
    # OPS manager can
    code, d3 = cli("delete-document", "--user", "U005", "--doc", doc_id)
    assert code == 0 and d3["deleted"] is True
    # gone from OPS manager's manage view and from workspace
    _, mgr = cli("manage", "--user", "U005")
    assert doc_id not in {d["doc_id"] for d in mgr["documents"]}


def test_executive_can_upload_to_other_department(env):
    (env / "y.md").write_text("chien luoc", encoding="utf-8")
    code, up = cli("add-document", "--user", "U007", "--file", str(env / "y.md"),
                   "--classification", "Confidential", "--department", "HR")
    assert code == 0 and up["uploaded"] is True and up["department"] == "HR"

    # a Manager cannot target another department
    code, bad = cli("add-document", "--user", "U005", "--file", str(env / "y.md"),
                    "--classification", "Internal", "--department", "HR")
    assert code == 1 and bad["uploaded"] is False


def test_stats(env):
    _, s = cli("stats", "--user", "U004")  # ENG Employee
    assert s["total_visible"] == 10
    assert set(s["by_department"]) == {"COMP", "ENG"}


def test_read_document_renders_image(env):
    Image = pytest.importorskip("PIL.Image")
    p = env / "pic.png"
    Image.new("RGB", (30, 30), "white").save(str(p))
    _, up = cli("add-document", "--user", "U005", "--file", str(p), "--classification", "Internal")
    _, r = cli("read-document", "--user", "U005", "--doc", up["doc_id"])
    assert r["allowed"] is True and r["render"] == "image" and r["file_b64"]
