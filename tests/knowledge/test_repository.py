# tests/knowledge/test_repository.py
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from minder.core.knowledge.repository import KnowledgeRepository
from minder.db.models import Base


@pytest.fixture
async def sm():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_create_find_and_status(sm):
    repo = KnowledgeRepository(sm)
    doc_id = await repo.create_document("t1", "reference_docs", "Doc", "hash1")
    found = await repo.find_document_by_hash("t1", "hash1")
    assert found["id"] == doc_id and found["status"] == "pending"
    await repo.set_status(doc_id, "ready")
    assert (await repo.find_document_by_hash("t1", "hash1"))["status"] == "ready"


@pytest.mark.asyncio
async def test_replace_chunks_and_delete_returns_point_ids(sm):
    repo = KnowledgeRepository(sm)
    doc_id = await repo.create_document("t1", "reference_docs", "Doc", "hash1")
    await repo.replace_chunks(
        doc_id, "t1", "reference_docs",
        [(0, "text a", "pt-0", "Doc [1] · 1#0"), (1, "text b", "pt-1", "Doc [1] · 1#1")],
    )
    point_ids = await repo.delete_document(doc_id)
    assert sorted(point_ids) == ["pt-0", "pt-1"]
    assert await repo.find_document_by_hash("t1", "hash1") is None


@pytest.mark.asyncio
async def test_pending_ids_and_tenant_isolation(sm):
    repo = KnowledgeRepository(sm)
    a = await repo.create_document("t1", "faq" if False else "reference_docs", "A", "h1")
    await repo.create_document("t2", "reference_docs", "B", "h2")
    pending = await repo.pending_document_ids(limit=10)
    assert a in pending
    assert [d["title"] for d in await repo.list_documents("t1")] == ["A"]
