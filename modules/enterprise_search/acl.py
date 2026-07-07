"""Track 1 permission matrix, enforced at retrieval time on both recall paths.

Rules (dataset Permissions sheet):
    Public, Internal -> every authenticated employee.
    Confidential     -> only the owning department; Executive sees all.
    Restricted       -> Executive only.

Identity is injected by the runtime (SearchContext), never by the model.
Unknown identity degrades to the most restrictive non-executive view.
"""

from __future__ import annotations

from qdrant_client import models

OPEN_CLASSIFICATIONS = ("Public", "Internal")


def is_allowed(
    role: str, department: str | None, doc_classification: str, doc_department: str
) -> bool:
    """Reference predicate for the permission matrix (source of truth).

    Determines whether a user with the given role and department can access
    a document based on its classification and owning department.

    Args:
        role: User's role (Employee, Manager, Director, Executive).
        department: User's department, or None/empty string if unknown. An
            empty or blank string is treated the same as unknown (None) and
            denies access to Confidential documents.
        doc_classification: Document classification (Public, Internal,
            Confidential, Restricted).
        doc_department: Document's owning department.

    Returns:
        True if access is allowed, False otherwise.
    """
    if role == "Executive":
        return True
    if doc_classification in OPEN_CLASSIFICATIONS:
        return True
    if doc_classification == "Confidential":
        return bool(department) and department == doc_department
    return False  # Restricted (and anything unknown) is executive-only


def allowed_clause(role: str, department_param: int) -> str:
    """SQL predicate over columns (classification, department).

    For non-executives the caller must bind the user's department (or empty
    string when unknown) at position $<department_param>.

    Args:
        role: User's role (Employee, Manager, Director, Executive).
        department_param: Position index for the SQL parameter binding.

    Returns:
        SQL fragment (boolean expression) to use in WHERE clause.
    """
    if role == "Executive":
        return "TRUE"
    return (
        "(classification IN ('Public','Internal') "
        f"OR (classification = 'Confidential' AND department = ${department_param}))"
    )


def qdrant_acl_filter(role: str, department: str | None) -> models.Filter | None:
    """Equivalent payload filter for the dense recall path (None = no filter).

    Constructs a Qdrant filter object for access control on vector similarity
    search. Returns None for unrestricted access (Executive role).

    Args:
        role: User's role (Employee, Manager, Director, Executive).
        department: User's department or None if unknown.

    Returns:
        Qdrant Filter object for non-executives, None (unrestricted) for
        Executive.
    """
    if role == "Executive":
        return None
    branches: list[models.Condition] = [
        models.FieldCondition(
            key="classification", match=models.MatchAny(any=list(OPEN_CLASSIFICATIONS))
        )
    ]
    if department:
        branches.append(
            models.Filter(
                must=[
                    models.FieldCondition(
                        key="classification",
                        match=models.MatchValue(value="Confidential"),
                    ),
                    models.FieldCondition(
                        key="department", match=models.MatchValue(value=department)
                    ),
                ]
            )
        )
    return models.Filter(should=branches)
