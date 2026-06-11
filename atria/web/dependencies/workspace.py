"""Per-user workspace resolution + auto-provisioning.

Each authenticated user owns one workspace directory
(``~/.atria/workspaces/user-<id>``) and a matching row in the ``projects``
table. The directory is the agent's default working directory; the
project row groups the user's conversations.

Both are idempotently provisioned on first access via
:func:`ensure_user_workspace`, so the very first call after a login (or
after a fresh install) creates them. Subsequent calls are cheap lookups.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends

from atria.core.workspace.manager import ensure_path, workspace_base
from atria.db.connection import get_sessionmaker
from atria.db.repositories.project_repo import ProjectRepository
from atria.models.user import User
from atria.web.dependencies.auth import require_authenticated_user


@dataclass(frozen=True)
class UserWorkspace:
    user_id: int
    project_id: int
    workspace_path: Path


def workspace_dir_for(user_id: int) -> Path:
    """Return the canonical workspace path for a user id (not created)."""
    return workspace_base() / f"user-{user_id}"


async def ensure_user_workspace(user_id: int) -> UserWorkspace:
    """Create the workspace directory and project row if missing."""
    workspace_path = ensure_path(workspace_dir_for(user_id))
    workspace_str = str(workspace_path)
    sm = await get_sessionmaker()
    project_repo = ProjectRepository(sm)
    project_id = await project_repo.get_or_create(user_id=user_id, title=workspace_str)
    await project_repo.backfill_workspace_path(project_id, workspace_str)
    return UserWorkspace(
        user_id=user_id,
        project_id=project_id,
        workspace_path=workspace_path,
    )


async def require_workspace(
    user: User = Depends(require_authenticated_user),
) -> UserWorkspace:
    """FastAPI dependency: resolve (and lazily create) the caller's workspace."""
    return await ensure_user_workspace(user.id)
