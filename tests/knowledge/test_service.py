import pytest

from minder.core.knowledge.service import KnowledgeService


class FakeRepo:
    def __init__(self):
        self.created = []
        self.pending = [1, 2]
        self.status = {}

    async def create_document(self, tenant_id, category, title, content_hash, **kw):
        self.created.append((tenant_id, category))
        return len(self.created)

    async def pending_document_ids(self, limit=5):
        out, self.pending = self.pending[:limit], self.pending[limit:]
        return out

    async def set_status(self, document_id, status, *, error=None):
        self.status[document_id] = status


class FakeIngestion:
    def __init__(self):
        self.done = []

    async def ingest_document(self, document_id):
        self.done.append(document_id)


@pytest.mark.asyncio
async def test_register_upload_validates_category():
    svc = KnowledgeService(FakeRepo(), FakeIngestion())
    with pytest.raises(ValueError):
        await svc.register_upload("t1", "bogus", "T", "h", artifact_id=7)
    doc_id = await svc.register_upload("t1", "reference_docs", "T", "h", artifact_id=7)
    assert doc_id == 1


@pytest.mark.asyncio
async def test_drain_processes_pending_batch():
    repo, ing = FakeRepo(), FakeIngestion()
    svc = KnowledgeService(repo, ing)
    count = await svc.drain_queue(batch=5)
    assert count == 2 and ing.done == [1, 2]
