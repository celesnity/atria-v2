"""Real-DB tests for ProjectRepository on SQLAlchemy ORM."""

from __future__ import annotations

import os
import pytest

from atria.db.connection import get_sessionmaker, init_schema, close_engine
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


async def test_get_or_create_is_idempotent(sm):
    users = UserRepository(sm)
    projects = ProjectRepository(sm)
    uid = await users.upsert_by_email("orm-project-1@atria.local")
    a = await projects.get_or_create(uid, "title-A")
    b = await projects.get_or_create(uid, "title-A")
    assert a == b


async def test_list_by_user_includes_conversation_count(sm):
    users = UserRepository(sm)
    projects = ProjectRepository(sm)
    uid = await users.upsert_by_email("orm-project-2@atria.local")
    pid = await projects.get_or_create(uid, "with-counts")
    rows = await projects.list_by_user(uid)
    project = next(r for r in rows if r["id"] == pid)
    assert "conversation_count" in project
    assert project["conversation_count"] == 0


async def test_soft_delete_returns_true_when_row_updated(sm):
    users = UserRepository(sm)
    projects = ProjectRepository(sm)
    uid = await users.upsert_by_email("orm-project-3@atria.local")
    pid = await projects.create(uid, "to-delete", "/tmp/x")
    assert await projects.soft_delete(pid, uid) is True
    assert await projects.soft_delete(pid, uid) is False


async def test_backfill_workspace_path_only_when_missing(sm):
    users = UserRepository(sm)
    projects = ProjectRepository(sm)
    uid = await users.upsert_by_email("orm-project-4@atria.local")
    pid = await projects.get_or_create(uid, "no-ws")
    await projects.backfill_workspace_path(pid, "/tmp/ws1")
    after = await projects.get_by_id(pid)
    assert after["workspace_path"] == "/tmp/ws1"
    await projects.backfill_workspace_path(pid, "/tmp/ws2")
    final = await projects.get_by_id(pid)
    assert final["workspace_path"] == "/tmp/ws1"
