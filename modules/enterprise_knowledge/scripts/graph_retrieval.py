"""Query-time GraphRAG expansion for the enterprise_knowledge module.

Vector hits seed a graph traversal (entity- and tag-based). Every candidate
chunk the graph returns is re-checked with the authoritative ``acl.can_access``
predicate — the same gate as the vector path — before it can enter synthesis.
The graph never grants access; it only surfaces candidate chunks faster.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import sibling  # noqa: E402

acl = sibling("acl")
graph_store = sibling("graph_store")


def expand(store, seed_hits, user, hops: int, max_neighbors: int) -> list[dict]:
    """Return ACL-safe graph-neighbor chunks for the given vector seed hits.

    Args:
        store: An ``EKGraphStore`` (or compatible) exposing ``neighbors_*``.
        seed_hits: Vector hits; each must carry ``chunk_id``.
        user: The querying identity (RBAC scope).
        hops: Entity-graph traversal depth.
        max_neighbors: Per-strategy candidate cap.

    Returns:
        Candidate chunk dicts (same shape as vector hits) that pass
        ``acl.can_access`` — de-duplicated across the entity and tag strategies.
    """
    seeds = [h["chunk_id"] for h in seed_hits if h.get("chunk_id")]
    if not seeds:
        return []
    aclp = graph_store.acl_params(user)
    candidates = store.neighbors_via_entities(
        seeds, hops, aclp, max_neighbors
    ) + store.neighbors_via_tags(seeds, aclp, max_neighbors)
    safe: list[dict] = []
    seen: set[str] = set()
    for cand in candidates:
        cid = cand["chunk_id"]
        if cid in seen:
            continue
        decision = acl.can_access(
            user, {"classification": cand["classification"], "department": cand["department"]}
        )
        if decision.allowed:
            seen.add(cid)
            safe.append(cand)
    return safe


def merge_hits(vector_hits, graph_hits, cap: int, boost: float = 0.1) -> list[dict]:
    """Merge vector and graph hits: vector leads (with a connectivity boost),
    graph-only chunks are appended below, de-duplicated, capped at ``cap``.
    """
    graph_ids = {h["chunk_id"] for h in graph_hits}
    merged: list[dict] = []
    seen: set[str] = set()
    for hit in vector_hits:
        h = dict(hit)
        if h["chunk_id"] in graph_ids:  # connectivity boost (Approach B)
            h["score"] = float(h.get("score", 0.0)) * (1.0 + boost)
        merged.append(h)
        seen.add(h["chunk_id"])
    merged.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    floor = min((float(h.get("score", 0.0)) for h in vector_hits), default=0.0)
    for gh in graph_hits:
        if gh["chunk_id"] in seen:
            continue
        g = dict(gh)
        g.setdefault("score", max(0.0, floor - 1e-3))  # rank below vector hits
        merged.append(g)
        seen.add(g["chunk_id"])
    return merged[:cap]
