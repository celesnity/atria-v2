"""Access predicate parity — same canonical cases as the dataset matrix."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "modules" / "ai_workspace" / "scripts"
_TOOLS = Path(__file__).resolve().parent.parent / "modules" / "ai_workspace" / "tools"
for _p in (str(_SCRIPTS), str(_TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import access  # noqa: E402
import repo  # noqa: E402
import seed_db  # noqa: E402


# (role, user_dept, classification, doc_dept, expected_allowed)
CASES = [
    ("Employee", "ENG", "Confidential", "HR", False),
    ("Employee", "HR", "Confidential", "HR", True),
    ("Employee", "PROD", "Restricted", "EXEC", False),
    ("Executive", "EXEC", "Restricted", "EXEC", True),
    ("Manager", "FIN", "Confidential", "OPS", False),
    ("Manager", "OPS", "Confidential", "OPS", True),
    ("Employee", "ENG", "Internal", "COMP", True),
    ("Employee", "PROD", "Public", "COMP", True),
]


@pytest.mark.parametrize("role,udept,cls,ddept,expected", CASES)
def test_decide_default_matrix(role, udept, cls, ddept, expected):
    assert access.decide(role, udept, cls, ddept).allowed is expected


# 3-gate model: a department's own knowledge is isolated — even Internal docs of
# another department are not visible; Company docs are company-wide; Executive
# sees everything.
GATE_CASES = [
    ("Employee", "ENG", "Internal", "HR", False),    # other-dept Internal -> denied
    ("Employee", "HR", "Internal", "HR", True),       # own-dept Internal -> allowed
    ("Employee", "ENG", "Internal", "COMP", True),    # company Internal -> all
    ("Employee", "ENG", "Public", "HR", True),        # public anywhere -> all
    ("Manager", "FIN", "Internal", "OPS", False),     # other-dept Internal -> denied
    ("Director", "PROD", "Internal", "LEGAL", False), # other-dept Internal -> denied
    ("Executive", "EXEC", "Internal", "HR", True),    # executive sees all departments
]


@pytest.mark.parametrize("role,udept,cls,ddept,expected", GATE_CASES)
def test_three_gate_department_isolation(role, udept, cls, ddept, expected):
    assert access.decide(role, udept, cls, ddept).allowed is expected


def test_knowledge_space_mapping():
    assert access.knowledge_space_of("COMP") == access.COMPANY_KNOWLEDGE
    assert access.knowledge_space_of("EXEC") == access.EXECUTIVE_KNOWLEDGE
    assert access.knowledge_space_of("HR") == access.DEPARTMENT_KNOWLEDGE


def test_restricted_denied_for_all_non_executives():
    for role in ("Employee", "Manager", "Director"):
        assert access.decide(role, "EXEC", "Restricted", "EXEC").allowed is False
    assert access.decide("Executive", "EXEC", "Restricted", "EXEC").allowed is True


def test_upload_roles():
    assert access.can_upload("Manager") and access.can_upload("Director")
    assert access.can_upload("Executive")
    assert not access.can_upload("Employee")


def test_seeded_matrix_matches_default(tmp_path, monkeypatch):
    monkeypatch.setenv("AIW_DB_PATH", str(tmp_path / "aiw.db"))
    monkeypatch.setenv("AIW_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("AIW_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    seed_db.seed()
    assert repo.load_access_matrix() == access.DEFAULT_MATRIX
