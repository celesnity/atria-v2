"""Integration tests for PgSessionManager — require DATABASE_URL."""

import os
import pytest
import asyncpg
import pytest_asyncio

pytestmark = pytest.mark.asyncio

DB_URL = os.environ.get("DATABASE_URL", "")


@pytest_asyncio.fixture(scope="module")
async def pool():
    if not DB_URL:
        pytest.skip("DATABASE_URL not set")
    p = await asyncpg.create_pool(DB_URL)
    yield p
    await p.close()


@pytest_asyncio.fixture
async def manager(pool):
    from atria.core.context_engineering.history.session_manager.pg_manager import PgSessionManager

    return PgSessionManager(pool=pool, working_directory="/tmp/test_atria")


async def test_create_and_load_session(manager):
    from atria.models.message import ChatMessage, Role

    session = await manager.create_session(working_directory="/tmp/test_atria")
    assert session.id.isdigit()

    msg = ChatMessage(role=Role.USER, content="hello")
    await manager.add_message(msg)
    await manager.save_session()

    loaded = await manager.load_session(session.id)
    assert len(loaded.messages) == 1
    assert loaded.messages[0].content == "hello"


async def test_list_sessions(manager):
    await manager.create_session(working_directory="/tmp/test_atria")
    sessions = await manager.list_sessions()
    assert len(sessions) >= 1


async def test_delete_session(manager):
    session = await manager.create_session(working_directory="/tmp/test_atria")
    await manager.save_session(force=True)
    sid = session.id
    await manager.delete_session(sid)
    with pytest.raises(FileNotFoundError):
        await manager.load_session(sid)
