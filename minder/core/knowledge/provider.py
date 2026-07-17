"""Hybrid (dense + FTS + graph) search provider over knowledge chunks."""

from __future__ import annotations

from typing import Any, Callable

from minder.core.context_engineering.search.fusion import rrf_fuse, top_margin
from minder.core.context_engineering.search.provider import SearchProvider
from minder.core.context_engineering.search.types import SearchContext, SearchHit, SourceResults
from minder.core.knowledge.categories import Category
from minder.core.knowledge.graph import graph_enabled, graph_hops, merge_graph_hits

_MAX_NEIGHBORS = 20


class DocumentsProvider(SearchProvider):
    """Permission-scoped hybrid retrieval; tenant is injected, never model-set."""

    name = "documents"
    description = (
        "Per-tenant knowledge base: reference documents (policies, PDFs, FAQs, "
        "workflows). Results are scoped to the acting tenant and cited."
    )
    filter_schema: dict[str, Any] = {
        "category": {
            "type": "string",
            "enum": [c.value for c in Category],
            "description": "Which knowledge category to search (default reference_docs).",
        }
    }

    def __init__(
        self,
        embedder: Any,
        repo: Any,
        graph: Any,
        resolve_tenant: Callable[[SearchContext], str | None],
    ) -> None:
        self._embedder = embedder
        self._repo = repo
        self._graph = graph
        self._resolve_tenant = resolve_tenant

    def search(
        self, query: str, filters: dict[str, Any], limit: int, context: SearchContext
    ) -> SourceResults:
        tenant_id = self._resolve_tenant(context)
        if not tenant_id:
            return SourceResults(
                source=self.name, hits=[], note="no tenant in context; access denied"
            )
        category = filters.get("category") or Category.REFERENCE_DOCS.value

        query_vec = self._embedder.embed_query(query)
        dense = self._embedder.search(query_vec, tenant_id, category, max(limit * 2, 10))
        payloads = {external_id: payload for external_id, _score, payload in dense}
        dense_ids = [external_id for external_id, _s, _p in dense]
        fts_ids = self._repo.fts_search(tenant_id, category, query, max(limit * 2, 10))

        fused = rrf_fuse([dense_ids, fts_ids])
        ranked = sorted(fused, key=lambda i: fused[i], reverse=True)

        if graph_enabled():
            graph_ids = self._graph.expand(
                tenant_id, ranked[:limit], graph_hops(), _MAX_NEIGHBORS
            )
            ranked = merge_graph_hits(ranked, graph_ids, cap=limit + _MAX_NEIGHBORS)

        hits: list[SearchHit] = []
        for external_id in ranked[:limit]:
            payload = payloads.get(external_id) or self._hydrate(external_id, tenant_id)
            if payload is None:
                continue
            hits.append(
                SearchHit(
                    id=external_id,
                    source=self.name,
                    title=payload.get("title", ""),
                    snippet=payload.get("text", "")[:700],
                    score=fused.get(external_id, 0.0),
                    metadata={"citation": payload.get("citation", "")},
                )
            )
        return SourceResults(
            source=self.name, hits=hits, top_margin=top_margin([h.score for h in hits])
        )

    def _hydrate(self, external_id: str, tenant_id: str) -> dict[str, Any] | None:
        """Fetch a graph-only chunk's payload from Postgres when not in the dense set."""
        document_id, _, chunk_index = external_id.partition("#")
        rows = self._repo.chunk_payload(tenant_id, int(document_id), int(chunk_index))
        return rows
