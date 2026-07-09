"""Schema + seed integrity for the ai_workspace module DB."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "modules" / "ai_workspace" / "scripts"
_TOOLS = Path(__file__).resolve().parent.parent / "modules" / "ai_workspace" / "tools"
for _p in (str(_SCRIPTS), str(_TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import models  # noqa: E402
import repo  # noqa: E402
import seed_db  # noqa: E402
from db import session_scope  # noqa: E402
from sqlalchemy import select  # noqa: E402


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("AIW_DB_PATH", str(tmp_path / "aiw.db"))
    monkeypatch.setenv("AIW_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("AIW_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    counts = seed_db.seed()
    return counts


def test_seed_counts(env):
    assert env == {
        "departments": 8, "roles": 4, "classifications": 4,
        "access_matrix": 16, "users": 32, "documents": 40,
    }


def test_fk_integrity(env):
    with session_scope() as s:
        roles = {r.id for r in s.scalars(select(models.Role))}
        depts = {d.id for d in s.scalars(select(models.Department))}
        classes = {c.id for c in s.scalars(select(models.Classification))}
        users = list(s.scalars(select(models.User)))
        docs = list(s.scalars(select(models.Document)))
    assert len(users) == 32 and len(docs) == 40
    for u in users:
        assert u.role_id in roles, u.id
        assert u.department_id in depts, u.id
        assert u.password_hash.startswith("pbkdf2$")
    for d in docs:
        assert d.department_id in depts, d.id
        assert d.classification_id in classes, d.id
        assert d.file_path, d.id


def test_access_matrix_is_16_unique_pairs(env):
    matrix = repo.load_access_matrix()
    assert len(matrix) == 16
    assert {r for (r, _c) in matrix} == {"Employee", "Manager", "Director", "Executive"}
    assert {c for (_r, c) in matrix} == {"Public", "Internal", "Confidential", "Restricted"}


def test_seed_is_idempotent(env):
    again = seed_db.seed()
    assert again["documents"] == 40
    assert len(repo.list_documents()) == 40


def test_document_has_index_status_default_pending(env):
    repo.insert_document(
        doc_id="DOC900", title="t", dept_code="ENG", classification_code="Internal",
        file_path="ENG/DOC900_t.txt", original_filename="t.txt", mime_type="text/plain",
        size_bytes=3, uploaded_by="U004",
    )
    assert repo.get_document("DOC900")["index_status"] == "pending"
    assert repo.set_index_status("DOC900", "indexed") is True
    assert repo.get_document("DOC900")["index_status"] == "indexed"
    assert repo.set_index_status("NOPE", "indexed") is False
