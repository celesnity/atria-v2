"""CRUD for the projects table."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from atria.db.models import Conversation, Project
from atria.db.repositories.base import BaseRepository


def _flatten(model_instance) -> dict:
    return {c.name: getattr(model_instance, c.name) for c in model_instance.__table__.columns}


class ProjectRepository(BaseRepository):

    async def get_or_create(self, user_id: int, title: str) -> int:
        async with self._sessionmaker() as session:
            existing = await session.execute(
                select(Project.id).where(
                    Project.user_id == user_id,
                    Project.title == title,
                    Project.is_deleted.is_(False),
                )
            )
            row = existing.first()
            if row is not None:
                return int(row.id)
            stmt = (
                pg_insert(Project)
                .values(is_deleted=False, user_id=user_id, title=title, pinned=False)
                .returning(Project.id)
            )
            result = await session.execute(stmt)
            new_id = int(result.scalar_one())
            await session.commit()
            return new_id

    async def create(self, user_id: int, title: str, workspace_path: str) -> int:
        async with self._sessionmaker() as session:
            stmt = (
                pg_insert(Project)
                .values(
                    is_deleted=False,
                    user_id=user_id,
                    title=title,
                    pinned=False,
                    workspace_path=workspace_path,
                )
                .returning(Project.id)
            )
            result = await session.execute(stmt)
            new_id = int(result.scalar_one())
            await session.commit()
            return new_id

    async def list_by_user(self, user_id: int) -> list[dict]:
        async with self._sessionmaker() as session:
            stmt = (
                select(
                    Project,
                    func.count(Conversation.id)
                    .filter(Conversation.is_deleted.is_(False))
                    .label("conversation_count"),
                )
                .outerjoin(Conversation, Conversation.project_id == Project.id)
                .where(Project.user_id == user_id, Project.is_deleted.is_(False))
                .group_by(Project.id)
                .order_by(Project.created_at.desc())
            )
            result = await session.execute(stmt)
            rows: list[dict] = []
            for project, count in result.all():
                row = _flatten(project)
                row["conversation_count"] = int(count or 0)
                rows.append(row)
            return rows

    async def get_by_id(self, project_id: int) -> Optional[dict]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(Project).where(Project.id == project_id, Project.is_deleted.is_(False))
            )
            obj = result.scalars().first()
            return _flatten(obj) if obj else None

    async def get_by_id_and_user(self, project_id: int, user_id: int) -> Optional[dict]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(Project).where(
                    Project.id == project_id,
                    Project.user_id == user_id,
                    Project.is_deleted.is_(False),
                )
            )
            obj = result.scalars().first()
            return _flatten(obj) if obj else None

    async def soft_delete(self, project_id: int, user_id: int) -> bool:
        async with self._sessionmaker() as session:
            stmt = (
                update(Project)
                .where(Project.id == project_id, Project.user_id == user_id)
                .values(is_deleted=True, updated_at=func.now())
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def backfill_workspace_path(self, project_id: int, workspace_path: str) -> None:
        """Set `workspace_path` only when it is currently NULL or empty."""
        async with self._sessionmaker() as session:
            stmt = (
                update(Project)
                .where(
                    Project.id == project_id,
                    or_(Project.workspace_path.is_(None), Project.workspace_path == ""),
                )
                .values(workspace_path=workspace_path)
            )
            await session.execute(stmt)
            await session.commit()
