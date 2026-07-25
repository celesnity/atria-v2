"""Management API for the knowledge base: register, drain, list, delete."""

from __future__ import annotations

from typing import Any

from minder.core.knowledge.categories import is_valid_category


class KnowledgeService:
    """Coordinates document lifecycle over the repository + ingestion service."""

    def __init__(self, repo: Any, ingestion: Any, embedder: Any = None) -> None:
        self._repo = repo
        self._ingestion = ingestion
        self._embedder = embedder

    async def register_upload(
        self, tenant_id: str, category: str, title: str, content_hash: str, artifact_id: int
    ) -> int:
        if not is_valid_category(category):
            raise ValueError(f"Unknown category: {category!r}")
        return await self._repo.create_document(
            tenant_id, category, title, content_hash, artifact_id=artifact_id
        )

    async def drain_queue(self, batch: int = 5) -> int:
        ids = await self._repo.pending_document_ids(limit=batch)
        for document_id in ids:
            await self._ingestion.ingest_document(document_id)
        return len(ids)

    async def list_documents(self, tenant_id: str) -> list[dict[str, Any]]:
        return await self._repo.list_documents(tenant_id)

    async def reingest(self, document_id: int) -> None:
        await self._repo.set_status(document_id, "pending")

    async def delete(self, document_id: int) -> None:
        point_ids = await self._repo.delete_document(document_id)
        if self._embedder and point_ids:
            self._embedder.delete(point_ids)
