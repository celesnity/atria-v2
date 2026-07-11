"""Access-control predicate — the department-security core.

Pure logic, no DB import, so it is unit-testable in isolation. Every decision is
driven by an access matrix keyed ``(role_en, classification_code) -> effect``.
``DEFAULT_MATRIX`` embeds the dataset's canonical 4x4 rules; at runtime the same
matrix is loaded from the DB (repo.load_access_matrix), so the two must agree —
a parity test guards against drift.

Effects: ``allow`` / ``deny`` are terminal; ``own_department`` allows only when
the requesting user's department equals the document's department.
"""
from __future__ import annotations

from dataclasses import dataclass

ALLOW = "allow"
DENY = "deny"
OWN_DEPARTMENT = "own_department"

EXECUTIVE = "Executive"
ROLES = ("Employee", "Manager", "Director", "Executive")
CLASSIFICATIONS = ("Public", "Internal", "Confidential", "Restricted")
UPLOAD_ROLES = frozenset({"Manager", "Director", "Executive"})


def _canonical_effect(role: str, classification: str) -> str:
    """The dataset rule for a (role, classification) cell."""
    if classification in ("Public", "Internal"):
        return ALLOW
    if classification == "Restricted":
        return ALLOW if role == "Executive" else DENY
    # Confidential
    return ALLOW if role == "Executive" else OWN_DEPARTMENT


DEFAULT_MATRIX: dict[tuple[str, str], str] = {
    (role, cls): _canonical_effect(role, cls)
    for role in ROLES
    for cls in CLASSIFICATIONS
}

# Knowledge spaces (Access control matrix in the problem statement). A document's
# space is derived from its owning department: the Company department is
# company-wide knowledge, the Executive Office is executive-only, everything else
# is that department's own knowledge.
COMPANY_DEPT = "COMP"
EXECUTIVE_DEPT = "EXEC"
COMPANY_KNOWLEDGE = "Company Knowledge"
DEPARTMENT_KNOWLEDGE = "Department Knowledge"
EXECUTIVE_KNOWLEDGE = "Executive Knowledge"


def knowledge_space_of(doc_department: str) -> str:
    """Map a document's owning department to its knowledge space."""
    if doc_department == COMPANY_DEPT:
        return COMPANY_KNOWLEDGE
    if doc_department == EXECUTIVE_DEPT:
        return EXECUTIVE_KNOWLEDGE
    return DEPARTMENT_KNOWLEDGE


@dataclass(frozen=True)
class Decision:
    """An access decision with a human-readable reason (for the audit trail)."""

    allowed: bool
    reason: str


def decide(
    role: str,
    user_department: str,
    classification: str,
    doc_department: str,
    matrix: dict[tuple[str, str], str] | None = None,
) -> Decision:
    """Decide whether a user (role, department) may access a document.

    Combines both axes of the dataset (the "3-gate" model):

    1. Knowledge space (Access control matrix): the role must be granted the
       document's space. Company Knowledge → all employees; Executive Knowledge →
       Executives only; Department Knowledge → the owning department (Executives
       see all departments).
    2. Department: for Department Knowledge, the user's department must match the
       document's.
    3. Classification (Permissions matrix): the role's classification permission
       must not be ``deny`` (Restricted → Executives only).

    ``user_department`` and ``doc_department`` are canonical ``dept_code`` values.
    """
    active = matrix or DEFAULT_MATRIX

    # Executive: full access — every knowledge space and every classification.
    if role == EXECUTIVE:
        return Decision(True, "executive: full access")

    space = knowledge_space_of(doc_department)

    # Gate 1 — Executive Knowledge is executive-only.
    if space == EXECUTIVE_KNOWLEDGE:
        return Decision(False, "executive knowledge: executive only")

    # Gate 3 — classification: Restricted (or any explicit deny) is blocked.
    effect = active.get((role, classification))
    if effect is None:
        return Decision(False, f"no rule for ({role}, {classification})")
    if effect == DENY:
        return Decision(False, f"{classification.lower()}: denied for {role.lower()}")

    # Gate 1 — Company Knowledge is available to all employees.
    if space == COMPANY_KNOWLEDGE:
        return Decision(True, "company knowledge: all employees")

    # Public is company-wide regardless of the owning department.
    if classification == "Public":
        return Decision(True, "public: all employees")

    # Gate 2 — Department Knowledge (Internal/Confidential): own department only.
    if user_department == doc_department:
        return Decision(True, f"{classification.lower()}: own department")
    return Decision(False, f"{classification.lower()}: other department")


def accessible_classifications(
    role: str, matrix: dict[tuple[str, str], str] | None = None
) -> set[str]:
    """Classifications this role can ever reach (own_department still dept-gated)."""
    active = matrix or DEFAULT_MATRIX
    return {
        cls
        for (r, cls), effect in active.items()
        if r == role and effect in (ALLOW, OWN_DEPARTMENT)
    }


def can_upload(role: str) -> bool:
    """Only Manager and above may publish documents."""
    return role in UPLOAD_ROLES
