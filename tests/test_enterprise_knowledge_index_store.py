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


def _embed_fn(texts):
    out = []
    for t in texts:
        low = t.lower()
        out.append(
            [
                1.0 if "lương" in low else 0.0,
                1.0 if "nghỉ" in low else 0.0,
                1.0 if "sản phẩm" in low else 0.0,
            ]
        )
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
    s.upsert_chunks(
        [
            _rec(chunking, "DOC007", 0, "khung lương phòng nhân sự", "Confidential", "HR"),
            _rec(chunking, "DOC002", 0, "chính sách nghỉ phép", "Internal", "COMP"),
            _rec(chunking, "DOC016", 0, "chiến lược sản phẩm", "Confidential", "PROD"),
        ]
    )
    return s, identity, acl


def test_employee_cannot_retrieve_other_dept_confidential(env):
    s, identity, acl = env
    eng = identity.User("U004", "n", "Employee", "ENG", "Active")
    hits = s.query("lương", k=5, acl_filter=acl.build_filter(eng), mode="dense")
    ids = {h["doc_id"] for h in hits}
    assert "DOC007" not in ids  # HR confidential is filtered out


def test_hr_employee_can_retrieve_own_confidential(env):
    s, identity, acl = env
    hr = identity.User("U001", "n", "Employee", "HR", "Active")
    hits = s.query("lương", k=5, acl_filter=acl.build_filter(hr), mode="dense")
    assert "DOC007" in {h["doc_id"] for h in hits}


def test_executive_sees_all(env):
    s, identity, acl = env
    ex = identity.User("U007", "n", "Executive", "EXEC", "Active")
    hits = s.query("sản phẩm", k=5, acl_filter=acl.build_filter(ex), mode="dense")
    assert "DOC016" in {h["doc_id"] for h in hits}


def test_upsert_with_avgdl_stores_sparse_vector():
    from qdrant_client import QdrantClient
    from uuid import uuid5

    chunking = _load("chunking", "ek_chunk_sparse")
    index_store = _load("index_store", "ek_store_sparse")
    s = index_store.IndexStore(QdrantClient(":memory:"), _embed_fn)
    s.ensure_collection(dim=3)
    rec = _rec(chunking, "DOC001", 0, "chính sách nghỉ phép", "Internal", "COMP")
    s.upsert_chunks([rec], avgdl=3.0)
    point_id = str(uuid5(index_store._POINT_NS, rec.citation))
    got = s._q.retrieve("enterprise_chunks", ids=[point_id], with_vectors=True)[0]
    assert "dense" in got.vector and "bm25" in got.vector


def test_upsert_without_avgdl_is_dense_only():
    from qdrant_client import QdrantClient
    from uuid import uuid5

    chunking = _load("chunking", "ek_chunk_dense")
    index_store = _load("index_store", "ek_store_dense")
    s = index_store.IndexStore(QdrantClient(":memory:"), _embed_fn)
    s.ensure_collection(dim=3)
    rec = _rec(chunking, "DOC002", 0, "chính sách nghỉ phép", "Internal", "COMP")
    s.upsert_chunks([rec])
    got = s._q.retrieve(
        "enterprise_chunks",
        ids=[str(uuid5(index_store._POINT_NS, rec.citation))],
        with_vectors=True,
    )[0]
    assert "dense" in got.vector and "bm25" not in got.vector


def _vec_embed(mapping):
    def _fn(texts):
        return [mapping[t] for t in texts]

    return _fn


