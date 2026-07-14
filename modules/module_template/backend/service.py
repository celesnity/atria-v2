"""Pure showcase logic for module_template — fake, in-memory, no heavy deps and
never imports ``minder``. Exists only to give the SDK connector something to return."""

from __future__ import annotations

import threading
import time

_ITEMS = [
    {"title": "Getting started", "score": 0.92},
    {"title": "Federated blocks", "score": 0.81},
    {"title": "Reverse-push", "score": 0.66},
    {"title": "Readiness gating", "score": 0.55},
    {"title": "Typed params", "score": 0.44},
]

_warm = threading.Event()


def warm_up(delay: float = 2.0) -> None:
    """Simulate a slow warm-up (index load, model download …)."""
    time.sleep(delay)
    _warm.set()


def is_warm() -> bool:
    return _warm.is_set()


def search(topic: str, limit: int = 3) -> dict:
    hits = _ITEMS[: max(0, int(limit))]
    return {"topic": topic, "count": len(hits), "results": hits}


def report_markdown(topic: str = "demo") -> str:
    lines = [f"# module_template report — {topic}", ""]
    for i, item in enumerate(_ITEMS, 1):
        lines.append(f"{i}. **{item['title']}** — score {item['score']}")
    return "\n".join(lines) + "\n"
