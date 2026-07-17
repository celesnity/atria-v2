"""Background ingestion: parse -> chunk -> embed -> index -> graph -> summarize."""

from __future__ import annotations

import logging
from typing import Any, Callable

from minder.core.knowledge.categories import behavior_for
from minder.core.knowledge.chunking import chunk_text
from minder.core.knowledge.extraction import extract_entities
from minder.core.knowledge.parsing import parse_file
from minder.core.knowledge.summarize import summarize_document

logger = logging.getLogger(__name__)


class IngestionService:
    """Runs a single document through the full ingest pipeline, fail-safe."""

    def __init__(self, repo: Any, embedder: Any, graph: Any, chat_fn: Callable[[list[dict]], str]):
        self._repo = repo
        self._embedder = embedder
        self._graph = graph
        self._chat_fn = chat_fn

    async def ingest_document(self, document_id: int) -> None:
        doc = await self._repo.get_document(document_id)
        if doc is None:
            return
        await self._repo.set_status(document_id, "ingesting")
        try:
            await self._run(doc)
            await self._repo.set_status(document_id, "ready")
        except Exception as exc:  # noqa: BLE001
            logger.warning("ingest failed for doc %s: %s", document_id, exc)
            await self._repo.set_status(document_id, "failed", error=str(exc))

    async def _run(self, doc: dict[str, Any]) -> None:
        behavior = behavior_for(doc["category"])
        text = self._resolve_text(doc)
        chunks = chunk_text(text)
        did, tenant, category, title = doc["id"], doc["tenant_id"], doc["category"], doc["title"]

        external_ids = [f"{did}#{i}" for i in range(len(chunks))]
        citations = [f"{title} [{did}] · {did}#{i}" for i in range(len(chunks))]
        payloads = [
            {
                "id": external_ids[i],
                "tenant_id": tenant,
                "category": category,
                "document_id": did,
                "chunk_id": external_ids[i],
                "text": chunks[i],
                "title": title,
                "citation": citations[i],
            }
            for i in range(len(chunks))
        ]
        self._embedder.index_chunks(external_ids, chunks, payloads)
        await self._repo.replace_chunks(
            did, tenant, category,
            [(i, chunks[i], external_ids[i], citations[i]) for i in range(len(chunks))],
        )

        if behavior.build_graph:
            for i, chunk in enumerate(chunks):
                entities, relations = extract_entities(chunk, self._chat_fn)
                self._graph.build_chunk(tenant, did, i, chunk, entities, relations)

        if behavior.summarize:
            summary = summarize_document(text, self._chat_fn)
            if summary:
                await self._repo.set_summary(did, summary)

    def _resolve_text(self, doc: dict[str, Any]) -> str:
        if doc.get("source_path"):
            return parse_file(doc["source_path"])
        raise ValueError("document has no source_path (artifact resolution is Task 12)")
