"""Adversarial: the graph path must never surface a chunk the user can't access.

We wire an EKGraphStore to a fake store that simulates a fully-leaking backend:
it returns ALL candidate chunks — Public, other-department Confidential, and
Restricted — regardless of the ACL params it was passed, for every query.
``graph_retrieval.expand``'s own authoritative ``acl.can_access`` re-check is
therefore the SOLE mechanism producing each expected per-corner result set. If
that re-check were ever removed from ``expand``, this test would fail.
"""

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


# An in-memory graph: seed entity 'e' is mentioned by the seed chunk and by three
# candidate chunks of different classifications/departments.
_CANDIDATES = {
    "pub": {
        "chunk_id": "DOCP#0",
        "doc_id": "DOCP",
        "text": "t",
        "title": "P",
        "department": "COMP",
        "classification": "Public",
        "knowledge_space": "Company Knowledge",
        "citation": "[P]",
    },
    "conf_hr": {
        "chunk_id": "DOCH#0",
        "doc_id": "DOCH",
        "text": "t",
        "title": "H",
        "department": "HR",
        "classification": "Confidential",
        "knowledge_space": "Department Knowledge",
        "citation": "[H]",
    },
    "restricted": {
        "chunk_id": "DOCR#0",
        "doc_id": "DOCR",
        "text": "t",
        "title": "R",
        "department": "EXEC",
        "classification": "Restricted",
        "knowledge_space": "Executive Knowledge",
        "citation": "[R]",
    },
}


def _run_fn(cypher, params):
    # Simulate a fully-leaking store: return every candidate unconditionally,
    # ignoring params/ACL entirely. expand()'s own acl.can_access re-check is
    # the only thing standing between this and a leak.
    if ":MENTIONS]->" in cypher:
        return list(_CANDIDATES.values())
    return []  # no tag edges in this fixture


@pytest.mark.parametrize(
    "role,dept,expected_ids",
    [
        ("Employee", "ENG", {"DOCP#0"}),  # only Public survives
        ("Employee", "HR", {"DOCP#0", "DOCH#0"}),  # + own-dept Confidential
        ("Executive", "EXEC", {"DOCP#0", "DOCH#0", "DOCR#0"}),  # sees all
    ],
)
def test_graph_expand_never_leaks(role, dept, expected_ids):
    gs_mod = _load("graph_store", f"ek_leak_gs_{role}_{dept}")
    gr = _load("graph_retrieval", f"ek_leak_gr_{role}_{dept}")
    identity = _load("identity", f"ek_leak_id_{role}_{dept}")
    store = gs_mod.EKGraphStore(_run_fn)
    user = identity.User("U", "n", role, dept, "Active")
    out = gr.expand(store, [{"chunk_id": "SEED#0"}], user, hops=1, max_neighbors=20)
    assert {h["chunk_id"] for h in out} == expected_ids
