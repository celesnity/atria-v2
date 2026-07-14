"""In-memory product catalog for the co-pilot / agent-surface demo.

Deliberately tiny and process-local (resets on restart) — the point is to show
the v3 SDK surface (risk gate, events, UI-driving), not persistence.
"""

from __future__ import annotations

import itertools
import threading

_lock = threading.Lock()
_counter = itertools.count(1)
_products: dict[int, dict] = {}


def create(sku: str, name: str, price: float, category: str = "", stock: int = 0) -> dict:
    with _lock:
        pid = next(_counter)
        p = {
            "id": pid,
            "sku": sku,
            "name": name,
            "price": float(price),
            "category": category or "",
            "stock": int(stock),
        }
        _products[pid] = p
        return dict(p)


def list_products() -> list[dict]:
    with _lock:
        return [dict(p) for p in sorted(_products.values(), key=lambda p: p["id"])]


def get(pid: int) -> dict | None:
    with _lock:
        p = _products.get(pid)
        return dict(p) if p else None


def delete(pid: int) -> dict | None:
    with _lock:
        return _products.pop(pid, None)


def set_price(pid: int, price: float) -> dict | None:
    with _lock:
        p = _products.get(pid)
        if p is None:
            return None
        p["price"] = float(price)
        return dict(p)


def restock(pid: int, qty: int) -> dict | None:
    with _lock:
        p = _products.get(pid)
        if p is None:
            return None
        p["stock"] += int(qty)
        return dict(p)


def _full_graph() -> tuple[list[dict], list[dict]]:
    """The catalog as an Operational Graph: product + category nodes, joined by
    ``in_category`` edges. Small and derived on the fly (the catalog is the
    source of truth) — enough to show BE-SDK-10 linked-context queries."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    for p in list_products():
        pid = f"product:{p['id']}"
        nodes[pid] = {
            "id": pid,
            "kind": "product",
            "label": p["name"],
            "sku": p["sku"],
            "price": p["price"],
            "stock": p["stock"],
        }
        cat = p["category"] or "uncategorized"
        cid = f"category:{cat}"
        nodes.setdefault(cid, {"id": cid, "kind": "category", "label": cat})
        edges.append({"from": pid, "to": cid, "rel": "in_category"})
    return list(nodes.values()), edges


def graph(node: str | None = None, depth: int = 1) -> dict:
    """Linked context around ``node`` out to ``depth`` hops (whole graph when
    ``node`` is None). Undirected BFS over the ``in_category`` edges."""
    nodes, edges = _full_graph()
    if not node:
        return {"nodes": nodes, "edges": edges, "focus": None}

    by_id = {n["id"]: n for n in nodes}
    if node not in by_id:
        return {"nodes": [], "edges": [], "focus": node, "available": True}

    adj: dict[str, set[str]] = {}
    for e in edges:
        adj.setdefault(e["from"], set()).add(e["to"])
        adj.setdefault(e["to"], set()).add(e["from"])

    seen = {node}
    frontier = {node}
    for _ in range(max(1, depth)):
        nxt: set[str] = set()
        for n in frontier:
            nxt |= adj.get(n, set()) - seen
        seen |= nxt
        frontier = nxt

    sub_edges = [e for e in edges if e["from"] in seen and e["to"] in seen]
    return {
        "nodes": [by_id[n] for n in seen],
        "edges": sub_edges,
        "focus": node,
    }


def _seed() -> None:
    if not _products:
        create("SKU-001", "Aurora Lamp", 39.0, "A", 12)
        create("SKU-002", "Nimbus Speaker", 89.0, "B", 5)


_seed()
