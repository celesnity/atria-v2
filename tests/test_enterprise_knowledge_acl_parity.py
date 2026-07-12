"""Cross-module ACL parity: enterprise_knowledge must decide access exactly like
ai_workspace (the authoritative My Tasco P1 department-security model).

Both modules encode the same 4x4 role x classification rules *and* the knowledge-
space gate (Company / Department / Executive Knowledge). This test runs the full
cartesian product of (role, user_department, classification, doc_department)
through ``ai_workspace.access.decide`` and ``enterprise_knowledge.acl.can_access``
and asserts identical allow/deny outcomes, so the two enforcement points can
never drift on the shared corpus.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_AW = _ROOT / "modules" / "ai_workspace" / "scripts"
_EK = _ROOT / "modules" / "enterprise_knowledge" / "scripts"

ROLES = ("Employee", "Manager", "Director", "Executive")
DEPTS = ("COMP", "EXEC", "HR", "FIN", "ENG", "OPS", "LEGAL", "PROD")
CLASSIFICATIONS = ("Public", "Internal", "Confidential", "Restricted")


def _load(path: Path, name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, path / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def _modules():
    aw = _load(_AW, "access", "parity_aw_access")
    ek = _load(_EK, "acl", "parity_ek_acl")
    identity = _load(_EK, "identity", "parity_ek_identity")
    return aw, ek, identity


def test_ek_acl_matches_ai_workspace_on_every_combination():
    aw, ek, identity = _modules()
    mismatches = []
    for role in ROLES:
        for udept in DEPTS:
            for cls in CLASSIFICATIONS:
                for ddept in DEPTS:
                    aw_allowed = aw.decide(role, udept, cls, ddept).allowed
                    user = identity.User("U", "n", role, udept, "Active")
                    ek_allowed = ek.can_access(
                        user, {"classification": cls, "department": ddept}
                    ).allowed
                    if aw_allowed != ek_allowed:
                        mismatches.append(
                            f"{role}/{udept} x {cls}@{ddept}: "
                            f"ai_workspace={aw_allowed} ek={ek_allowed}"
                        )
    assert not mismatches, "ACL divergence:\n" + "\n".join(mismatches[:20])


def test_cross_department_internal_is_denied():
    """A FIN employee may not read ENG's Internal department knowledge."""
    _, ek, identity = _modules()
    user = identity.User("U", "n", "Employee", "FIN", "Active")
    d = ek.can_access(user, {"classification": "Internal", "department": "ENG"})
    assert d.allowed is False


def test_executive_office_internal_is_executive_only():
    """Executive-Office documents are executive-only regardless of classification."""
    _, ek, identity = _modules()
    emp = identity.User("U", "n", "Employee", "ENG", "Active")
    exe = identity.User("U", "n", "Executive", "EXEC", "Active")
    assert ek.can_access(emp, {"classification": "Internal", "department": "EXEC"}).allowed is False
    assert ek.can_access(exe, {"classification": "Internal", "department": "EXEC"}).allowed is True


def test_company_confidential_visible_to_all_employees():
    """Company Knowledge is company-wide even at Confidential classification."""
    _, ek, identity = _modules()
    user = identity.User("U", "n", "Employee", "HR", "Active")
    d = ek.can_access(user, {"classification": "Confidential", "department": "COMP"})
    assert d.allowed is True


def test_own_department_internal_allowed():
    """An employee still sees their own department's Internal knowledge."""
    _, ek, identity = _modules()
    user = identity.User("U", "n", "Employee", "HR", "Active")
    d = ek.can_access(user, {"classification": "Internal", "department": "HR"})
    assert d.allowed is True
