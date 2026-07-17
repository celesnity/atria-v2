"""Primitive node-type catalog (dict, no class registry). Feeds GET /node-types."""
from __future__ import annotations


def _field(name, type_, required=False, display_name="", description="", options=None):
    return {"name": name, "display_name": display_name or name, "type": type_,
            "required": required, "description": description, "options": options or []}


NODE_TYPES: dict[str, dict] = {
    "begin": {"kind": "begin", "metadata": {
        "display_name": "Begin", "description": "Workflow entry point.",
        "category": "flow", "inputs": []}},
    "end": {"kind": "end", "metadata": {
        "display_name": "End", "description": "Terminal node; completes the work item.",
        "category": "flow", "inputs": []}},
    "human": {"kind": "human", "metadata": {
        "display_name": "Human Step", "description": "A person claims, executes, and submits output.",
        "category": "work", "inputs": [
            _field("output_contract", "json", description="JSON Schema the output must satisfy."),
            _field("instructions", "textarea", description="What the operator must do."),
            _field("assignment_rule", "json", description="Who may execute, e.g. {by: role, value: worker}.")]}},
    "decision": {"kind": "decision", "metadata": {
        "display_name": "Decision", "description": "Auto-routes on a condition over upstream output.",
        "category": "logic", "inputs": [
            _field("condition", "json", required=True,
                   description="{left, operator, right}; left/right may use {{ nodes.X.output.f }}.")]}},
}


def primitives_metadata() -> list[dict]:
    return [{"node_type": nt, **spec["metadata"]} for nt, spec in NODE_TYPES.items()]
