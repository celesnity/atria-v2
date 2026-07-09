"""Graph retrieval: ACL re-check on graph candidates, and vector+graph merge."""

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


class StubStore:
    """Returns preset candidates, incl. one the user must NOT be able to access."""

    def __init__(self, ent, tag):
        self._ent, self._tag = ent, tag

    def neighbors_via_entities(self, seeds, hops, acl, limit):
        return self._ent

    def neighbors_via_tags(self, seeds, acl, limit):
        return self._tag


def _chunk(cid, cls, dept):
    return {
        "chunk_id": cid,
        "doc_id": cid.split("#")[0],
        "text": "t",
        "title": "T",
        "department": dept,
        "classification": cls,
        "knowledge_space": "Department Knowledge",
        "citation": f"[{cid}]",
    }


def test_expand_drops_forbidden_candidate_even_if_store_returns_it():
    gr = _load("graph_retrieval", "ek_gr_expand")
    identity = _load("identity", "ek_ident_gr")
    # Store leaks a Confidential HR chunk to an ENG employee; expand() MUST drop it.
    store = StubStore(
        ent=[_chunk("DOC050#0", "Confidential", "HR"), _chunk("DOC002#0", "Internal", "COMP")],
        tag=[],
    )
    eng = identity.User("U004", "n", "Employee", "ENG", "Active")
    out = gr.expand(store, [{"chunk_id": "DOC001#0"}], eng, hops=1, max_neighbors=20)
    ids = {h["chunk_id"] for h in out}
    assert "DOC002#0" in ids
    assert "DOC050#0" not in ids  # authoritative acl.can_access re-check blocks it


def test_merge_dedups_and_appends_graph_only_below_vector():
    gr = _load("graph_retrieval", "ek_gr_merge")
    vector = [
        {"chunk_id": "A#0", "score": 0.9, "citation": "[A]"},
        {"chunk_id": "B#0", "score": 0.5, "citation": "[B]"},
    ]
    graph = [
        {"chunk_id": "B#0", "citation": "[B]"},  # dup of a vector hit
        {"chunk_id": "C#0", "citation": "[C]"},
    ]  # graph-only
    merged = gr.merge_hits(vector, graph, cap=10, boost=0.1)
    ids = [h["chunk_id"] for h in merged]
    assert ids[:2] == ["A#0", "B#0"]  # vector hits lead
    assert "C#0" in ids  # graph-only appended
    assert merged[0]["score"] >= merged[1]["score"]  # ordering preserved


def test_merge_respects_cap():
    gr = _load("graph_retrieval", "ek_gr_cap")
    vector = [{"chunk_id": "A#0", "score": 0.9, "citation": "[A]"}]
    graph = [{"chunk_id": f"G{i}#0", "citation": f"[G{i}]"} for i in range(10)]
    assert len(gr.merge_hits(vector, graph, cap=3)) == 3
