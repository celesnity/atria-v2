"""CRUD for the conversations table."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from atria.db.models import Conversation, Message
from atria.db.repositories.base import BaseRepository


def _flatten(model_instance) -> dict:
    return {c.name: getattr(model_instance, c.name) for c in model_instance.__table__.columns}


class ConversationRepository(BaseRepository):

    async def create(
        self,
        project_id: Optional[int],
        user_id: Optional[int],
        title: Optional[str],
        mode: str,
        working_directory: Optional[str] = None,
    ) -> int:
        async with self._sessionmaker() as session:
            stmt = (
                pg_insert(Conversation)
                .values(
                    is_deleted=False,
                    project_id=project_id,
                    user_id=user_id,
                    title=title,
                    mode=mode[:10],
                    status="active",
                    working_directory=working_directory,
                )
                .returning(Conversation.id)
            )
            result = await session.execute(stmt)
            new_id = int(result.scalar_one())
            await session.commit()
            return new_id

    async def list_personal(self, user_id: Optional[int] = None) -> list[dict]:
        async with self._sessionmaker() as session:
            stmt = (
                select(
                    Conversation,
                    func.count(Message.id)
                    .filter(Message.is_deleted.is_(False))
                    .label("message_count"),
                )
                .outerjoin(Message, Message.conversation_id == Conversation.id)
                .where(
                    Conversation.project_id.is_(None),
                    Conversation.is_deleted.is_(False),
                )
                .group_by(Conversation.id)
                .order_by(
                    Conversation.updated_at.desc().nulls_last(),
                    Conversation.created_at.desc(),
                )
            )
            return await self._rows_with_count(session, stmt)

    async def get_by_id(
        self,
        conversation_id: int,
        user_id: Optional[int] = None,
    ) -> Optional[dict]:
        async with self._sessionmaker() as session:
            stmt = select(Conversation).where(
                Conversation.id == conversation_id, Conversation.is_deleted.is_(False)
            )
            if user_id is not None:
                stmt = stmt.where(Conversation.user_id == user_id)
            result = await session.execute(stmt)
            obj = result.scalars().first()
            return _flatten(obj) if obj else None

    async def update(
        self,
        conversation_id: int,
        title: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        values: dict = {"updated_at": func.now()}
        if title is not None:
            values["title"] = title
        if status is not None:
            values["status"] = status
        async with self._sessionmaker() as session:
            await session.execute(
                update(Conversation).where(Conversation.id == conversation_id).values(**values)
            )
            await session.commit()

    async def soft_delete(self, conversation_id: int) -> None:
        async with self._sessionmaker() as session:
            await session.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(is_deleted=True, updated_at=func.now())
            )
            await session.commit()

    async def list_by_project(self, project_id: int) -> list[dict]:
        async with self._sessionmaker() as session:
            stmt = (
                select(
                    Conversation,
                    func.count(Message.id)
                    .filter(Message.is_deleted.is_(False))
                    .label("message_count"),
                )
                .outerjoin(Message, Message.conversation_id == Conversation.id)
                .where(
                    Conversation.project_id == project_id,
                    Conversation.is_deleted.is_(False),
                )
                .group_by(Conversation.id)
                .order_by(
                    Conversation.updated_at.desc().nulls_last(),
                    Conversation.created_at.desc(),
                )
            )
            return await self._rows_with_count(session, stmt)

    async def list_all(self, user_id: Optional[int] = None) -> list[dict]:
        async with self._sessionmaker() as session:
            stmt = select(Conversation).where(Conversation.is_deleted.is_(False))
            if user_id is not None:
                stmt = stmt.where(Conversation.user_id == user_id)
            stmt = stmt.order_by(
                func.coalesce(Conversation.updated_at, Conversation.created_at).desc()
            )
            result = await session.execute(stmt)
            return [_flatten(obj) for obj in result.scalars().all()]

    @staticmethod
    async def _rows_with_count(session, stmt) -> list[dict]:
        result = await session.execute(stmt)
        rows: list[dict] = []
        for conv, count in result.all():
            row = _flatten(conv)
            row["message_count"] = int(count or 0)
            rows.append(row)
        return rows
