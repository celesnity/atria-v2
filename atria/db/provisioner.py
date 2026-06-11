"""Auto-provision the default user and project rows on startup."""

from __future__ import annotations

import os
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from atria.db.repositories.project_repo import ProjectRepository
from atria.db.repositories.user_repo import UserRepository

_DEFAULT_EMAIL = "default@atria.local"


async def provision(
    sessionmaker: async_sessionmaker[AsyncSession],
    working_directory: Optional[str] = None,
) -> tuple[int, int]:
    """Ensure the default user and a project row exist.

    Returns:
        (user_id, project_id) — both integers from the DB.
    """
    email = os.environ.get("ATRIA_USER_EMAIL", _DEFAULT_EMAIL)
    user_repo = UserRepository(sessionmaker)
    project_repo = ProjectRepository(sessionmaker)

    user_id = await user_repo.upsert_by_email(email)
    title = working_directory or os.getcwd()
    project_id = await project_repo.get_or_create(user_id=user_id, title=title)

    return user_id, project_id
