"""Extract enterprise entities/relationships from a chunk via the kg_extract LLM.

The LLM is asked for strict JSON. Output is validated against fixed entity/edge
type allow-lists (unknown types are dropped, not trusted), and every surviving
node/edge is stamped with provenance, a confidence score, and
``status="unverified"`` so an LLM-built graph stays auditable.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import budget  # type: ignore[import-not-found]

ALLOWED_ENTITY_TYPES = frozenset(
    {"Policy", "Process", "Concept", "Person", "Org", "Amount", "Date", "Term"}
)
ALLOWED_EDGE_TYPES = frozenset({"RELATED_TO"})

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


@dataclass(frozen=True)
class Entity:
    """A graph node: a typed, keyed entity with stamped props."""

    type: str
    key: str
    props: dict


@dataclass(frozen=True)
class Edge:
    """A graph relationship between two entity keys with stamped props."""

    type: str
    src_key: str
    dst_key: str
    props: dict


@dataclass(frozen=True)
class GraphExtraction:
    """The validated entities and edges extracted from one chunk."""

    entities: list[Entity]
    edges: list[Edge]


def build_extraction_messages(chunk_text: str) -> list[dict]:
    """Build the chat messages that ask the LLM for strict-JSON extraction."""
    system = (
        "You extract a knowledge graph from a Vietnamese enterprise document. "
        "Return ONLY JSON, no prose. Shape: "
        '{"entities":[{"type":<T>,"key":<str>,"props":{}}],'
        '"relationships":[{"type":"RELATED_TO","src":<key>,"dst":<key>,'
        '"confidence":<0-1>}]}. '
        f"Entity types: {sorted(ALLOWED_ENTITY_TYPES)}. "
        "Use a short lowercase slug of the entity name as its key (e.g. "
        "'chinh_sach_nghi_phep'). Link two entities with RELATED_TO only when the "
        "text states a real relationship. Omit anything you are unsure of."
    )
    remaining = budget.input_budget("kg_extract") - budget.estimate_tokens(system) - 16
    chunk_text = budget.fit_text(chunk_text, remaining)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": chunk_text},
    ]


def _confidence(raw: object) -> float:
    """Coerce an item-supplied confidence to a 0–1 float, defaulting to 0.5."""
    if isinstance(raw, (int, float)) and 0.0 <= float(raw) <= 1.0:
        return float(raw)
    return 0.5


def _stamp(props: object, provenance: dict, item: dict) -> dict:
    """Merge model props with provenance + status + confidence."""
    base = dict(props) if isinstance(props, dict) else {}
    base.update(provenance)
    base["status"] = "unverified"
    base["confidence"] = _confidence(item.get("confidence"))
    return base


def parse_extraction(raw: str, provenance: dict) -> GraphExtraction:
    """Parse + validate the LLM's JSON into a :class:`GraphExtraction`.

    Args:
        raw: The raw LLM response (may be fenced with ```json).
        provenance: Keys stamped onto every node/edge (e.g. source_doc, page).

    Returns:
        Validated entities/edges; unknown types are dropped.

    Raises:
        ValueError: If ``raw`` is not JSON or lacks the expected shape.
    """
    cleaned = _FENCE_RE.sub("", raw).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"extraction output is not JSON: {exc}") from exc
    if not isinstance(data, dict) or "entities" not in data or "relationships" not in data:
        raise ValueError("extraction JSON must have 'entities' and 'relationships'")

    entities: list[Entity] = []
    for item in data["entities"]:
        if not isinstance(item, dict) or item.get("type") not in ALLOWED_ENTITY_TYPES:
            continue
        if not item.get("key"):
            continue
        entities.append(Entity(type=item["type"], key=str(item["key"]),
                               props=_stamp(item.get("props"), provenance, item)))

    edges: list[Edge] = []
    for item in data["relationships"]:
        if not isinstance(item, dict) or item.get("type") not in ALLOWED_EDGE_TYPES:
            continue
        if not item.get("src") or not item.get("dst"):
            continue
        edges.append(Edge(type=item["type"], src_key=str(item["src"]),
                          dst_key=str(item["dst"]),
                          props=_stamp(item.get("props"), provenance, item)))
    return GraphExtraction(entities=entities, edges=edges)


def extract_graph(
    chunk_text: str, chat_fn: Callable[[list], str], provenance: dict
) -> GraphExtraction:
    """Run the kg_extract LLM over ``chunk_text`` and parse its output."""
    raw = chat_fn(build_extraction_messages(chunk_text))
    return parse_extraction(raw, provenance)
