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
        for label, key in ((_DOC, "doc_id"), (_CHUNK, "chunk_id"),
                           (_ENTITY, "key"), (_TAG, "name")):
            self._run(
                f"CREATE CONSTRAINT ek_{label.lower()}_{key} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE",
                {},
            )

    def upsert_document(self, doc: dict) -> None:
        """MERGE a Document node plus its Department and Tag edges."""
        self._run(
            f"MERGE (d:{_DOC}:{NS_LABEL} {{doc_id: $doc_id}}) SET d += $props",
            {"doc_id": doc["doc_id"], "props": {
                "title": doc["title"], "department": doc["department"],
                "classification": doc["classification"], "owner": doc.get("owner", ""),
                "knowledge_space": doc.get("knowledge_space", ""),
                "last_updated": doc.get("last_updated", ""),
            }},
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
            {"chunk_id": chunk["chunk_id"], "props": {
                "doc_id": chunk["doc_id"], "text": chunk["text"],
                "title": chunk["title"], "department": chunk["department"],
                "classification": chunk["classification"],
                "knowledge_space": chunk.get("knowledge_space", ""),
                "citation": chunk["citation"],
            }},
        )
        self._run(
            f"MATCH (c:{_CHUNK} {{chunk_id: $chunk_id}}), (d:{_DOC} {{doc_id: $doc_id}}) "
            "MERGE (c)-[:PART_OF]->(d)",
            {"chunk_id": chunk["chunk_id"], "doc_id": chunk["doc_id"]},
        )

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
        auth=(src.get("EK_NEO4J_USER", "neo4j"),
              src.get("EK_NEO4J_PASSWORD", "atria-neo4j")),
    )
