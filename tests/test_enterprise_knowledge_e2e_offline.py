"""Offline end-to-end: the real materialized 40-doc corpus + a fake embedder +
in-memory Qdrant, proving permission-aware retrieval enforces the ACL over real
data without needing hosted embeddings or a live Qdrant server."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge"
_MOD = _ROOT / "scripts"
_DOCS = _ROOT / "sample_documents"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def _fake_embed(texts):
    out = []
    for t in texts:
        v = [0.0] * 8
        for ch in t:
            v[ord(ch) % 8] += 1.0
        out.append(v)
    return out


@pytest.fixture()
def indexed():
    from qdrant_client import QdrantClient

    corpus = _load("corpus", "ek_corpus_e2e")
    chunking = _load("chunking", "ek_chunking_e2e")
    identity = _load("identity", "ek_identity_e2e")
    acl = _load("acl", "ek_acl_e2e")
    index_store = _load("index_store", "ek_index_store_e2e")
    store = index_store.IndexStore(QdrantClient(":memory:"), _fake_embed)
    store.ensure_collection(dim=8)
    docs = corpus.load_corpus(str(_DOCS))
    for doc in docs:
        store.upsert_chunks(chunking.chunk_document(doc))
    return store, identity, acl, len(docs)


def test_corpus_materialized_40_docs(indexed):
    _, _, _, n = indexed
    assert n == 40


def test_eng_employee_cannot_retrieve_hr_confidential(indexed):
    store, identity, acl, _ = indexed
    eng = identity.User("U004", "n", "Employee", "ENG", "Active")  # dataset P009 = Deny
    hits = store.query("khung lương", k=100, acl_filter=acl.build_filter(eng))
    assert all(h["doc_id"] != "DOC007" for h in hits)  # HR Confidential excluded


def test_hr_employee_can_retrieve_hr_confidential(indexed):
    store, identity, acl, _ = indexed
    hr = identity.User("U001", "n", "Employee", "HR", "Active")  # dataset P010 = Allow
    hits = store.query("khung lương", k=100, acl_filter=acl.build_filter(hr))
    assert any(h["doc_id"] == "DOC007" for h in hits)  # own-dept Confidential visible


def test_non_exec_never_sees_restricted(indexed):
    store, identity, acl, _ = indexed
    for role, dept in [("Employee", "ENG"), ("Manager", "FIN"), ("Director", "LEGAL")]:
        u = identity.User("U", "n", role, dept, "Active")
        hits = store.query("dự báo", k=100, acl_filter=acl.build_filter(u))
        assert all(h["classification"] != "Restricted" for h in hits)


def test_executive_sees_restricted(indexed):
    store, identity, acl, _ = indexed
    ex = identity.User("U007", "n", "Executive", "EXEC", "Active")
    hits = store.query("dự báo", k=100, acl_filter=acl.build_filter(ex))
    assert any(h["classification"] == "Restricted" for h in hits)


def test_cmd_query_empty_store_returns_no_leak_message(capsys, tmp_path, monkeypatch):
    """_cmd_query with zero accessible hits prints the no-leak message, no answer."""
    from qdrant_client import QdrantClient

    monkeypatch.setenv("EK_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    knowledge = _load("knowledge", "ek_knowledge_e2e_empty")
    index_store = _load("index_store", "ek_index_store_e2e_empty")
    users = tmp_path / "users.csv"
    users.write_text(
        "user_id,full_name,department,role,email,status\n"
        "U004,n,ENG,Employee,e,Active\n", encoding="utf-8")
    store = index_store.IndexStore(QdrantClient(":memory:"), _fake_embed)
    store.ensure_collection(dim=8)  # empty — nothing ingested
    rc = knowledge._cmd_query("bất kỳ", "U004", 5, None, False, str(users), store=store)
    out = capsys.readouterr().out
    assert rc == 0
    assert "phạm vi truy cập" in out   # the Vietnamese no-leak message
    assert '"answer"' not in out
    assert '"hits": []' in out


def test_cmd_query_excludes_other_dept_confidential(capsys, tmp_path, monkeypatch):
    """_cmd_query over the real corpus never returns another department's Confidential doc."""
    from qdrant_client import QdrantClient

    monkeypatch.setenv("EK_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    knowledge = _load("knowledge", "ek_knowledge_e2e_real")
    corpus = _load("corpus", "ek_corpus_e2e_real")
    chunking = _load("chunking", "ek_chunking_e2e_real")
    index_store = _load("index_store", "ek_index_store_e2e_real")
    users = tmp_path / "users.csv"
    users.write_text(
        "user_id,full_name,department,role,email,status\n"
        "U004,n,ENG,Employee,e,Active\n", encoding="utf-8")
    store = index_store.IndexStore(QdrantClient(":memory:"), _fake_embed)
    store.ensure_collection(dim=8)
    for doc in corpus.load_corpus(str(_DOCS)):
        store.upsert_chunks(chunking.chunk_document(doc))
    rc = knowledge._cmd_query("khung lương", "U004", 100, None, False, str(users), store=store)
    out = capsys.readouterr().out
    assert rc == 0
    assert "DOC007" not in out   # HR Confidential never leaks to an ENG employee
