from minder.core.knowledge.embedding import KnowledgeEmbedder


class FakeEmbedder:
    def embed(self, texts):
        return [[float(len(t)), 1.0, 0.0] for t in texts]


class FakeIndex:
    def __init__(self):
        self.ensured = None
        self.upserts = []
        self.deleted = []

    def ensure(self, dim):
        self.ensured = dim

    def upsert(self, ids, vectors, payloads):
        self.upserts.append((ids, vectors, payloads))

    def delete(self, ids):
        self.deleted.extend(ids)


def test_index_chunks_ensures_dim_and_upserts():
    idx = FakeIndex()
    ke = KnowledgeEmbedder(embedder=FakeEmbedder(), index=idx)
    ke.index_chunks(["1#0"], ["hello"], [{"tenant_id": "t1"}])
    assert idx.ensured == 3
    assert idx.upserts[0][0] == ["1#0"]


def test_embed_query_returns_vector():
    ke = KnowledgeEmbedder(embedder=FakeEmbedder(), index=FakeIndex())
    assert ke.embed_query("abcd")[0] == 4.0
