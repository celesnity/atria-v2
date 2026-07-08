"""Role/classification access control for enterprise documents.

Enforces the My Tasco P1 department-security model — the same one the
``ai_workspace`` module applies — combining two axes of the dataset:

1. Knowledge space (the Access-control matrix): a document's space is derived
   from its owning department. Company Knowledge (``COMP``) is company-wide;
   Executive Knowledge (``EXEC``) is executive-only; every other department is
   its own Department Knowledge, visible only to that department (Executives see
   all departments).
2. Classification (the Permissions matrix): Public/Internal never deny on the
   classification axis; Restricted is Executive-only; Confidential is limited to
   the owning department (Executives see all).

The same predicate powers a Qdrant pre-retrieval filter and a citation-time
re-check, so enforcement is defence-in-depth and unit-tested in isolation. A
cross-module parity test asserts these decisions match ``ai_workspace.access``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from identity import User  # type: ignore[import-not-found]

EXECUTIVE = "Executive"
PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED = (
    "Public",
    "Internal",
    "Confidential",
    "Restricted",
)
CLASSIFICATIONS = (PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED)

# Knowledge spaces, derived from the owning department (mirrors corpus.py).
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
    """An access decision with a human-readable reason."""

    allowed: bool
    reason: str


def can_access(user: User, doc: dict) -> Decision:
    """Decide whether ``user`` may access a document.

    Args:
        user: The resolved identity (``role`` and canonical ``department``).
        doc: A mapping carrying ``classification`` and ``department`` (canonical
            id). ``knowledge_space`` is used when present, else derived from
            ``department`` so graph candidates and bare doc dicts still decide
            correctly.

    Returns:
        A :class:`Decision` — advisory-quality reason included for the audit trail.
    """
    classification = str(doc.get("classification", ""))
    department = str(doc.get("department", ""))
    space = str(doc.get("knowledge_space", "")) or knowledge_space_of(department)

    # Executive: full access — every knowledge space and every classification.
    if user.role == EXECUTIVE:
        return Decision(True, "executive: full access")

    # Gate 1 — Executive Knowledge is executive-only, whatever the classification.
    if space == EXECUTIVE_KNOWLEDGE:
        return Decision(False, "executive knowledge: executive only")

    # Gate 3 — classification: Restricted is Executive-only.
    if classification == RESTRICTED:
        return Decision(False, "restricted: executive only")
    if classification not in (PUBLIC, INTERNAL, CONFIDENTIAL):
        return Decision(False, f"unknown classification: {classification!r}")

    # Gate 1 — Company Knowledge is available to all employees.
    if space == COMPANY_KNOWLEDGE:
        return Decision(True, "company knowledge: all employees")

    # Public is company-wide regardless of the owning department.
    if classification == PUBLIC:
        return Decision(True, "public: all employees")

    # Gate 2 — Department Knowledge (Internal/Confidential): own department only.
    if user.department == department:
        return Decision(True, f"{classification.lower()}: own department")
    return Decision(False, f"{classification.lower()}: other department")


def accessible_classifications(user: User) -> set[str]:
    """Classifications this user can ever access (dept/space gates still apply)."""
    if user.role == EXECUTIVE:
        return set(CLASSIFICATIONS)
    return {PUBLIC, INTERNAL, CONFIDENTIAL}


def build_filter(user: User):
    """Compile a Qdrant payload filter selecting only retrievable documents.

    Mirrors :func:`can_access` for non-executive users using the indexed
    ``knowledge_space``, ``classification`` and ``department`` payload fields:

    - Company Knowledge → all employees (any non-Restricted classification);
    - Department Knowledge + Public → company-wide;
    - Department Knowledge + Internal/Confidential → the owning department only.

    Executive Knowledge and Restricted documents match no clause, so they never
    enter the candidate set. Executives get ``None`` (no restriction).
    """
    from qdrant_client import models

    if user.role == EXECUTIVE:
        return None

    non_restricted = models.MatchAny(any=[PUBLIC, INTERNAL, CONFIDENTIAL])
    department_scoped = models.MatchAny(any=[INTERNAL, CONFIDENTIAL])
    return models.Filter(
        should=[
            # Company Knowledge — all employees (Restricted excluded).
            models.Filter(
                must=[
                    models.FieldCondition(
                        key="knowledge_space",
                        match=models.MatchValue(value=COMPANY_KNOWLEDGE),
                    ),
                    models.FieldCondition(key="classification", match=non_restricted),
                ]
            ),
            # Department Knowledge, Public — company-wide.
            models.Filter(
                must=[
                    models.FieldCondition(
                        key="knowledge_space",
                        match=models.MatchValue(value=DEPARTMENT_KNOWLEDGE),
                    ),
                    models.FieldCondition(
                        key="classification", match=models.MatchValue(value=PUBLIC)
                    ),
                ]
            ),
            # Department Knowledge, Internal/Confidential — own department only.
            models.Filter(
                must=[
                    models.FieldCondition(
                        key="knowledge_space",
                        match=models.MatchValue(value=DEPARTMENT_KNOWLEDGE),
                    ),
                    models.FieldCondition(
                        key="department",
                        match=models.MatchValue(value=user.department),
                    ),
                    models.FieldCondition(key="classification", match=department_scoped),
                ]
            ),
        ]
    )
