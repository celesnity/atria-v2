"""Integration tests — require a real Postgres instance via DATABASE_URL."""

import os
import pytest
import pytest_asyncio
import asyncpg

pytestmark = pytest.mark.asyncio

DB_URL = os.environ.get("DATABASE_URL", "")


@pytest_asyncio.fixture(scope="module")
async def pool():
    if not DB_URL:
        pytest.skip("DATABASE_URL not set")
    p = await asyncpg.create_pool(DB_URL)
    yield p
    await p.close()


async def test_upsert_default_user(pool):
    from atria.db.repositories.user_repo import UserRepository

    repo = UserRepository(pool)
    uid = await repo.upsert_by_email("test@example.com")
    assert isinstance(uid, int)
    # idempotent
    uid2 = await repo.upsert_by_email("test@example.com")
    assert uid == uid2


async def test_get_or_create_project(pool):
    from atria.db.repositories.user_repo import UserRepository
    from atria.db.repositories.project_repo import ProjectRepository

    uid = await UserRepository(pool).upsert_by_email("projtest@example.com")
    repo = ProjectRepository(pool)
    pid = await repo.get_or_create(user_id=uid, title="/workspace/myproject")
    assert isinstance(pid, int)
    # idempotent
    pid2 = await repo.get_or_create(user_id=uid, title="/workspace/myproject")
    assert pid == pid2


async def test_conversation_crud(pool):
    from atria.db.repositories.user_repo import UserRepository
    from atria.db.repositories.project_repo import ProjectRepository
    from atria.db.repositories.conversation_repo import ConversationRepository

    uid = await UserRepository(pool).upsert_by_email("convtest@example.com")
    pid = await ProjectRepository(pool).get_or_create(uid, "/workspace/conv")
    repo = ConversationRepository(pool)

    cid = await repo.create(project_id=pid, user_id=uid, title="Test conv", mode="cli")
    assert isinstance(cid, int)

    row = await repo.get_by_id(cid)
    assert row["title"] == "Test conv"
    assert row["mode"] == "cli"
    assert row["status"] == "active"

    await repo.update(cid, title="Updated")
    row = await repo.get_by_id(cid)
    assert row["title"] == "Updated"

    rows = await repo.list_by_project(pid)
    assert any(r["id"] == cid for r in rows)

    await repo.soft_delete(cid)
    row = await repo.get_by_id(cid)
    assert row is None


async def test_message_insert_and_list(pool):
    from atria.db.repositories.user_repo import UserRepository
    from atria.db.repositories.project_repo import ProjectRepository
    from atria.db.repositories.conversation_repo import ConversationRepository
    from atria.db.repositories.message_repo import MessageRepository
    from atria.models.message import ChatMessage, Role

    uid = await UserRepository(pool).upsert_by_email("msgtest@example.com")
    pid = await ProjectRepository(pool).get_or_create(uid, "/workspace/msgs")
    cid = await ConversationRepository(pool).create(pid, uid, "msg test", "cli")

    msg = ChatMessage(role=Role.USER, content="hello world")
    repo = MessageRepository(pool)
    mid = await repo.insert(conversation_id=cid, message=msg, mode="normal")
    assert isinstance(mid, int)

    messages = await repo.list_by_conversation(cid)
    assert len(messages) == 1
    restored = messages[0]
    assert restored.role == Role.USER
    assert restored.content == "hello world"


async def test_message_blocks_with_tool_calls(pool):
    from atria.db.repositories.user_repo import UserRepository
    from atria.db.repositories.project_repo import ProjectRepository
    from atria.db.repositories.conversation_repo import ConversationRepository
    from atria.db.repositories.message_repo import MessageRepository
    from atria.models.message import ChatMessage, Role, ToolCall

    uid = await UserRepository(pool).upsert_by_email("tooltest@example.com")
    pid = await ProjectRepository(pool).get_or_create(uid, "/workspace/tools")
    cid = await ConversationRepository(pool).create(pid, uid, "tool test", "cli")

    tc = ToolCall(id="call_abc", name="bash", parameters={"command": "ls"}, result="file.txt")
    msg = ChatMessage(
        role=Role.ASSISTANT,
        content="I ran bash",
        thinking_trace="I should run bash",
        tool_calls=[tc],
    )
    repo = MessageRepository(pool)
    mid = await repo.insert(conversation_id=cid, message=msg, mode="normal")

    messages = await repo.list_by_conversation(cid)
    restored = messages[0]
    assert restored.thinking_trace == "I should run bash"
    assert len(restored.tool_calls) == 1
    assert restored.tool_calls[0].name == "bash"
