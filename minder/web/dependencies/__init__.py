"""FastAPI dependency providers."""

from minder.web.dependencies.auth import require_authenticated_user
from minder.web.dependencies.modules import get_modules_registry
from minder.web.dependencies.workspace import require_workspace, ensure_user_workspace

__all__ = [
    "require_authenticated_user",
    "require_workspace",
    "ensure_user_workspace",
    "get_modules_registry",
]
