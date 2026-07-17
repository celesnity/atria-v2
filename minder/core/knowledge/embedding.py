"""Embedding + Qdrant wrapper bound to the knowledge_chunks collection."""

from __future__ import annotations

from typing import Any

from qdrant_client import models

from minder.core.context_engineering.search.dense import DenseIndex
from minder.core.context_engineering.search.embedder import Embedder

COLLECTION = "knowledge_chunks"


def tenant_category_filter(tenant_id: str, category: str) -> models.Filter:
    """Qdrant hard filter scoping a query to one tenant + category."""
    return models.Filter(
        must=[
            models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id)),
            models.FieldCondition(key="category", match=models.MatchValue(value=category)),
        ]
    )


class KnowledgeEmbedder:
    """Generate embeddings and read/write the knowledge_chunks collection."""

    COLLECTION = COLLECTION

    def __init__(self, embedder: Any = None, index: Any = None) -> None:
        self._embedder = embedder or Embedder()
        self._index = index or DenseIndex(COLLECTION)

    def embed_query(self, text: str) -> list[float]:
        return self._embedder.embed([text])[0]

    def index_chunks(
        self,
        external_ids: list[str],
        texts: list[str],
        payloads: list[dict[str, Any]],
    ) -> None:
        if not texts:
            return
        vectors = self._embedder.embed(texts)
        self._index.ensure(len(vectors[0]))
        self._index.upsert(external_ids, vectors, payloads)

    def delete(self, external_ids: list[str]) -> None:
        self._index.delete(external_ids)

    def search(
        self,
        query_vector: list[float],
        tenant_id: str,
        category: str,
        limit: int,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        return self._index.query(query_vector, tenant_category_filter(tenant_id, category), limit)
