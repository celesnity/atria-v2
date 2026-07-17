import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from minder.db.models import Base, KnowledgeChunk, KnowledgeDocument


@pytest.mark.asyncio
async def test_document_and_chunk_roundtrip():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        doc = KnowledgeDocument(
            tenant_id="t1",
            category="reference_docs",
            title="Policy",
            content_hash="abc",
            status="pending",
        )
        s.add(doc)
        await s.flush()
        s.add(
            KnowledgeChunk(
                document_id=doc.id,
                tenant_id="t1",
                category="reference_docs",
                chunk_index=0,
                text="hello",
                citation="Policy [1] · 1#0",
            )
        )
        await s.commit()
        assert doc.id is not None
        assert doc.status == "pending"

    # M2: read the chunk back to verify FK linkage and chunk persistence.
    async with sm() as s:
        result = await s.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id)
        )
        chunk = result.scalar_one()
        assert chunk.text == "hello"
        assert chunk.citation == "Policy [1] · 1#0"
