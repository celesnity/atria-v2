"""ACL predicate tests, seeded with labeled Deny/Allow cases from the dataset."""

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


def _user(role, dept):
    ident = _load("identity", "ek_identity_for_acl")
    return ident.User("U", "n", role, dept, "Active")


# (role, user_dept, doc_classification, doc_dept, expected_allowed) — from Public_Evaluation.
CASES = [
    ("Employee", "ENG", "Confidential", "HR", False),  # P009 Deny
    ("Employee", "HR", "Confidential", "HR", True),  # P010 Allow
    ("Employee", "PROD", "Restricted", "EXEC", False),  # P007 Deny
    ("Executive", "EXEC", "Restricted", "EXEC", True),  # P008 Allow
    ("Manager", "FIN", "Confidential", "OPS", False),  # P035 Deny
    ("Manager", "OPS", "Confidential", "OPS", True),  # P034 Allow
    ("Employee", "ENG", "Internal", "COMP", True),  # internal → all
    ("Employee", "PROD", "Public", "COMP", True),  # public → all
]


@pytest.mark.parametrize("role,udept,cls,ddept,expected", CASES)
def test_can_access_matrix(role, udept, cls, ddept, expected):
    acl = _load("acl", "ek_acl_uut")
    dec = acl.can_access(_user(role, udept), {"classification": cls, "department": ddept})
    assert dec.allowed is expected


def test_build_filter_none_for_executive():
    acl = _load("acl", "ek_acl_uut2")
    assert acl.build_filter(_user("Executive", "EXEC")) is None


def test_build_filter_is_a_qdrant_filter_for_employee():
    acl = _load("acl", "ek_acl_uut3")
    from qdrant_client import models

    f = acl.build_filter(_user("Employee", "ENG"))
    assert isinstance(f, models.Filter)


def test_build_filter_excludes_restricted_and_other_dept_confidential():
    """Behavioral guard: an Employee's filter admits only their accessible docs."""
    from qdrant_client import QdrantClient, models

    acl = _load("acl", "ek_acl_filter_behavior")
    q = QdrantClient(":memory:")
    q.create_collection(
        "t",
        vectors_config=models.VectorParams(size=1, distance=models.Distance.COSINE),
    )
    # (name, classification, department, knowledge_space) — the full indexed schema.
    docs = [
        ("public_COMP", "Public", "COMP", "Company Knowledge"),
        ("internal_COMP", "Internal", "COMP", "Company Knowledge"),
        ("conf_ENG", "Confidential", "ENG", "Department Knowledge"),
        ("internal_ENG", "Internal", "ENG", "Department Knowledge"),
        ("internal_HR", "Internal", "HR", "Department Knowledge"),
        ("conf_HR", "Confidential", "HR", "Department Knowledge"),
        ("internal_EXEC", "Internal", "EXEC", "Executive Knowledge"),
        ("restricted_EXEC", "Restricted", "EXEC", "Executive Knowledge"),
    ]
    q.upsert(
        "t",
        points=[
            models.PointStruct(
                id=i,
                vector=[1.0],
                payload={
                    "classification": c,
                    "department": d,
                    "knowledge_space": ks,
                    "name": n,
                },
            )
            for i, (n, c, d, ks) in enumerate(docs)
        ],
    )
    eng = _user("Employee", "ENG")
    rows, _ = q.scroll("t", scroll_filter=acl.build_filter(eng), with_payload=True, limit=100)
    visible = {r.payload["name"] for r in rows}
    assert visible == {"public_COMP", "internal_COMP", "conf_ENG", "internal_ENG"}
    assert "conf_HR" not in visible  # other-department Confidential excluded
    assert "internal_HR" not in visible  # other-department Internal excluded
    assert "internal_EXEC" not in visible  # Executive Knowledge excluded for non-exec
    assert "restricted_EXEC" not in visible  # Restricted excluded for non-executive
