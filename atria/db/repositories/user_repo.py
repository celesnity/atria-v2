"""CRUD for the users table."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping

from atria.db.models import User
from atria.db.repositories.base import BaseRepository


class UserRepository(BaseRepository):

    async def upsert_by_email(self, email: str) -> int:
        """Insert a user row if it doesn't exist; return its id."""
        async with self._sessionmaker() as session:
            existing = await session.execute(
                select(User.id).where(User.email == email, User.is_deleted.is_(False))
            )
            row = existing.first()
            if row is not None:
                return int(row.id)
            stmt = (
                pg_insert(User)
                .values(
                    is_deleted=False,
                    email=email,
                    role="admin",
                    failed_login_attempts=0,
                    is_active=True,
                    email_verified=False,
                )
                .returning(User.id)
            )
            result = await session.execute(stmt)
            new_id = int(result.scalar_one())
            await session.commit()
            return new_id

    async def get_by_id(self, user_id: int) -> Optional[RowMapping]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(User).where(User.id == user_id, User.is_deleted.is_(False))
            )
            row = result.mappings().first()
            return self._flatten(row) if row else None

    async def get_by_email(self, email: str) -> Optional[RowMapping]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(User).where(User.email == email, User.is_deleted.is_(False))
            )
            row = result.mappings().first()
            return self._flatten(row) if row else None

    async def get_by_display_name(self, display_name: str) -> Optional[RowMapping]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(User).where(User.display_name == display_name, User.is_deleted.is_(False))
            )
            row = result.mappings().first()
            return self._flatten(row) if row else None

    async def create_user(
        self,
        display_name: str,
        email: str,
        password_hash: str = "",
        role: str = "user",
    ) -> RowMapping:
        async with self._sessionmaker() as session:
            stmt = (
                pg_insert(User)
                .values(
                    is_deleted=False,
                    email=email,
                    display_name=display_name,
                    password_hash=password_hash or None,
                    role=role,
                    failed_login_attempts=0,
                    is_active=True,
                    email_verified=False,
                )
                .returning(User)
            )
            result = await session.execute(stmt)
            row = result.mappings().one()
            await session.commit()
            return self._flatten(row)

    @staticmethod
    def _flatten(mapping) -> dict:
        """Return a plain dict view of a row keyed by column name."""
        if hasattr(mapping, "keys") and len(mapping.keys()) == 1:
            only_key = next(iter(mapping.keys()))
            obj = mapping[only_key]
            if hasattr(obj, "__table__"):
                return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
        return dict(mapping)
