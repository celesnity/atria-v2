"""Deterministic edge dialects for graph-augmented retrieval (G1).

Implements the generic G1 pipeline (GENERIC_PIPELINE_production.md): a corpus is
segmented into Nodes, then **deterministic, regex-driven** edges are built —
``ref`` (cross-reference) and ``hier`` (parent/child) — with an optional sparse
kNN ``semantic`` backstop when refs are thin. Retrieval is then
seed-vector -> BFS over edges -> RRF -> top-k. The retriever stays corpus-agnostic;
only the three edge functions per dialect change.

Zero LLM by design. The project's own benchmark shows deterministic edges beat an
LLM-built KG (G1 0.794 > G4 0.510) — so we never let an LLM invent "relatedness".
"""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


@dataclass
class Node:
    id: str
    heading: str = ""
    text: str = ""
    doc_type: str = ""
    ata: str = ""
    citation: str = ""
    embedding: Optional[List[float]] = None


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    kind: str  # "ref" | "hier" | "semantic"


# Maintenance item numbers: "32-31-01", "32-31", "MEL 32-42-02" — dash-separated
# groups of two digits (ATA / chapter / section / item). This is the dotted family
# with dashes, so hier is nearly free (parent = drop the last "-NN").
_ITEM = re.compile(r"\b(\d{2}(?:-\d{2}){1,3})\b")


def _item_of(n: Node) -> Optional[str]:
    """The canonical item a node IS about. Prefer the citation/heading; else fall
    back to the first item number in the chunk's leading text (maintenance chunks
    usually open with a heading like ``# MEL 32-31-01 — …``), since the citation
    field here is doc-level, not item-level."""
    m = _ITEM.search(n.citation or n.heading or "")
    if m:
        return m.group(1)
    m = _ITEM.search((n.text or "")[:200])
    return m.group(1) if m else None


def _index_by_item(nodes: List[Node]) -> Dict[str, List[str]]:
    idx: Dict[str, List[str]] = {}
    for n in nodes:
        it = _item_of(n)
        if it:
            idx.setdefault(it, []).append(n.id)
    return idx


def ref_edges(nodes: List[Node]) -> List[Edge]:
    """ref = an item number mentioned in a node's body that resolves to another
    node's item (same id space — the whole trick to regex cross-refs)."""
    by_item = _index_by_item(nodes)
    out: List[Edge] = []
    for n in nodes:
        self_item = _item_of(n)
        for it in set(_ITEM.findall(n.text or "")):
            if it == self_item:
                continue
            for tgt in by_item.get(it, ()):
                if tgt != n.id:
                    out.append(Edge(n.id, tgt, "ref"))
    return out


def hier_edges(nodes: List[Node]) -> List[Edge]:
    """hier = item-number parent (32-31-01 -> 32-31 -> 32) resolving to a node
    (bidirectional). Parent suffix-strip is free from the id — no extra regex."""
    by_item = _index_by_item(nodes)
    out: List[Edge] = []
    for n in nodes:
        it = _item_of(n)
        if not it or "-" not in it:
            continue
        parent = it.rsplit("-", 1)[0]
        for tgt in by_item.get(parent, ()):
            if tgt != n.id:
                out.append(Edge(n.id, tgt, "hier"))
                out.append(Edge(tgt, n.id, "hier"))
    return out


def knn_edges(nodes: List[Node], m: int = 4, tau: float = 0.75) -> List[Edge]:
    """Sparse semantic backstop (spec 3.1): each node -> m nearest cosine
    neighbours above tau. Needs node.embedding; small m + high tau keep it sparse
    (avoids the dense-noise trap that sank G4). No-op if embeddings are absent."""
    have = [n for n in nodes if n.embedding]
    if len(have) < 2:
        return []
    import numpy as np  # local: numpy only needed on this path

    matrix = np.asarray([n.embedding for n in have], dtype="float32")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix = matrix / norms
    sims = matrix @ matrix.T
    np.fill_diagonal(sims, -1.0)
    out: List[Edge] = []
    for i, n in enumerate(have):
        for j in np.argsort(-sims[i])[:m]:
            if sims[i, j] >= tau:
                out.append(Edge(n.id, have[int(j)].id, "semantic"))
    return out


EDGE_SETS: Dict[str, Dict[str, Callable[[List[Node]], List[Edge]]]] = {
    "maintenance": {"ref": ref_edges, "hier": hier_edges},
    "dotted": {"ref": ref_edges, "hier": hier_edges},  # same numbering family
}

_REF_DENSITY_FLOOR = 0.1  # below this, refs are too thin -> enable the kNN backstop


def corpus_edges(nodes, dialect, *, knn_if_sparse=True, count_only=False):
    """Build a corpus's edges: ref + hier, plus sparse kNN only when ref density
    (len(ref)/len(nodes)) is below the floor (spec 3.2 structural-first rule)."""
    ref = dialect["ref"](nodes)
    hier = dialect["hier"](nodes)
    density = (len(ref) / len(nodes)) if nodes else 0.0
    knn: List[Edge] = []
    if knn_if_sparse and density < _REF_DENSITY_FLOOR and any(n.embedding for n in nodes):
        knn = knn_edges(nodes)
    edges = list(ref) + list(hier) + list(knn)
    if count_only:
        return {"ref": len(ref), "hier": len(hier), "semantic": len(knn),
                "total": len(edges), "ref_density": round(density, 3)}
    return edges


def graph_rerank(hits: List[dict], *, dialect_name: str = "maintenance",
                 seed_size: int = 5, k: int = 5, hop_depth: int = 2, c: int = 60) -> List[dict]:
    """Seed-vector -> BFS-over-edges -> RRF -> top-k, over a vector-recalled pool.

    ``hits`` is the ordered vector-recall (each a dict with at least ``chunk_id``,
    ``text``, ``citation``, ``doc_type``, ``ata_chapter``; ``score``/``embedding``
    optional). Edges are built over the pool (no persistent graph store), so this
    is a self-contained graph rerank. Returns the reordered top-``k`` hits.
    """
    if len(hits) <= 1:
        return hits[:k]
    nodes = [Node(id=h.get("chunk_id", ""), heading=h.get("citation", ""),
                  text=h.get("text", ""), doc_type=h.get("doc_type", ""),
                  ata=str(h.get("ata_chapter", "")), citation=h.get("citation", ""),
                  embedding=h.get("embedding")) for h in hits]
    edges = corpus_edges(nodes, EDGE_SETS.get(dialect_name, EDGE_SETS["maintenance"]))
    adj: Dict[str, set] = {}
    for e in edges:
        adj.setdefault(e.src, set()).add(e.dst)

    by_id = {h.get("chunk_id", ""): h for h in hits}
    vrank = {h.get("chunk_id", ""): i for i, h in enumerate(hits)}

    # BFS from the top-seed_size vector hits over all edge kinds (kinds=None).
    grank: Dict[str, int] = {}
    seen: set = set()
    order = 0
    dq = deque((h.get("chunk_id", ""), 0) for h in hits[:seed_size])
    while dq:
        cid, depth = dq.popleft()
        if cid in seen or depth > hop_depth:
            continue
        seen.add(cid)
        grank[cid] = order
        order += 1
        for nb in adj.get(cid, ()):
            if nb not in seen:
                dq.append((nb, depth + 1))

    n = len(hits)

    def rrf(cid: str) -> float:
        score = 1.0 / (c + vrank.get(cid, n))
        if cid in grank:
            score += 1.0 / (c + grank[cid])
        return score

    ranked = sorted(by_id.keys(), key=lambda cid: -rrf(cid))
    return [by_id[cid] for cid in ranked[:k]]
