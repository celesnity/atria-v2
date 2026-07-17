import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("KNOWLEDGE_IT") != "1",
    reason="integration test; set KNOWLEDGE_IT=1 with Qdrant+Postgres+Neo4j up",
)


@pytest.mark.asyncio
async def test_seed_ingest_then_query_is_tenant_scoped():
    from minder.core.knowledge.repository import KnowledgeRepository
    from minder.core.knowledge.seed import scan_seed_dir
    from minder.core.knowledge.wiring import build_knowledge_service
    from minder.db.connection import get_sessionmaker, init_schema

    await init_schema()
    sm = await get_sessionmaker()
    repo = KnowledgeRepository(sm)

    root = os.path.join(os.path.dirname(__file__), "fixtures")
    await scan_seed_dir(root, repo)
    service = build_knowledge_service()
    await service.drain_queue(batch=50)

    docs = await service.list_documents("dev")
    assert any(d["status"] == "ready" for d in docs)
    # tenant isolation: a different tenant sees nothing
    assert await service.list_documents("other-tenant") == []
