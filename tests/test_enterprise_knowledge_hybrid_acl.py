"""Adversarial: no search mode (dense/bm25/hybrid) may return forbidden docs."""

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


def _rec(chunking, doc_id, text, cls, dept):
    cid = f"{doc_id}#0"
    return chunking.ChunkRecord(
        doc_id=doc_id,
        chunk_id=cid,
        text=text,
        start_index=0,
        end_index=len(text),
        token_count=len(text.split()),
        title=f"T{doc_id}",
        department=dept,
        classification=cls,
        knowledge_space="Department Knowledge",
        owner=dept,
        source_path=f"/x/{doc_id}.md",
        citation=f"T{doc_id} [{doc_id}] · {cid}",
    )


# Every doc shares the token "chung" and the same dense vector, so absent ACL all
# five would match every mode; only the ACL filter may exclude them.
_DOCS = [
    ("DOCP", "chung public", "Public", "COMP"),
    ("DOCI", "chung internal", "Internal", "COMP"),
    ("DOCH", "chung hr mật", "Confidential", "HR"),
    ("DOCPR", "chung prod mật", "Confidential", "PROD"),
    ("DOCR", "chung restricted", "Restricted", "EXEC"),
]


def _store():
    from qdrant_client import QdrantClient

    chunking = _load("chunking", "ek_hacl_chunk")
    index_store = _load("index_store", "ek_hacl_store")
    s = index_store.IndexStore(QdrantClient(":memory:"), lambda ts: [[1.0, 0.0, 0.0] for _ in ts])
    s.ensure_collection(dim=3)
    s.upsert_chunks([_rec(chunking, d, t, c, dp) for d, t, c, dp in _DOCS], avgdl=2.0)
    return s


@pytest.mark.parametrize("mode", ["dense", "bm25", "hybrid"])
@pytest.mark.parametrize(
    "role,dept,forbidden",
    [
        ("Employee", "ENG", {"DOCH", "DOCPR", "DOCR"}),
        ("Employee", "HR", {"DOCPR", "DOCR"}),  # own-dept HR Confidential allowed
        ("Executive", "EXEC", set()),  # sees all
    ],
)
def test_no_mode_leaks_forbidden_docs(mode, role, dept, forbidden):
    s = _store()
    acl = _load("acl", f"ek_hacl_acl_{mode}_{role}_{dept}")
    identity = _load("identity", f"ek_hacl_id_{mode}_{role}_{dept}")
    user = identity.User("U", "n", role, dept, "Active")
    hits = s.query("chung", k=10, acl_filter=acl.build_filter(user), mode=mode)
    ids = {h["doc_id"] for h in hits}
    assert ids.isdisjoint(forbidden), f"{mode} leaked {ids & forbidden} to {role}/{dept}"
