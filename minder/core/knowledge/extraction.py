"""LLM entity/relation extraction for the knowledge graph."""

from __future__ import annotations

import json
import logging
from typing import Any
from typing import Callable

logger = logging.getLogger(__name__)

_ALLOWED_TYPES = {"Concept", "Process", "Policy", "Person", "Org", "Term"}
_SYSTEM = (
    'Extract entities and relations as JSON: {"entities":[{"key","type"}],'
    '"relations":[{"src","dst","confidence"}]}. type in '
    "[Concept,Process,Policy,Person,Org,Term]. key is a lowercase slug. "
    "Only output JSON."
)


def extract_entities(
    text: str, chat_fn: Callable[[list[dict[str, Any]]], str]
) -> tuple[list[tuple[str, str]], list[tuple[str, str, float]]]:
    """Return (entities, relations); ([], []) on any parse/model failure."""
    try:
        raw = chat_fn([{"role": "system", "content": _SYSTEM}, {"role": "user", "content": text}])
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("extraction failed/invalid: %s", exc)
        return [], []
    entities = [
        (e["key"], e["type"])
        for e in data.get("entities", [])
        if e.get("type") in _ALLOWED_TYPES and e.get("key")
    ]
    valid_keys = {k for k, _ in entities}
    relations = [
        (r["src"], r["dst"], float(r.get("confidence", 0.5)))
        for r in data.get("relations", [])
        if r.get("src") in valid_keys and r.get("dst")
    ]
    return entities, relations
