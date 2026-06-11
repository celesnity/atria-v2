"""Real-DB tests for ConversationRepository on SQLAlchemy ORM."""

from __future__ import annotations

import os
import pytest

from atria.db.connection import get_sessionmaker, init_schema, close_engine
from atria.db.repositories.conversation_repo import ConversationRepository
from atria.db.repositories.project_repo import ProjectRepository
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


async def test_create_then_get_by_id_roundtrip(sm):
    users = UserRepository(sm)
    projects = ProjectRepository(sm)
    convs = ConversationRepository(sm)
    uid = await users.upsert_by_email("orm-conv-1@atria.local")
    pid = await projects.get_or_create(uid, "p1")
    cid = await convs.create(pid, uid, "hi", "normal")
    row = await convs.get_by_id(cid)
    assert row is not None
    assert row["title"] == "hi"
    assert row["mode"] == "normal"
    assert row["status"] == "active"


async def test_list_by_project_includes_message_count(sm):
    users = UserRepository(sm)
    projects = ProjectRepository(sm)
    convs = ConversationRepository(sm)
    uid = await users.upsert_by_email("orm-conv-2@atria.local")
    pid = await projects.get_or_create(uid, "p2")
    await convs.create(pid, uid, "a", "normal")
    rows = await convs.list_by_project(pid)
    assert all("message_count" in r for r in rows)


async def test_update_partial_fields(sm):
    users = UserRepository(sm)
    convs = ConversationRepository(sm)
    uid = await users.upsert_by_email("orm-conv-3@atria.local")
    cid = await convs.create(None, uid, "old", "normal")
    await convs.update(cid, title="new")
    row = await convs.get_by_id(cid)
    assert row["title"] == "new"
    assert row["status"] == "active"


async def test_soft_delete_removes_from_lists(sm):
    users = UserRepository(sm)
    convs = ConversationRepository(sm)
    uid = await users.upsert_by_email("orm-conv-4@atria.local")
    cid = await convs.create(None, uid, "doomed", "normal")
    await convs.soft_delete(cid)
    assert await convs.get_by_id(cid) is None
