"""Neo4j-backed knowledge graph store for the enterprise_knowledge module.

All database access goes through an injected ``run_fn(cypher, params) -> rows``
so unit tests supply a fake and never touch a server. Every EK node carries the
``:EKNode`` label (plus a type label), so all reads, writes, and reset stay
scoped to EK data and never touch a co-located module's graph (the compose
Neo4j is a single shared Community-edition database).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, Mapping, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from identity import User  # type: ignore[import-not-found]

NS_LABEL = "EKNode"
RunFn = Callable[[str, dict], list]

_DOC = "EKDocument"
_CHUNK = "EKChunk"
_ENTITY = "EKEntity"
_TAG = "EKTag"
_DEPT = "EKDepartment"


def acl_params(user: User) -> dict:
    """Cypher parameters mirroring ``acl.build_filter`` for graph traversal.

    The authoritative gate remains ``acl.can_access`` (applied in
    ``graph_retrieval``); these params are a first-line WHERE filter only.
    """
    return {
        "is_exec": user.role == "Executive",
        "dept": user.department,
        "open": ["Public", "Internal"],
        "conf": "Confidential",
    }


class EKGraphStore:
    """Create constraints, upsert the EK subgraph, and query it."""

    def __init__(self, run_fn: RunFn):
        self._run = run_fn

    def ensure_constraints(self) -> None:
        """One uniqueness constraint per EK node label on its key property."""
        for label, key in (
            (_DOC, "doc_id"),
            (_CHUNK, "chunk_id"),
            (_ENTITY, "key"),
            (_TAG, "name"),
        ):
            self._run(
                f"CREATE CONSTRAINT ek_{label.lower()}_{key} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE",
                {},
            )

    def upsert_document(self, doc: dict) -> None:
        """MERGE a Document node plus its Department and Tag edges."""
        self._run(
            f"MERGE (d:{_DOC}:{NS_LABEL} {{doc_id: $doc_id}}) SET d += $props",
            {
                "doc_id": doc["doc_id"],
                "props": {
                    "title": doc["title"],
                    "department": doc["department"],
                    "classification": doc["classification"],
                    "owner": doc.get("owner", ""),
                    "knowledge_space": doc.get("knowledge_space", ""),
                    "last_updated": doc.get("last_updated", ""),
                },
            },
        )
        self._run(
            f"MERGE (dep:{_DEPT}:{NS_LABEL} {{department_id: $dept}}) "
            f"WITH dep MATCH (d:{_DOC} {{doc_id: $doc_id}}) "
            "MERGE (d)-[:IN_DEPARTMENT]->(dep)",
            {"dept": doc["department"], "doc_id": doc["doc_id"]},
        )
        for tag in doc.get("tags", []) or []:
            self._run(
                f"MERGE (t:{_TAG}:{NS_LABEL} {{name: $name}}) "
                f"WITH t MATCH (d:{_DOC} {{doc_id: $doc_id}}) "
                "MERGE (d)-[:TAGGED]->(t)",
                {"name": tag, "doc_id": doc["doc_id"]},
            )

    def upsert_chunk(self, chunk: dict) -> None:
        """MERGE a Chunk node (with passage text) and link it to its Document."""
        self._run(
            f"MERGE (c:{_CHUNK}:{NS_LABEL} {{chunk_id: $chunk_id}}) SET c += $props",
            {
                "chunk_id": chunk["chunk_id"],
                "props": {
                    "doc_id": chunk["doc_id"],
                    "text": chunk["text"],
                    "title": chunk["title"],
                    "department": chunk["department"],
                    "classification": chunk["classification"],
                    "knowledge_space": chunk.get("knowledge_space", ""),
                    "citation": chunk["citation"],
                },
            },
        )
        self._run(
            f"MATCH (c:{_CHUNK} {{chunk_id: $chunk_id}}), (d:{_DOC} {{doc_id: $doc_id}}) "
            "MERGE (c)-[:PART_OF]->(d)",
            {"chunk_id": chunk["chunk_id"], "doc_id": chunk["doc_id"]},
        )

    def upsert_extraction(self, chunk_id: str, ext) -> tuple[int, int]:
        """MERGE entities, chunk->entity MENTIONS, and entity->entity RELATED_TO.

        Args:
            chunk_id: The source chunk whose entities these are.
            ext: An ``extraction.GraphExtraction``.

        Returns:
            ``(entity_count, edge_count)`` upserted.
        """
        for ent in ext.entities:
            self._run(
                f"MERGE (n:{_ENTITY}:{NS_LABEL} {{key: $key}}) SET n += $props, "
                "n.etype = $etype",
                {"key": ent.key, "props": ent.props, "etype": ent.type},
            )
            self._run(
                f"MATCH (c:{_CHUNK} {{chunk_id: $chunk_id}}), (n:{_ENTITY} {{key: $key}}) "
                "MERGE (c)-[:MENTIONS]->(n)",
                {"chunk_id": chunk_id, "key": ent.key},
            )
        for edge in ext.edges:
            self._run(
                f"MATCH (a:{_ENTITY} {{key: $src}}), (b:{_ENTITY} {{key: $dst}}) "
                "MERGE (a)-[r:RELATED_TO]->(b) SET r += $props",
                {"src": edge.src_key, "dst": edge.dst_key, "props": edge.props},
            )
        return len(ext.entities), len(ext.edges)

    def stats(self) -> dict:
        """Return EK node and edge counts."""
        rows = self._run(
            f"MATCH (n:{NS_LABEL}) WITH count(n) AS nodes "
            f"OPTIONAL MATCH (:{NS_LABEL})-[r]->(:{NS_LABEL}) "
            "RETURN nodes, count(r) AS edges",
            {},
        )
        if not rows:
            return {"nodes": 0, "edges": 0}
        return {"nodes": rows[0].get("nodes", 0), "edges": rows[0].get("edges", 0)}

    def reset(self) -> None:
        """Delete every EK node and its relationships (never touches other modules)."""
        self._run(f"MATCH (n:{NS_LABEL}) DETACH DELETE n", {})

    _ACL_WHERE = (
        "(cand.classification IN $open OR $is_exec "
        "OR (cand.classification = $conf AND cand.department = $dept))"
    )

    @staticmethod
    def _return_chunk(var: str = "cand") -> str:
        return (
            f"RETURN DISTINCT {var}.chunk_id AS chunk_id, {var}.doc_id AS doc_id, "
            f"{var}.text AS text, {var}.title AS title, {var}.department AS department, "
            f"{var}.classification AS classification, "
            f"{var}.knowledge_space AS knowledge_space, {var}.citation AS citation"
        )

    def neighbors_via_entities(self, seed_chunk_ids, hops, acl, limit) -> list[dict]:
        """Candidate chunks reachable seed-chunk -> entity -> RELATED_TO* -> entity -> chunk."""
        depth = max(0, int(hops))
        cypher = (
            f"MATCH (c:{_CHUNK})-[:MENTIONS]->(seed:{_ENTITY}) "
            "WHERE c.chunk_id IN $seeds "
            f"MATCH (seed)-[:RELATED_TO*0..{depth}]-(rel:{_ENTITY}) "
            f"MATCH (rel)<-[:MENTIONS]-(cand:{_CHUNK}) "
            "WHERE NOT cand.chunk_id IN $seeds AND "
            + self._ACL_WHERE
            + " "
            + self._return_chunk()
            + " LIMIT $limit"
        )
        return self._run(cypher, {"seeds": list(seed_chunk_ids), "limit": int(limit), **acl})

    def neighbors_via_tags(self, seed_chunk_ids, acl, limit) -> list[dict]:
        """Candidate chunks in documents sharing a tag with a seed chunk's document."""
        cypher = (
            f"MATCH (c:{_CHUNK})-[:PART_OF]->(:{_DOC})-[:TAGGED]->(t:{_TAG}) "
            "WHERE c.chunk_id IN $seeds "
            f"MATCH (t)<-[:TAGGED]-(:{_DOC})<-[:PART_OF]-(cand:{_CHUNK}) "
            "WHERE NOT cand.chunk_id IN $seeds AND "
            + self._ACL_WHERE
            + " "
            + self._return_chunk()
            + " LIMIT $limit"
        )
        return self._run(cypher, {"seeds": list(seed_chunk_ids), "limit": int(limit), **acl})


def neo4j_run_fn(driver) -> RunFn:
    """Build a run_fn that executes each statement in its own Neo4j session."""

    def _run(cypher: str, params: dict) -> list:
        with driver.session() as session:
            result = session.run(cypher, **params)
            return [record.data() for record in result]

    return _run


def build_driver(env: Optional[Mapping[str, str]] = None):
    """Construct a Neo4j driver from ``EK_NEO4J_URI|USER|PASSWORD``."""
    from neo4j import GraphDatabase  # local import: heavy optional dep

    src = os.environ if env is None else env
    return GraphDatabase.driver(
        src.get("EK_NEO4J_URI", "bolt://localhost:7687"),
        auth=(src.get("EK_NEO4J_USER", "neo4j"), src.get("EK_NEO4J_PASSWORD", "atria-neo4j")),
    )
