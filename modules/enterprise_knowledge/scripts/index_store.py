"""Qdrant-backed vector index for enterprise document chunks.

Embeds chunk text with an injected ``embed_fn`` (production: hosted embeddings
via the ``index_embed`` role) and stores one point per chunk with its full
metadata payload — including ``classification`` and canonical ``department`` —
so retrieval can be constrained by an access-control filter.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Callable

from qdrant_client import QdrantClient, models

if TYPE_CHECKING:
    from chunking import ChunkRecord  # type: ignore[import-not-found]

COLLECTION = "enterprise_chunks"

# Fixed namespace so uuid5(citation) is stable across processes → idempotent re-index.
_POINT_NS = uuid.UUID("b8f1c2d3-4e5a-6b7c-8d9e-0f1a2b3c4d5e")

EmbedFn = Callable[[list[str]], list[list[float]]]


class IndexStore:
    """Create/populate/query the ``enterprise_chunks`` collection."""

    def __init__(self, qdrant: QdrantClient, embed_fn: EmbedFn, collection: str = COLLECTION):
        self._q = qdrant
        self._embed = embed_fn
        self._collection = collection

    def ensure_collection(self, dim: int) -> None:
        """Create the collection with cosine distance if it does not exist."""
        if self._q.collection_exists(self._collection):
            return
        self._q.create_collection(
            collection_name=self._collection,
            vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
        )

    def upsert_chunks(self, records: list["ChunkRecord"]) -> int:
        """Embed and upsert one point per record. Returns the number stored.

        Point ids are a stable ``uuid5`` of the citation, so re-indexing the same
        chunk updates in place rather than duplicating.
        """
        if not records:
            return 0
        vectors = self._embed([r.text for r in records])
        points = [
            models.PointStruct(
                id=str(uuid.uuid5(_POINT_NS, rec.citation)),
                vector=vec,
                payload={
                    "doc_id": rec.doc_id,
                    "chunk_id": rec.chunk_id,
                    "text": rec.text,
                    "title": rec.title,
                    "department": rec.department,
                    "classification": rec.classification,
                    "knowledge_space": rec.knowledge_space,
                    "owner": rec.owner,
                    "citation": rec.citation,
                },
            )
            for rec, vec in zip(records, vectors)
        ]
        self._q.upsert(collection_name=self._collection, points=points, wait=True)
        return len(points)

    def query(
        self,
        text: str,
        k: int = 5,
        acl_filter: models.Filter | None = None,
        department: str | None = None,
    ) -> list[dict]:
        """Embed ``text`` and return the top-``k`` access-filtered hits.

        Args:
            text: The query text.
            k: Max hits to return.
            acl_filter: Access-control filter from ``acl.build_filter(user)``;
                ``None`` means no access restriction (executive).
            department: Optional narrowing to a single canonical department_id
                *within* the accessible scope. Never widens access.

        Returns:
            Hit dicts with score, citation, text, and metadata.
        """
        query_filter = self._combine(acl_filter, department)
        vector = self._embed([text])[0]
        result = self._q.query_points(
            collection_name=self._collection,
            query=vector,
            limit=k,
            query_filter=query_filter,
        )
        return [
            {
                "score": point.score,
                "citation": point.payload["citation"],
                "text": point.payload["text"],
                "doc_id": point.payload["doc_id"],
                "chunk_id": point.payload["chunk_id"],
                "title": point.payload["title"],
                "department": point.payload["department"],
                "classification": point.payload["classification"],
                "knowledge_space": point.payload["knowledge_space"],
            }
            for point in result.points
        ]

    @staticmethod
    def _combine(
        acl_filter: models.Filter | None, department: str | None
    ) -> models.Filter | None:
        """Combine the ACL filter with an optional department narrowing."""
        if department is None:
            return acl_filter
        dept_cond = models.FieldCondition(
            key="department", match=models.MatchValue(value=department)
        )
        if acl_filter is None:
            return models.Filter(must=[dept_cond])
        return models.Filter(must=[acl_filter, dept_cond])

    def list_indexed(self) -> dict:
        """Return the point count and a breakdown by classification and department."""
        count = self._q.count(collection_name=self._collection).count
        by_class: dict[str, int] = {}
        by_dept: dict[str, int] = {}
        offset = None
        while True:
            recs, offset = self._q.scroll(
                collection_name=self._collection, with_payload=True, limit=256, offset=offset
            )
            for r in recs:
                by_class[r.payload["classification"]] = by_class.get(
                    r.payload["classification"], 0) + 1
                by_dept[r.payload["department"]] = by_dept.get(
                    r.payload["department"], 0) + 1
            if offset is None:
                break
        return {"count": count, "by_classification": by_class, "by_department": by_dept}

    def reset(self) -> None:
        """Delete the collection if it exists."""
        if self._q.collection_exists(self._collection):
            self._q.delete_collection(self._collection)
