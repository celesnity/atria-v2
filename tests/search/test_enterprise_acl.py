"""Unit tests for the Track 1 permission matrix."""

import sys
from pathlib import Path

from qdrant_client import models

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


def test_confidential_blank_department_treated_as_unknown():
    # Empty-string department must be equivalent to None (unknown): denied for
    # Confidential, and the Qdrant filter must likewise omit the Confidential
    # branch for an empty department (mirrors the falsy `if department:` check).
    assert is_allowed("Employee", "", "Confidential", "") is False
    assert len(qdrant_acl_filter("Employee", "").should) == 1


def test_restricted_executive_only():
    for role in ("Employee", "Manager", "Director"):
        assert not is_allowed(role, "Finance", "Restricted", "Finance")
    assert is_allowed("Executive", "Executive Office", "Restricted", "Finance")


def test_allowed_clause_shapes():
    assert allowed_clause("Executive", 1) == "TRUE"
    clause = allowed_clause("Employee", 3)
    assert clause == (
        "(classification IN ('Public','Internal') "
        "OR (classification = 'Confidential' AND department = $3))"
    )


def test_qdrant_filter_none_for_executive():
    assert qdrant_acl_filter("Executive", "Executive Office") is None
    assert qdrant_acl_filter("Employee", "Finance") is not None


def test_qdrant_filter_structure_for_department_scoped_employee():
    result = qdrant_acl_filter("Employee", "Finance")
    assert isinstance(result, models.Filter)
    assert len(result.should) == 2

    open_branch, confidential_branch = result.should

    assert isinstance(open_branch, models.FieldCondition)
    assert open_branch.key == "classification"
    assert isinstance(open_branch.match, models.MatchAny)
    assert set(open_branch.match.any) == {"Public", "Internal"}

    assert isinstance(confidential_branch, models.Filter)
    assert confidential_branch.must is not None
    assert len(confidential_branch.must) == 2

    classification_cond, department_cond = confidential_branch.must
    assert isinstance(classification_cond, models.FieldCondition)
    assert classification_cond.key == "classification"
    assert isinstance(classification_cond.match, models.MatchValue)
    assert classification_cond.match.value == "Confidential"

    assert isinstance(department_cond, models.FieldCondition)
    assert department_cond.key == "department"
    assert isinstance(department_cond.match, models.MatchValue)
    assert department_cond.match.value == "Finance"


def test_qdrant_filter_no_confidential_branch_without_department():
    result = qdrant_acl_filter("Employee", None)
    assert len(result.should) == 1


def test_role_string_matching_fails_closed_for_non_exact_executive():
    # Only the exact string "Executive" grants the executive bypass; case
    # variants and unrelated role names must fail closed (treated as
    # non-executive) rather than silently gaining elevated access.
    assert is_allowed("executive", "Finance", "Restricted", "Finance") is False
    assert is_allowed("Admin", "Finance", "Confidential", "HR") is False
    assert allowed_clause("executive", 1) != "TRUE"
    assert qdrant_acl_filter("admin", "Finance") is not None
