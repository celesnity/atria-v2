"""EKGraphStore tests using an in-memory fake run_fn (no live Neo4j)."""

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


class FakeRun:
    """Record every (cypher, params) and return a canned rows list."""

    def __init__(self, rows=None):
        self.calls = []
        self._rows = rows or []

    def __call__(self, cypher, params):
        self.calls.append((cypher, params))
        return self._rows


def test_ensure_constraints_covers_all_ek_labels():
    gs = _load("graph_store", "ek_gs_constraints")
    fake = FakeRun()
    gs.EKGraphStore(fake).ensure_constraints()
    joined = " ".join(c for c, _ in fake.calls)
    for label, key in [
        ("EKDocument", "doc_id"),
        ("EKChunk", "chunk_id"),
        ("EKEntity", "key"),
        ("EKTag", "name"),
    ]:
        assert f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE" in joined


def test_upsert_document_merges_doc_department_and_tags():
    gs = _load("graph_store", "ek_gs_doc")
    fake = FakeRun()
    gs.EKGraphStore(fake).upsert_document(
        {
            "doc_id": "DOC001",
            "title": "Sổ tay",
            "department": "COMP",
            "classification": "Public",
            "owner": "COMP",
            "knowledge_space": "Company Knowledge",
            "last_updated": "2025-02-04",
            "tags": ["sổ", "company"],
        }
    )
    cyphers = " ".join(c for c, _ in fake.calls)
    assert "MERGE (d:EKDocument:EKNode {doc_id: $doc_id})" in cyphers
    assert ":IN_DEPARTMENT]->" in cyphers
    assert ":TAGGED]->" in cyphers
    # one TAGGED merge per tag
    assert sum("MERGE (t:EKTag:EKNode {name: $name})" in c for c, _ in fake.calls) == 2


def test_reset_only_deletes_ek_namespace():
    gs = _load("graph_store", "ek_gs_reset")
    fake = FakeRun()
    gs.EKGraphStore(fake).reset()
    assert fake.calls == [("MATCH (n:EKNode) DETACH DELETE n", {})]


def test_acl_params_executive_vs_employee():
    gs = _load("graph_store", "ek_gs_acl")
    ident = _load("identity", "ek_ident_gs")
    ex = gs.acl_params(ident.User("U", "n", "Executive", "EXEC", "Active"))
    emp = gs.acl_params(ident.User("U", "n", "Employee", "ENG", "Active"))
    assert ex["is_exec"] is True
    assert emp["is_exec"] is False and emp["dept"] == "ENG"
    assert emp["open"] == ["Public", "Internal"] and emp["conf"] == "Confidential"


def test_upsert_extraction_merges_entities_mentions_and_relations():
    gs = _load("graph_store", "ek_gs_ext")
    ext_mod = _load("extraction", "ek_ext_for_gs")
    fake = FakeRun()
    ext = ext_mod.GraphExtraction(
        entities=[ext_mod.Entity("Policy", "leave", {"status": "unverified"})],
        edges=[ext_mod.Edge("RELATED_TO", "leave", "handbook", {"confidence": 0.8})],
    )
    n, e = gs.EKGraphStore(fake).upsert_extraction("DOC001#0", ext)
    assert (n, e) == (1, 1)
    cyphers = " ".join(c for c, _ in fake.calls)
    assert "MERGE (n:EKEntity:EKNode {key: $key})" in cyphers
    assert ":MENTIONS]->" in cyphers
    assert ":RELATED_TO]->" in cyphers


def test_neighbors_via_entities_builds_acl_scoped_cypher():
    gs = _load("graph_store", "ek_gs_nbr_e")
    rows = [
        {
            "chunk_id": "DOC002#0",
            "doc_id": "DOC002",
            "text": "t",
            "title": "T",
            "department": "COMP",
            "classification": "Internal",
            "knowledge_space": "Company Knowledge",
            "citation": "c",
        }
    ]
    fake = FakeRun(rows)
    acl = {"is_exec": False, "dept": "ENG", "open": ["Public", "Internal"], "conf": "Confidential"}
    out = gs.EKGraphStore(fake).neighbors_via_entities(["DOC001#0"], hops=1, acl=acl, limit=20)
    assert out == rows
    cypher, params = fake.calls[0]
    assert ":MENTIONS]->" in cypher and "RELATED_TO" in cypher
    assert "$is_exec" in cypher and "$open" in cypher and "$conf" in cypher
    assert params["seeds"] == ["DOC001#0"] and params["dept"] == "ENG"
    assert "*0..1" in cypher  # hops inlined as a sanitized int


def test_neighbors_via_tags_builds_acl_scoped_cypher():
    gs = _load("graph_store", "ek_gs_nbr_t")
    fake = FakeRun([])
    acl = {"is_exec": True, "dept": "EXEC", "open": ["Public", "Internal"], "conf": "Confidential"}
    gs.EKGraphStore(fake).neighbors_via_tags(["DOC001#0"], acl=acl, limit=10)
    cypher, params = fake.calls[0]
    assert ":TAGGED]" in cypher and ":PART_OF]" in cypher
    assert params["seeds"] == ["DOC001#0"] and params["limit"] == 10
