"""Real-DB tests for ArtifactRepository on SQLAlchemy ORM."""

from __future__ import annotations

import os
import pytest

from atria.db.connection import get_sessionmaker, init_schema, close_engine
from atria.db.repositories.artifact_repo import ArtifactRepository
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


async def _ctx(sm):
    users = UserRepository(sm)
    projects = ProjectRepository(sm)
    convs = ConversationRepository(sm)
    uid = await users.upsert_by_email("orm-art@atria.local")
    pid = await projects.get_or_create(uid, "art-project")
    cid = await convs.create(pid, uid, "art-conv", "normal")
    return pid, cid


async def test_create_and_get_roundtrip(sm):
    pid, cid = await _ctx(sm)
    repo = ArtifactRepository(sm)
    aid = await repo.create(
        project_id=pid,
        type="file",
        conversation_id=cid,
        title="hello.txt",
        payload_ref="/tmp/hello.txt",
        preview={"snippet": "hello"},
    )
    row = await repo.get_by_id(aid)
    assert row is not None
    assert row["title"] == "hello.txt"
    assert row["preview"] == {"snippet": "hello"}


async def test_upsert_by_ref_is_idempotent(sm):
    pid, cid = await _ctx(sm)
    repo = ArtifactRepository(sm)
    a = await repo.upsert_by_ref(pid, cid, "/tmp/x.md", "file")
    b = await repo.upsert_by_ref(pid, cid, "/tmp/x.md", "file")
    assert a == b


async def test_soft_delete_idempotent(sm):
    pid, cid = await _ctx(sm)
    repo = ArtifactRepository(sm)
    aid = await repo.create(project_id=pid, type="file", conversation_id=cid)
    assert await repo.soft_delete(aid) is True
    assert await repo.soft_delete(aid) is False
