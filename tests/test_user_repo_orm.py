"""Real-DB tests for UserRepository running on SQLAlchemy ORM."""

from __future__ import annotations

import os
import pytest

from atria.db.connection import get_sessionmaker, init_schema, close_engine
from atria.db.repositories.user_repo import UserRepository


pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL required for real-Postgres ORM tests",
)


@pytest.fixture
async def sm():
    await init_schema()
    sm = await get_sessionmaker()
    yield sm
    await close_engine()


async def test_upsert_by_email_creates_and_returns_same_id(sm):
    repo = UserRepository(sm)
    a = await repo.upsert_by_email("orm-test-1@atria.local")
    b = await repo.upsert_by_email("orm-test-1@atria.local")
    assert a == b
    assert isinstance(a, int)


async def test_get_by_email_returns_mapping(sm):
    repo = UserRepository(sm)
    uid = await repo.upsert_by_email("orm-test-2@atria.local")
    row = await repo.get_by_email("orm-test-2@atria.local")
    assert row is not None
    assert row["id"] == uid
    assert row["email"] == "orm-test-2@atria.local"


async def test_get_by_id_missing_returns_none(sm):
    repo = UserRepository(sm)
    assert await repo.get_by_id(987654321) is None


async def test_create_user_returns_dict_view(sm):
    repo = UserRepository(sm)
    row = await repo.create_user(
        display_name="orm_display",
        email="orm-test-3@atria.local",
        password_hash="hash",
        role="user",
    )
    assert row["display_name"] == "orm_display"
    assert row["email"] == "orm-test-3@atria.local"
