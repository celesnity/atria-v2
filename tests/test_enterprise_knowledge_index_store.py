"""Index store tests: real in-memory Qdrant, fake embeddings, ACL filtering."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def _rec(chunking, doc_id, i, text, cls, dept):
    cid = f"{doc_id}#{i}"
    return chunking.ChunkRecord(
        doc_id=doc_id, chunk_id=cid, text=text, start_index=0, end_index=len(text),
        token_count=len(text.split()), title=f"T{doc_id}", department=dept,
        classification=cls, knowledge_space="Department Knowledge", owner=dept,
        source_path=f"/x/{doc_id}.md", citation=f"T{doc_id} [{doc_id}] · {cid}",
    )


def _embed_fn(texts):
    out = []
    for t in texts:
        low = t.lower()
        out.append([
            1.0 if "lương" in low else 0.0,
            1.0 if "nghỉ" in low else 0.0,
            1.0 if "sản phẩm" in low else 0.0,
        ])
    return out


@pytest.fixture()
def env():
    from qdrant_client import QdrantClient
    chunking = _load("chunking", "ek_chunk_for_store")
    identity = _load("identity", "ek_ident_for_store")
    acl = _load("acl", "ek_acl_for_store")
    index_store = _load("index_store", "ek_index_store_uut")
    s = index_store.IndexStore(QdrantClient(":memory:"), _embed_fn)
    s.ensure_collection(dim=3)
    s.upsert_chunks([
        _rec(chunking, "DOC007", 0, "khung lương phòng nhân sự", "Confidential", "HR"),
        _rec(chunking, "DOC002", 0, "chính sách nghỉ phép", "Internal", "COMP"),
        _rec(chunking, "DOC016", 0, "chiến lược sản phẩm", "Confidential", "PROD"),
    ])
    return s, identity, acl


def test_employee_cannot_retrieve_other_dept_confidential(env):
    s, identity, acl = env
    eng = identity.User("U004", "n", "Employee", "ENG", "Active")
    hits = s.query("lương", k=5, acl_filter=acl.build_filter(eng))
    ids = {h["doc_id"] for h in hits}
    assert "DOC007" not in ids  # HR confidential is filtered out


def test_hr_employee_can_retrieve_own_confidential(env):
    s, identity, acl = env
    hr = identity.User("U001", "n", "Employee", "HR", "Active")
    hits = s.query("lương", k=5, acl_filter=acl.build_filter(hr))
    assert "DOC007" in {h["doc_id"] for h in hits}


def test_executive_sees_all(env):
    s, identity, acl = env
    ex = identity.User("U007", "n", "Executive", "EXEC", "Active")
    hits = s.query("sản phẩm", k=5, acl_filter=acl.build_filter(ex))
    assert "DOC016" in {h["doc_id"] for h in hits}
