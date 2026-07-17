# minder/core/knowledge/repository.py
"""Postgres persistence for knowledge documents and chunks."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from minder.core.context_engineering.search import pg
from minder.core.context_engineering.search.normalize import normalize_for_search
from minder.db.models import KnowledgeChunk, KnowledgeDocument


class KnowledgeRepository:
    """CRUD for knowledge documents/chunks plus Postgres FTS recall."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    async def create_document(
        self,
        tenant_id: str,
        category: str,
        title: str,
        content_hash: str,
        *,
        artifact_id: int | None = None,
        source_path: str | None = None,
        source_filename: str | None = None,
    ) -> int:
        async with self._sm() as s:
            doc = KnowledgeDocument(
                tenant_id=tenant_id,
                category=category,
                title=title,
                content_hash=content_hash,
                artifact_id=artifact_id,
                source_path=source_path,
                source_filename=source_filename,
                status="pending",
            )
            s.add(doc)
            await s.commit()
            return doc.id

    async def get_document(self, document_id: int) -> dict[str, Any] | None:
        async with self._sm() as s:
            row = (
                await s.execute(
                    select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
                )
            ).scalar_one_or_none()
            return _doc_to_dict(row) if row else None

    async def find_document_by_hash(self, tenant_id: str, content_hash: str) -> dict[str, Any] | None:
        async with self._sm() as s:
            row = (
                await s.execute(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.tenant_id == tenant_id,
                        KnowledgeDocument.content_hash == content_hash,
                    )
                )
            ).scalar_one_or_none()
            return _doc_to_dict(row) if row else None

    async def set_status(self, document_id: int, status: str, *, error: str | None = None) -> None:
        async with self._sm() as s:
            await s.execute(
                update(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .values(status=status, error=error)
            )
            await s.commit()

    async def set_summary(self, document_id: int, summary: str) -> None:
        async with self._sm() as s:
            await s.execute(
                update(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .values(summary=summary)
            )
            await s.commit()

    async def replace_chunks(
        self,
        document_id: int,
        tenant_id: str,
        category: str,
        chunks: list[tuple[int, str, str, str]],
    ) -> None:
        async with self._sm() as s:
            await s.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
            )
            for chunk_index, text, point_id, citation in chunks:
                s.add(
                    KnowledgeChunk(
                        document_id=document_id,
                        tenant_id=tenant_id,
                        category=category,
                        chunk_index=chunk_index,
                        text=text,
                        qdrant_point_id=point_id,
                        citation=citation,
                    )
                )
            await s.commit()

    async def list_documents(self, tenant_id: str) -> list[dict[str, Any]]:
        async with self._sm() as s:
            rows = (
                await s.execute(
                    select(KnowledgeDocument)
                    .where(KnowledgeDocument.tenant_id == tenant_id)
                    .order_by(KnowledgeDocument.id)
                )
            ).scalars()
            return [_doc_to_dict(r) for r in rows]

    async def summaries_for_inject(self, tenant_id: str, categories: list[str]) -> list[dict[str, Any]]:
        async with self._sm() as s:
            rows = (
                await s.execute(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.tenant_id == tenant_id,
                        KnowledgeDocument.category.in_(categories),
                        KnowledgeDocument.status == "ready",
                    )
                )
            ).scalars()
            return [_doc_to_dict(r) for r in rows if r.summary]

    async def delete_document(self, document_id: int) -> list[str]:
        async with self._sm() as s:
            point_ids = [
                pid
                for pid in (
                    await s.execute(
                        select(KnowledgeChunk.qdrant_point_id).where(
                            KnowledgeChunk.document_id == document_id
                        )
                    )
                ).scalars()
                if pid
            ]
            await s.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
            await s.execute(
                delete(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
            )
            await s.commit()
            return point_ids

    async def pending_document_ids(self, limit: int = 5) -> list[int]:
        async with self._sm() as s:
            return list(
                (
                    await s.execute(
                        select(KnowledgeDocument.id)
                        .where(KnowledgeDocument.status == "pending")
                        .order_by(KnowledgeDocument.id)
                        .limit(limit)
                    )
                ).scalars()
            )

    def fts_search(self, tenant_id: str, category: str, query: str, limit: int) -> list[str]:
        """Return chunk external ids ('{document_id}#{chunk_index}') by FTS rank."""
        normalized = normalize_for_search(query)
        rows = pg.fetch_all(
            "SELECT document_id, chunk_index "
            "FROM knowledge_chunks "
            "WHERE tenant_id = $1 AND category = $2 "
            "AND to_tsvector('simple', text) @@ websearch_to_tsquery('simple', $3) "
            "ORDER BY ts_rank(to_tsvector('simple', text), "
            "websearch_to_tsquery('simple', $3)) DESC "
            "LIMIT $4",
            [tenant_id, category, normalized, limit],
        )
        return [f"{r['document_id']}#{r['chunk_index']}" for r in rows]


def _doc_to_dict(doc: KnowledgeDocument) -> dict[str, Any]:
    return {
        "id": doc.id,
        "tenant_id": doc.tenant_id,
        "category": doc.category,
        "title": doc.title,
        "content_hash": doc.content_hash,
        "status": doc.status,
        "error": doc.error,
        "summary": doc.summary,
        "artifact_id": doc.artifact_id,
        "source_path": doc.source_path,
        "source_filename": doc.source_filename,
    }
