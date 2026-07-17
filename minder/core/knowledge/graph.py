"""Best-effort Neo4j knowledge graph: build on ingest, expand on query."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def graph_enabled() -> bool:
    """True if graph writes/expansion are turned on via env."""
    return os.environ.get("KNOWLEDGE_GRAPH_ENABLED", "0") == "1"


def graph_hops() -> int:
    """Configured traversal depth (default 2)."""
    try:
        return int(os.environ.get("KNOWLEDGE_GRAPH_HOPS", "2"))
    except ValueError:
        return 2


def merge_graph_hits(
    vector_ids: list[str], graph_ids: list[str], cap: int, boost: float = 0.1
) -> list[str]:
    """Vector ids lead (deduped, order preserved); graph-only ids follow; cap total.

    `boost` is reserved for score-aware callers; ordering already encodes the
    "vector leads" preference, so graph ids never displace vector ids.
    """
    seen: set[str] = set()
    merged: list[str] = []
    for external_id in [*vector_ids, *graph_ids]:
        if external_id in seen:
            continue
        seen.add(external_id)
        merged.append(external_id)
        if len(merged) >= cap:
            break
    return merged


class KnowledgeGraph:
    """Thin Neo4j wrapper; every method degrades to a no-op if Neo4j is down."""

    def __init__(self, driver: Any = None) -> None:
        self._driver = driver if driver is not None else _connect()

    def build_chunk(
        self,
        tenant_id: str,
        document_id: int,
        chunk_index: int,
        text: str,
        entities: list[tuple[str, str]],
        relations: list[tuple[str, str, float]],
    ) -> None:
        if self._driver is None:
            return
        chunk_id = f"{document_id}#{chunk_index}"
        try:
            with self._driver.session() as session:
                session.execute_write(
                    _write_chunk, tenant_id, document_id, chunk_id, entities, relations
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("graph build_chunk failed for %s: %s", chunk_id, exc)

    def expand(
        self, tenant_id: str, seed_ids: list[str], hops: int, max_neighbors: int
    ) -> list[str]:
        if self._driver is None or not seed_ids:
            return []
        try:
            with self._driver.session() as session:
                return session.execute_read(
                    _expand, tenant_id, seed_ids, hops, max_neighbors
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("graph expand failed: %s", exc)
            return []


def _connect() -> Any:
    uri = os.environ.get("KNOWLEDGE_NEO4J_URI")
    if not uri or not graph_enabled():
        return None
    try:
        from neo4j import GraphDatabase

        return GraphDatabase.driver(
            uri,
            auth=(
                os.environ.get("KNOWLEDGE_NEO4J_USER", "neo4j"),
                os.environ.get("KNOWLEDGE_NEO4J_PASSWORD", ""),
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Neo4j unavailable, graph disabled: %s", exc)
        return None


def _write_chunk(tx, tenant_id, document_id, chunk_id, entities, relations):
    tx.run(
        "MERGE (c:KChunk {chunk_id:$chunk_id}) SET c.tenant_id=$tenant_id, c.document_id=$doc",
        chunk_id=chunk_id, tenant_id=tenant_id, doc=document_id,
    )
    for key, etype in entities:
        tx.run(
            "MERGE (e:KEntity {key:$key}) SET e.tenant_id=$tenant_id, e.type=$etype "
            "WITH e MATCH (c:KChunk {chunk_id:$chunk_id}) MERGE (c)-[:MENTIONS]->(e)",
            key=key, etype=etype, tenant_id=tenant_id, chunk_id=chunk_id,
        )
    for src, dst, confidence in relations:
        tx.run(
            "MATCH (a:KEntity {key:$src}), (b:KEntity {key:$dst}) "
            "MERGE (a)-[r:RELATED_TO]->(b) "
            "SET r.confidence=$confidence, r.status='unverified'",
            src=src, dst=dst, confidence=confidence,
        )


def _expand(tx, tenant_id, seed_ids, hops, max_neighbors):
    result = tx.run(
        "MATCH (c:KChunk)-[:MENTIONS]->(:KEntity)-[:RELATED_TO*1..$hops]-"
        "(:KEntity)<-[:MENTIONS]-(n:KChunk) "
        "WHERE c.chunk_id IN $seed_ids AND n.tenant_id=$tenant_id "
        "AND NOT n.chunk_id IN $seed_ids "
        "RETURN DISTINCT n.chunk_id AS chunk_id LIMIT $max_neighbors",
        seed_ids=seed_ids, tenant_id=tenant_id, hops=hops, max_neighbors=max_neighbors,
    )
    return [record["chunk_id"] for record in result]
