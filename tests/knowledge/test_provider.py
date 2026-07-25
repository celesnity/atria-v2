from minder.core.context_engineering.search.types import SearchContext
from minder.core.knowledge.provider import DocumentsProvider


class FakeEmbedder:
    def embed_query(self, text):
        return [0.1, 0.2, 0.3]

    def search(self, vec, tenant_id, category, limit):
        # (external_id, score, payload)
        return [
            ("1#0", 0.9, {"id": "1#0", "text": "alpha", "title": "A", "citation": "A [1] · 1#0"}),
            ("1#1", 0.5, {"id": "1#1", "text": "beta", "title": "A", "citation": "A [1] · 1#1"}),
        ]


class FakeRepo:
    def fts_search(self, tenant_id, category, query, limit):
        return ["1#1"]


class FakeGraph:
    def expand(self, tenant_id, seed_ids, hops, max_neighbors):
        return []


def _provider(tenant="t1"):
    return DocumentsProvider(
        FakeEmbedder(), FakeRepo(), FakeGraph(),
        resolve_tenant=lambda ctx: tenant,
    )


def test_search_returns_fused_hits_scoped_to_tenant():
    res = _provider().search("alpha", {"category": "reference_docs"}, 6, SearchContext("U1"))
    ids = [h.id for h in res.hits]
    assert "1#0" in ids and "1#1" in ids
    assert res.source == "documents"


def test_missing_tenant_returns_empty_with_note():
    res = _provider(tenant=None).search("x", {}, 6, SearchContext(None))
    assert res.hits == []
    assert res.note
