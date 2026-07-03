"""CLI wiring tests for whoami / can-access / guard_accessible (no live services)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_guard_accessible_splits_hits():
    k = _load("knowledge", "ek_knowledge_uut")
    identity = _load("identity", "ek_ident_for_cli")
    eng = identity.User("U004", "n", "Employee", "ENG", "Active")
    hits = [
        {"doc_id": "DOC002", "classification": "Internal", "department": "COMP"},
        {"doc_id": "DOC007", "classification": "Confidential", "department": "HR"},
    ]
    safe, blocked = k.guard_accessible(eng, hits)
    assert [h["doc_id"] for h in safe] == ["DOC002"]
    assert [h["doc_id"] for h in blocked] == ["DOC007"]


def test_can_access_command_denies(capsys, tmp_path, monkeypatch):
    k = _load("knowledge", "ek_knowledge_uut2")
    monkeypatch.setenv("EK_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    # users.csv
    users = tmp_path / "users.csv"
    users.write_text(
        "user_id,full_name,department,role,email,status\n"
        "U004,n,ENG,Employee,e,Active\n", encoding="utf-8")
    # a single sample doc
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "DOC036.md").write_text(
        "---\ndoc_id: DOC036\ntitle: t\ndepartment: EXEC\nclassification: Restricted\n---\nx\n",
        encoding="utf-8")
    rc = k.main(["can-access", "U004", "DOC036",
                 "--users", str(users), "--samples", str(docs)])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"allowed": false' in out.lower() or '"allowed": false' in out


def test_whoami_unknown_user_returns_clean_error(capsys, tmp_path, monkeypatch):
    k = _load("knowledge", "ek_knowledge_uut_unknown")
    monkeypatch.setenv("EK_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    users = tmp_path / "users.csv"
    users.write_text(
        "user_id,full_name,department,role,email,status\n"
        "U004,n,ENG,Employee,e,Active\n", encoding="utf-8")
    rc = k.main(["whoami", "U999", "--users", str(users)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "error" in out.lower()
