"""PostgreSQL-backed user store for authentication."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from atria.db.connection import get_sessionmaker
from atria.db.repositories.user_repo import UserRepository
from atria.models.user import User


def _row_to_user(row: dict) -> User:
    return User(
        id=row["id"],
        username=row["display_name"] or row["email"].split("@")[0],
        email=row["email"],
        password_hash=row["password_hash"],
        created_at=row["created_at"],
        role=row["role"],
    )


class PgUserStore:
    """Async user store backed by PostgreSQL via SQLAlchemy."""

    def __init__(
        self,
        sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._sm: Optional[async_sessionmaker[AsyncSession]] = sessionmaker
        self._repo: Optional[UserRepository] = (
            None if sessionmaker is None else UserRepository(sessionmaker)
        )

    async def _get_repo(self) -> UserRepository:
        if self._repo is None:
            self._sm = await get_sessionmaker()
            self._repo = UserRepository(self._sm)
        return self._repo

    async def get_by_email(self, email: str) -> Optional[User]:
        row = await (await self._get_repo()).get_by_email(email)
        return _row_to_user(row) if row else None

    async def get_by_username(self, username: str) -> Optional[User]:
        row = await (await self._get_repo()).get_by_display_name(username)
        return _row_to_user(row) if row else None

    async def get_by_id(self, user_id: int) -> Optional[User]:
        row = await (await self._get_repo()).get_by_id(user_id)
        return _row_to_user(row) if row else None

    async def create_user(
        self,
        username: str,
        password_hash: str,
        *,
        email: str,
        role: str = "user",
    ) -> User:
        repo = await self._get_repo()
        row = await repo.create_user(
            display_name=username,
            email=email,
            password_hash=password_hash,
            role=role,
        )
        return _row_to_user(row)