def test_modes_dense_bm25_hybrid_fusion():
    from qdrant_client import QdrantClient

    chunking = _load("chunking", "ek_chunk_modes")
    index_store = _load("index_store", "ek_store_modes")
    # Dense vectors are assigned per exact text, decoupled from the words, so a
    # query can semantically point at A while lexically matching B.
    embed = _vec_embed(
        {
            "semantic match doc": [1.0, 0, 0],
            "keyword zzz doc": [0, 1.0, 0],
            "distractor doc": [0, 0, 1.0],
            "zzz": [1.0, 0, 0],  # query embeds toward A, not B
        }
    )
    s = index_store.IndexStore(QdrantClient(":memory:"), embed)
    s.ensure_collection(dim=3)
    s.upsert_chunks(
        [
            _rec(chunking, "DOCA", 0, "semantic match doc", "Public", "COMP"),
            _rec(chunking, "DOCB", 0, "keyword zzz doc", "Public", "COMP"),
            _rec(chunking, "DOCC", 0, "distractor doc", "Public", "COMP"),
        ],
        avgdl=3.0,
    )

    dense = {h["doc_id"] for h in s.query("zzz", k=1, mode="dense")}
    assert "DOCA" in dense and "DOCB" not in dense  # dense misses the lexical match

    bm25_hits = {h["doc_id"] for h in s.query("zzz", k=3, mode="bm25")}
    assert "DOCB" in bm25_hits  # bm25 finds it by keyword

    hybrid = {h["doc_id"] for h in s.query("zzz", k=2, mode="hybrid")}
    assert {"DOCA", "DOCB"} <= hybrid  # fusion surfaces both


def test_unknown_mode_raises():
    import pytest
    from qdrant_client import QdrantClient

    index_store = _load("index_store", "ek_store_badmode")
    s = index_store.IndexStore(QdrantClient(":memory:"), _embed_fn)
    s.ensure_collection(dim=3)
    with pytest.raises(ValueError):
        s.query("x", mode="nope")


def _make_store(sentinel):
    from qdrant_client import QdrantClient

    index_store = _load("index_store", sentinel)
    s = index_store.IndexStore(QdrantClient(":memory:"), _embed_fn)
    s.ensure_collection(dim=3)
    return s


def test_upsert_stores_token_count_in_payload():
    chunking = _load("chunking", "ek_is_tc_chunk")
    s = _make_store("ek_is_tc_store")
    rec = _rec(chunking, "DOCT", 0, "một hai ba bốn", "Internal", "ENG")  # 4 tokens
    s.upsert_chunks([rec], avgdl=4.0)
    pts, _ = s._q.scroll(s._collection, with_payload=True, limit=10)
    assert pts[0].payload["token_count"] == rec.token_count == 4


def test_delete_by_doc_id_removes_only_that_doc():
    chunking = _load("chunking", "ek_is_del_chunk")
    s = _make_store("ek_is_del_store")
    s.upsert_chunks(
        [
            _rec(chunking, "DOCA", 0, "a b", "Internal", "ENG"),
            _rec(chunking, "DOCB", 0, "c d", "Internal", "ENG"),
        ],
        avgdl=2.0,
    )
    removed = s.delete_by_doc_id("DOCA")
    assert removed == 1
    left = {p.payload["doc_id"] for p in s._q.scroll(s._collection, limit=10)[0]}
    assert left == {"DOCB"}


def test_delete_by_doc_id_absent_returns_zero():
    s = _make_store("ek_is_del_absent")
    assert s.delete_by_doc_id("NOPE") == 0


def test_corpus_token_stats_sums_token_count():
    chunking = _load("chunking", "ek_is_stats_chunk")
    s = _make_store("ek_is_stats_store")
    r1 = _rec(chunking, "DOCA", 0, "a b c", "Internal", "ENG")  # 3 tokens
    r2 = _rec(chunking, "DOCB", 0, "d e", "Internal", "ENG")  # 2 tokens
    s.upsert_chunks([r1, r2], avgdl=2.5)
    total_tokens, total_chunks = s.corpus_token_stats()
    assert total_chunks == 2
    assert total_tokens == r1.token_count + r2.token_count == 5


def test_corpus_token_stats_empty_is_zero():
    s = _make_store("ek_is_stats_empty")
    assert s.corpus_token_stats() == (0, 0)
