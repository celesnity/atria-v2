"""Unit tests for the Track 1 permission matrix."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "modules" / "enterprise_search"))
from acl import allowed_clause, is_allowed, qdrant_acl_filter  # noqa: E402


def test_public_and_internal_open_to_all_roles():
    for role in ("Employee", "Manager", "Director", "Executive"):
        assert is_allowed(role, "Finance", "Public", "Human Resources")
        assert is_allowed(role, None, "Internal", "Engineering")


def test_confidential_own_department_only():
    assert is_allowed("Employee", "Finance", "Confidential", "Finance")
    assert not is_allowed("Employee", "Finance", "Confidential", "Human Resources")
    assert not is_allowed("Director", "Engineering", "Confidential", "Finance")
    assert is_allowed("Executive", "Executive Office", "Confidential", "Finance")
    assert not is_allowed("Employee", None, "Confidential", "Finance")


def test_restricted_executive_only():
    for role in ("Employee", "Manager", "Director"):
        assert not is_allowed(role, "Finance", "Restricted", "Finance")
    assert is_allowed("Executive", "Executive Office", "Restricted", "Finance")


def test_allowed_clause_shapes():
    assert allowed_clause("Executive", 1) == "TRUE"
    clause = allowed_clause("Employee", 3)
    assert "classification IN ('Public','Internal')" in clause
    assert "$3" in clause
    assert "Restricted" not in clause  # restricted is excluded by omission


def test_qdrant_filter_none_for_executive():
    assert qdrant_acl_filter("Executive", "Executive Office") is None
    assert qdrant_acl_filter("Employee", "Finance") is not None
