"""Qdrant-backed dense vector index with stable external ids."""

from __future__ import annotations

import os
import uuid
from typing import Any

from qdrant_client import QdrantClient, models


class DenseIndex:
    """Cosine-distance collection wrapper keyed by external string ids."""

    def __init__(self, collection: str, url: str | None = None) -> None:
        self.collection = collection
        self._client = QdrantClient(
            url=url or os.environ.get("QDRANT_URL", "http://localhost:6333"),
            api_key=os.environ.get("QDRANT_API_KEY") or None,
        )

    def ensure(self, dim: int) -> None:
        """Create the collection if it does not exist."""
        if not self._client.collection_exists(self.collection):
            self._client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
            )

    def upsert(
        self, ids: list[str], vectors: list[list[float]], payloads: list[dict[str, Any]]
    ) -> None:
        """Idempotently upsert points; external id is kept in payload['id']."""
        points = [
            models.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, external_id)),
                vector=vector,
                payload={**payload, "id": external_id},
            )
            for external_id, vector, payload in zip(ids, vectors, payloads)
        ]
        self._client.upsert(collection_name=self.collection, points=points)

    def delete(self, ids: list[str]) -> None:
        """Delete points by external id.

        Args:
            ids: External ids to remove, in the same id space as `upsert`.
                Each is mapped to its point id via
                `uuid.uuid5(uuid.NAMESPACE_URL, external_id)` before deletion.
                An empty list is a no-op.
        """
        if not ids:
            return
        point_ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, external_id)) for external_id in ids]
        self._client.delete(
            collection_name=self.collection,
            points_selector=models.PointIdsList(points=point_ids),
        )

    def query(
        self,
        vector: list[float],
        query_filter: models.Filter | None = None,
        limit: int = 20,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        """Return (external_id, cosine_score, payload) tuples, best first."""
        response = self._client.query_points(
            collection_name=self.collection,
            query=vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        results: list[tuple[str, float, dict[str, Any]]] = []
        for point in response.points:
            payload = point.payload or {}
            results.append((str(payload.get("id", point.id)), float(point.score), payload))
        return results
