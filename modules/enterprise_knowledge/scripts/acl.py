"""Role/classification access control for enterprise documents.

Encodes the classification × role matrix from the dataset's Permissions sheet:
Public/Internal are open to all employees; Restricted is Executive-only;
Confidential is limited to the owning department (Executives see all). The same
predicate powers a Qdrant pre-retrieval filter and a citation-time re-check, so
enforcement is defence-in-depth and unit-tested in isolation.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import sibling  # noqa: E402

User = sibling("identity").User

EXECUTIVE = "Executive"
PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED = (
    "Public", "Internal", "Confidential", "Restricted",
)
CLASSIFICATIONS = (PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED)


@dataclass(frozen=True)
class Decision:
    """An access decision with a human-readable reason."""

    allowed: bool
    reason: str


def can_access(user: User, doc: dict) -> Decision:
    """Decide whether ``user`` may access a document.

    Args:
        user: The resolved identity.
        doc: A mapping carrying ``classification`` and ``department`` (canonical id).

    Returns:
        A :class:`Decision` — advisory-quality reason included for the audit trail.
    """
    classification = str(doc.get("classification", ""))
    doc_department = str(doc.get("department", ""))
    if classification in (PUBLIC, INTERNAL):
        return Decision(True, f"{classification.lower()}: all employees")
    if classification == RESTRICTED:
        if user.role == EXECUTIVE:
            return Decision(True, "restricted: executive")
        return Decision(False, "restricted: executive only")
    if classification == CONFIDENTIAL:
        if user.role == EXECUTIVE:
            return Decision(True, "confidential: executive sees all departments")
        if user.department == doc_department:
            return Decision(True, "confidential: own department")
        return Decision(False, "confidential: other department")
    return Decision(False, f"unknown classification: {classification!r}")


def accessible_classifications(user: User) -> set[str]:
    """Classifications this user can ever access (Confidential still dept-gated)."""
    if user.role == EXECUTIVE:
        return set(CLASSIFICATIONS)
    return {PUBLIC, INTERNAL, CONFIDENTIAL}


def build_filter(user: User):
    """Compile a Qdrant payload filter selecting only retrievable documents.

    Executive → ``None`` (no restriction; sees everything). Everyone else →
    Public OR Internal OR (Confidential AND department == the user's). Restricted
    documents match no clause, so they never enter the candidate set.
    """
    from qdrant_client import models

    if user.role == EXECUTIVE:
        return None
    return models.Filter(
        should=[
            models.FieldCondition(
                key="classification", match=models.MatchValue(value=PUBLIC)
            ),
            models.FieldCondition(
                key="classification", match=models.MatchValue(value=INTERNAL)
            ),
            models.Filter(
                must=[
                    models.FieldCondition(
                        key="classification",
                        match=models.MatchValue(value=CONFIDENTIAL),
                    ),
                    models.FieldCondition(
                        key="department",
                        match=models.MatchValue(value=user.department),
                    ),
                ]
            ),
        ]
    )
