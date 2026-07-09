"""ai_workspace-facing ingest entry: one document at a time, ACL-aware, audit-free."""

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


def _store():
    from qdrant_client import QdrantClient

    index_store = _load("index_store", "ek_api_store")
    s = index_store.IndexStore(QdrantClient(":memory:"), lambda ts: [[1.0, 0.0, 0.0] for _ in ts])
    s.ensure_collection(dim=3)
    return s


def test_ingest_document_indexes_chunks_with_acl_payload():
    api = _load("ingest_api", "ek_api_1")
    s = _store()
    r = api.ingest_document(
        "DOC900", "Chính sách nghỉ phép", "ENG", "Internal",
        "Nhân viên được nghỉ phép theo quy định của phòng.", owner="U004", store=s
    )
    assert r["chunks_indexed"] >= 1 and r["doc_tokens"] > 0
    pts, _ = s._q.scroll(s._collection, with_payload=True, limit=10)
    p = pts[0].payload
    assert p["doc_id"] == "DOC900" and p["department"] == "ENG"
    assert p["classification"] == "Internal" and p["knowledge_space"] == "Department Knowledge"
    assert p["owner"] == "U004" and p["token_count"] > 0


def test_running_avgdl_accounts_for_existing_and_new():
    api = _load("ingest_api", "ek_api_2")
    s = _store()
    api.ingest_document("DOCA", "A", "ENG", "Internal", "a b c d e f", store=s)  # 6 tokens
    r = api.ingest_document("DOCB", "B", "ENG", "Internal", "x y", store=s)  # 2 tokens
    tot_tokens, tot_chunks = s.corpus_token_stats()
    assert abs(r["avgdl_used"] - tot_tokens / tot_chunks) < 1e-6


def test_ingest_empty_text_indexes_nothing():
    api = _load("ingest_api", "ek_api_3")
    s = _store()
    r = api.ingest_document("DOCE", "E", "ENG", "Internal", "   ", store=s)
    assert r["chunks_indexed"] == 0


def test_remove_document_deletes_all_its_chunks():
    api = _load("ingest_api", "ek_api_4")
    s = _store()
    api.ingest_document("DOCX", "X", "ENG", "Internal", "a b c", store=s)
    assert api.remove_document("DOCX", store=s) >= 1
    assert s.corpus_token_stats() == (0, 0)


def test_ingested_doc_respects_acl_filter():
    api = _load("ingest_api", "ek_api_5")
    acl = _load("acl", "ek_api_acl")
    identity = _load("identity", "ek_api_id")
    s = _store()
    api.ingest_document("DOCH", "HR internal", "HR", "Internal", "lương thưởng nội bộ", store=s)
    other = identity.User("U", "n", "Employee", "ENG", "Active")
    hits = s.query("lương", k=5, acl_filter=acl.build_filter(other))
    assert all(h["doc_id"] != "DOCH" for h in hits)  # cross-dept Internal excluded


def test_ingest_api_does_not_import_audit():
    _load("ingest_api", "ek_api_noaudit")
    mod = sys.modules["ek_api_noaudit"]
    assert "audit" not in mod.__dict__  # slim entry never pulls in the shared 'audit' name


def test_reindex_documents_rebuilds_with_exact_avgdl():
    api = _load("ingest_api", "ek_api_reindex")
    s = _store()
    docs = [
        {"doc_id": "DOCA", "title": "A", "department": "ENG", "classification": "Internal",
         "text": "a b c", "owner": "U004"},
        {"doc_id": "DOCB", "title": "B", "department": "ENG", "classification": "Internal",
         "text": "d e", "owner": "U004"},
    ]
    res = api.reindex_documents(docs, store=s)
    assert res["chunks_indexed"] == 2
    assert s.corpus_token_stats()[1] == 2
