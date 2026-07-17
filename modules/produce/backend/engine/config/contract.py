"""Graph helpers + JSON-Schema output-contract validation (new graph shape)."""
from __future__ import annotations

import jsonschema


def node_by_key(graph: dict, key: str) -> dict:
    for n in graph["nodes"]:
        if n["key"] == key:
            return n
    raise KeyError(key)


def _kind(graph: dict, key: str) -> str:
    return node_by_key(graph, key)["node_type"]


def predecessors(graph: dict, key: str) -> list[str]:
    return [e["from"] for e in graph.get("edges", [])
            if e["to"] == key and _kind(graph, e["from"]) != "decision"]


def out_edges(graph: dict, key: str) -> list[dict]:
    return [e for e in graph.get("edges", []) if e["from"] == key]


def branch_target(graph: dict, key: str, branch: str) -> str | None:
    edges = out_edges(graph, key)
    for e in edges:
        if e.get("branch") == branch:
            return e["to"]
    for e in edges:
        if e.get("branch") == "else":
            return e["to"]
    return None


def next_default(graph: dict, key: str) -> str | None:
    for e in out_edges(graph, key):
        if e.get("branch", "default") == "default":
            return e["to"]
    return None


def validate_output(node: dict, data: dict) -> None:
    schema = (node.get("config") or {}).get("output_contract") or {"type": "object"}
    jsonschema.validate(data, schema)


def _has_default_cycle(graph: dict) -> bool:
    adj: dict[str, list[str]] = {}
    for e in graph.get("edges", []):
        if e.get("branch", "default") == "default":
            adj.setdefault(e["from"], []).append(e["to"])
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n["key"]: WHITE for n in graph["nodes"]}

    def dfs(u: str) -> bool:
        color[u] = GREY
        for v in adj.get(u, []):
            if color.get(v) == GREY or (color.get(v) == WHITE and dfs(v)):
                return True
        color[u] = BLACK
        return False

    return any(color[k] == WHITE and dfs(k) for k in color)


def validate_graph(graph: dict) -> list[str]:
    issues: list[str] = []
    nodes = graph.get("nodes", [])
    keys = {n["key"] for n in nodes}
    begins = [n for n in nodes if n["node_type"] == "begin"]
    ends = [n for n in nodes if n["node_type"] == "end"]
    if len(begins) != 1:
        issues.append(f"graph must have exactly one 'begin' node (found {len(begins)})")
    if not ends:
        issues.append("graph must have at least one 'end' node")
    for e in graph.get("edges", []):
        if e["from"] not in keys:
            issues.append(f"edge references unknown source '{e['from']}'")
        if e["to"] not in keys:
            issues.append(f"edge references unknown target '{e['to']}'")
    # reachability from begin along any edge
    if begins:
        seen, stack = set(), [begins[0]["key"]]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            stack += [e["to"] for e in out_edges(graph, u)]
        if not any(n["key"] in seen for n in ends):
            issues.append("no 'end' node is reachable from 'begin'")
    if _has_default_cycle(graph):
        issues.append("cycle detected among default (non-branch) edges")
    for n in nodes:
        if n["node_type"] == "decision":
            oe = out_edges(graph, n["key"])
            if not oe:
                issues.append(f"decision '{n['key']}' has no outgoing edges")
            elif not any(e.get("branch") == "else" for e in oe):
                issues.append(f"decision '{n['key']}' must have an 'else' branch")
    return issues
