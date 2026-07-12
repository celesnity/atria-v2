"""Business logic for projects and their conversations.

Owns workspace-path resolution, ownership checks, and the session-manager
orchestration that creating/deleting a conversation requires. Routes call these
methods and return the results verbatim.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from minder.core.services.errors import ServiceError
from minder.core.workspace.manager import (
    conversation_path,
    ensure_path,
    project_path,
    slugify,
)
from minder.db.repositories.conversation_repo import ConversationRepository
from minder.db.repositories.project_repo import ProjectRepository
from minder.models.user import User


def _user_slug(user: User) -> str:
    name = (user.username or "").strip() or user.email.split("@")[0]
    return slugify(name)


class ProjectService:
    """Use cases for the projects/conversations resource."""

    def __init__(self, sessionmaker: Any, session_manager: Any) -> None:
        self._projects = ProjectRepository(sessionmaker)
        self._conversations = ConversationRepository(sessionmaker)
        self._sessions = session_manager

    async def list_projects(self, user: User) -> list[dict]:
        rows = await self._projects.list_by_user(user.id)
        return [
            {
                "id": str(row["id"]),
                "name": row["title"],
                "workspace_path": row["workspace_path"] or "",
                "created_at": row["created_at"].isoformat(),
                "conversation_count": row["conversation_count"],
            }
            for row in rows
        ]

    async def create_project(self, user: User, name: str) -> dict:
        name = name.strip()
        if not name:
            raise ServiceError.invalid("Project name cannot be empty")

        path = project_path(_user_slug(user), name)
        ensure_path(path)

        project_id = await self._projects.create(
            user_id=user.id, title=name, workspace_path=str(path)
        )
        return {
            "id": str(project_id),
            "name": name,
            "workspace_path": str(path),
            "created_at": None,
            "conversation_count": 0,
        }

    async def delete_project(self, user: User, project_id: int) -> None:
        deleted = await self._projects.soft_delete(project_id, user.id)
        if not deleted:
            raise ServiceError.not_found("Project not found")

    async def list_conversations(self, user: User, project_id: int) -> list[dict]:
        await self._require_owned_project(user, project_id)
        rows = await self._conversations.list_by_project(project_id)
        return [
            {
                "id": str(row["id"]),
                "name": row["title"] or f"Conversation {row['id']}",
                "project_id": str(project_id),
                "working_directory": row["working_directory"] or "",
                "message_count": row["message_count"],
                "created_at": row["created_at"].isoformat(),
                "updated_at": (row["updated_at"] or row["created_at"]).isoformat(),
            }
            for row in rows
        ]

    async def create_conversation(self, user: User, project_id: int, name: str) -> dict:
        name = name.strip()
        if not name:
            raise ServiceError.invalid("Conversation name cannot be empty")

        project = await self._require_owned_project(user, project_id)
        workspace = project["workspace_path"]
        if not workspace:
            raise ServiceError.bad_request("Project has no workspace path")

        conv_dir = conversation_path(Path(workspace), name)
        ensure_path(conv_dir)

        session = await self._sessions.create_session(
            working_directory=str(conv_dir),
            channel="web",
            owner_id=str(user.id),
            project_id=project_id,
            user_id=user.id,
        )
        await self._sessions.set_title(session.id, name)
        await self._sessions.save_session(force=True)

        return {
            "id": session.id,
            "name": name,
            "project_id": str(project_id),
            "working_directory": str(conv_dir),
            "message_count": 0,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
        }

    async def delete_conversation(self, user: User, project_id: int, conversation_id: str) -> None:
        await self._require_owned_project(user, project_id)
        await self._sessions.delete_session(conversation_id)

    async def _require_owned_project(self, user: User, project_id: int) -> dict:
        project = await self._projects.get_by_id_and_user(project_id, user.id)
        if not project:
            raise ServiceError.not_found("Project not found")
        return project
