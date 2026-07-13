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


def _seed() -> None:
    if not _products:
        create("SKU-001", "Aurora Lamp", 39.0, "A", 12)
        create("SKU-002", "Nimbus Speaker", 89.0, "B", 5)


_seed()
