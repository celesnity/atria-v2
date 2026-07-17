import pytest

from minder.core.knowledge.ingestion import IngestionService


class FakeRepo:
    def __init__(self, doc):
        self.doc = doc
        self.status = []
        self.chunks = None
        self.summary = None

    async def get_document(self, document_id):
        return self.doc

    async def set_status(self, document_id, status, *, error=None):
        self.status.append((status, error))

    async def replace_chunks(self, document_id, tenant_id, category, chunks):
        self.chunks = chunks

    async def set_summary(self, document_id, summary):
        self.summary = summary


class FakeEmbedder:
    def __init__(self):
        self.indexed = None

    def index_chunks(self, ids, texts, payloads):
        self.indexed = (ids, texts, payloads)


class FakeGraph:
    def __init__(self):
        self.built = []

    def build_chunk(self, *args, **kwargs):
        self.built.append(args)


@pytest.mark.asyncio
async def test_reference_docs_indexes_and_builds_graph(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("para one " * 120 + "\n\npara two", encoding="utf-8")
    doc = {
        "id": 1, "tenant_id": "t1", "category": "reference_docs",
        "title": "Doc", "source_path": str(f), "artifact_id": None,
    }
    repo, emb, graph = FakeRepo(doc), FakeEmbedder(), FakeGraph()
    svc = IngestionService(repo, emb, graph, chat_fn=lambda msgs: '{"entities":[],"relations":[]}')
    await svc.ingest_document(1)
    assert repo.status[0] == ("ingesting", None)
    assert repo.status[-1] == ("ready", None)
    assert emb.indexed[0] == ["1#0", "1#1"]
    assert repo.summary is None  # reference_docs is not summarized
    assert len(graph.built) == 2


@pytest.mark.asyncio
async def test_persona_summarized_not_graphed(tmp_path):
    f = tmp_path / "p.md"
    f.write_text("I am the assistant.", encoding="utf-8")
    doc = {"id": 2, "tenant_id": "t1", "category": "persona",
           "title": "P", "source_path": str(f), "artifact_id": None}
    repo, emb, graph = FakeRepo(doc), FakeEmbedder(), FakeGraph()
    svc = IngestionService(repo, emb, graph, chat_fn=lambda msgs: "short summary")
    await svc.ingest_document(2)
    assert repo.summary == "short summary"
    assert graph.built == []


@pytest.mark.asyncio
async def test_failure_marks_failed(tmp_path):
    doc = {"id": 3, "tenant_id": "t1", "category": "reference_docs",
           "title": "X", "source_path": "/nonexistent.md", "artifact_id": None}
    repo, emb, graph = FakeRepo(doc), FakeEmbedder(), FakeGraph()
    svc = IngestionService(repo, emb, graph, chat_fn=lambda msgs: "")
    await svc.ingest_document(3)
    assert repo.status[-1][0] == "failed"
    assert repo.status[-1][1]  # error message present
