"""Graph helpers + JSON-Schema output-contract validation."""

from __future__ import annotations

import jsonschema


def get_step(graph: dict, step_key: str) -> dict:
    for node in graph["nodes"]:
        if node["key"] == step_key:
            return node
    raise KeyError(step_key)


def entry_step(graph: dict) -> dict:
    for node in graph["nodes"]:
        if not node.get("entry"):
            return node
    raise ValueError("no entry step in graph")


def next_steps(graph: dict, step_key: str) -> list[str]:
    return [e["to"] for e in graph.get("edges", []) if e["from"] == step_key]


def validate_output(step: dict, data: dict) -> None:
    """Validate submitted output against the step's output_contract JSON Schema."""
    schema = step.get("output_contract") or {"type": "object"}
    jsonschema.validate(data, schema)
