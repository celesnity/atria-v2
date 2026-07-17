# tests/engine/test_graph_validate.py
from engine.config import contract as c

GOOD = {
    "nodes": [
        {"uid": "a", "node_type": "begin", "key": "start", "config": {}},
        {"uid": "b", "node_type": "human", "key": "m", "config": {"output_contract": {"type": "object"}}},
        {"uid": "d", "node_type": "decision", "key": "chk",
         "config": {"condition": {"left": 1, "operator": "<=", "right": 10}}},
        {"uid": "z", "node_type": "end", "key": "done", "config": {}},
    ],
    "edges": [
        {"from": "start", "to": "m", "branch": "default"},
        {"from": "m", "to": "chk", "branch": "default"},
        {"from": "chk", "to": "done", "branch": "pass"},
        {"from": "chk", "to": "done", "branch": "else"},
    ],
}


def test_valid_graph_has_no_issues():
    assert c.validate_graph(GOOD) == []


def test_predecessors_exclude_decision_sources():
    # 'done' has inbound from decision 'chk' only -> no AND-join predecessors
    assert c.predecessors(GOOD, "done") == []
    assert c.predecessors(GOOD, "chk") == ["m"]


def test_branch_target_else_fallback():
    assert c.branch_target(GOOD, "chk", "pass") == "done"
    assert c.branch_target(GOOD, "chk", "nope") == "done"  # else fallback


def test_missing_end_flagged():
    g = {"nodes": [{"uid": "a", "node_type": "begin", "key": "s", "config": {}}], "edges": []}
    assert any("end" in i for i in c.validate_graph(g))


def test_cycle_in_default_edges_flagged():
    g = {
        "nodes": [
            {"uid": "a", "node_type": "begin", "key": "s", "config": {}},
            {"uid": "b", "node_type": "human", "key": "x", "config": {}},
            {"uid": "z", "node_type": "end", "key": "e", "config": {}},
        ],
        "edges": [
            {"from": "s", "to": "x", "branch": "default"},
            {"from": "x", "to": "s", "branch": "default"},
            {"from": "x", "to": "e", "branch": "default"},
        ],
    }
    assert any("cycle" in i.lower() for i in c.validate_graph(g))
