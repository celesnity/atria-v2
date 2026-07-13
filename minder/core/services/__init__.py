"""Application service layer.

Services sit between the web/API layer and the database repositories. They own
business rules (ownership checks, validation), cross-repository orchestration,
and response-shaping — keeping HTTP handlers thin and repositories pure CRUD.

Services never import from ``minder.web`` and never raise ``HTTPException``; they
signal failure with :class:`~minder.core.services.errors.ServiceError`, which the
web layer maps to an HTTP response.
"""

from minder.core.services.errors import ServiceError

__all__ = ["ServiceError"]
