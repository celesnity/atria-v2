"""Qdrant-backed vector index for enterprise document chunks.

Embeds chunk text with an injected ``embed_fn`` (production: hosted embeddings
via the ``index_embed`` role) and stores one point per chunk with its full
metadata payload — including ``classification`` and canonical ``department`` —
so retrieval can be constrained by an access-control filter.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from qdrant_client import QdrantClient, models

if TYPE_CHECKING:
    from chunking import ChunkRecord  # type: ignore[import-not-found]

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import sibling  # noqa: E402

bm25 = sibling("bm25")

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
        """Create the collection (named ``dense`` + BM25 ``bm25`` sparse) if absent."""
        if self._q.collection_exists(self._collection):
            return
        self._q.create_collection(
            collection_name=self._collection,
            vectors_config={
                "dense": models.VectorParams(size=dim, distance=models.Distance.COSINE),
            },
            sparse_vectors_config={
                "bm25": models.SparseVectorParams(modifier=models.Modifier.IDF),
            },
        )

    def upsert_chunks(self, records: list["ChunkRecord"], avgdl: float | None = None) -> int:
        """Embed and upsert one point per record. Returns the number stored.

        Always writes the ``dense`` vector. When ``avgdl`` (corpus average token
        length) is given, also writes a ``bm25`` sparse vector for keyword/hybrid
        search. Point ids are a stable ``uuid5`` of the citation (idempotent).
        """
        if not records:
            return 0
        vectors = self._embed([r.text for r in records])
        points = []
        for rec, vec in zip(records, vectors):
            named: dict[str, object] = {"dense": vec}
            if avgdl is not None:
                indices, values = bm25.doc_sparse(bm25.tokenize(rec.text), avgdl)
                named["bm25"] = models.SparseVector(indices=indices, values=values)
            points.append(
                models.PointStruct(
                    id=str(uuid.uuid5(_POINT_NS, rec.citation)),
                    vector=named,
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
            )
        self._q.upsert(collection_name=self._collection, points=points, wait=True)
        return len(points)

    def query(
        self,
        text: str,
        k: int = 5,
        acl_filter: models.Filter | None = None,
        department: str | None = None,
        mode: str = "hybrid",
    ) -> list[dict]:
        """Return the top-``k`` access-filtered hits for ``text``.

        ``mode`` selects the retrieval signal: ``dense`` (vector), ``bm25``
        (sparse keyword), or ``hybrid`` (both, fused server-side with RRF).
        The ACL filter is applied to every path — in ``hybrid`` on each
        prefetch — so no mode can widen access.

        Args:
            text: The query text.
            k: Max hits to return.
            acl_filter: Access-control filter from ``acl.build_filter(user)``;
                ``None`` means no access restriction (executive).
            department: Optional narrowing to a single canonical department_id
                *within* the accessible scope. Never widens access.
            mode: ``dense`` | ``bm25`` | ``hybrid`` (default). Unknown modes
                raise ``ValueError``.

        Returns:
            Hit dicts with score, citation, text, and metadata.
        """
        flt = self._combine(acl_filter, department)
        if mode == "dense":
            result = self._q.query_points(
                collection_name=self._collection,
                query=self._embed([text])[0],
                using="dense",
                limit=k,
                query_filter=flt,
            )
        elif mode == "bm25":
            indices, values = bm25.query_sparse(bm25.tokenize(text))
            result = self._q.query_points(
                collection_name=self._collection,
                query=models.SparseVector(indices=indices, values=values),
                using="bm25",
                limit=k,
                query_filter=flt,
            )
        elif mode == "hybrid":
            prefetch_limit = max(k * 4, 20)
            indices, values = bm25.query_sparse(bm25.tokenize(text))
            result = self._q.query_points(
                collection_name=self._collection,
                prefetch=[
                    models.Prefetch(
                        query=self._embed([text])[0],
                        using="dense",
                        filter=flt,
                        limit=prefetch_limit,
                    ),
                    models.Prefetch(
                        query=models.SparseVector(indices=indices, values=values),
                        using="bm25",
                        filter=flt,
                        limit=prefetch_limit,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=k,
            )
        else:
            raise ValueError(f"unknown search mode: {mode!r}")
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
    def _combine(acl_filter: models.Filter | None, department: str | None) -> models.Filter | None:
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
                by_class[r.payload["classification"]] = (
                    by_class.get(r.payload["classification"], 0) + 1
                )
                by_dept[r.payload["department"]] = by_dept.get(r.payload["department"], 0) + 1
            if offset is None:
                break
        return {"count": count, "by_classification": by_class, "by_department": by_dept}

    def delete_by_doc_id(self, doc_id: str) -> int:
        """Delete every chunk whose payload ``doc_id`` matches. Returns count removed."""
        if not self._q.collection_exists(self._collection):
            return 0
        flt = models.Filter(
            must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))]
        )
        removed = self._q.count(self._collection, count_filter=flt).count
        if removed:
            self._q.delete(
                collection_name=self._collection,
                points_selector=models.FilterSelector(filter=flt),
                wait=True,
            )
        return removed

    def corpus_token_stats(self) -> tuple[int, int]:
        """Return ``(total_tokens, total_chunks)`` across the collection (0,0 if absent)."""
        if not self._q.collection_exists(self._collection):
            return 0, 0
        total_tokens = 0
        total_chunks = 0
        offset = None
        while True:
            recs, offset = self._q.scroll(
                collection_name=self._collection, with_payload=True, limit=256, offset=offset
            )
            for r in recs:
                total_tokens += int(r.payload.get("token_count", 0))
                total_chunks += 1
            if offset is None:
                break
        return total_tokens, total_chunks

    def reset(self) -> None:
        """Delete the collection if it exists."""
        if self._q.collection_exists(self._collection):
            self._q.delete_collection(self._collection)
