"""HTTP integration tests for the builder/workflow-management routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from engine import db
from engine.core import grant, scope


GOOD = {
    "nodes": [
        {"uid": "a", "node_type": "begin", "key": "start", "config": {}},
        {"uid": "b", "node_type": "human", "key": "m",
         "config": {"output_contract": {"type": "object"}}},
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


@pytest.fixture()
def client():
    """TestClient with dev principal granted configurator on site/lineA."""
    # Grant must be set up BEFORE create_app so the lifespan sees the same db engine.
    with db.db_session() as s:
        sc = scope.create(s, "site/lineA", kind="line", name="lineA")
        s.flush()
        s.add(grant.PrGrant(subject="dev", role="configurator", scope_id=sc.id))

    from engine.app import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


def test_node_types_lists_primitives(client):
    """GET /node-types returns all four primitive node types."""
    resp = client.get("/node-types")
    assert resp.status_code == 200
    data = resp.json()
    node_types = {p["node_type"] for p in data["primitives"]}
    assert node_types == {"begin", "end", "human", "decision"}


def test_create_draft_validate_publish_roundtrip(client):
    """Create workflow, PUT draft, validate, then publish at version 1."""
    # Create
    created = client.post("/workflows", json={
        "key": "test-wf",
        "name": "Test Workflow",
        "scope_path": "site/lineA",
    })
    assert created.status_code == 200, created.text
    wid = created.json()["id"]

    # PUT draft
    put = client.put(f"/workflows/{wid}/draft", json={"graph": GOOD})
    assert put.status_code == 200, put.text

    # Validate
    val = client.post(f"/workflows/{wid}/validate")
    assert val.status_code == 200, val.text
    assert val.json()["issues"] == []

    # Publish
    pub = client.post(f"/workflows/{wid}/publish", json={"note": "initial"})
    assert pub.status_code == 200, pub.text
    pub_data = pub.json()
    assert pub_data["version"] == 1
    assert pub_data["status"] == "published"


def test_list_workflows_scoped(client):
    """GET /workflows returns workflows filtered by scope_path."""
    client.post("/workflows", json={
        "key": "wf-line",
        "name": "Line WF",
        "scope_path": "site/lineA",
    })
    resp = client.get("/workflows", params={"scope_path": "site/lineA"})
    assert resp.status_code == 200
    keys = [w["key"] for w in resp.json()]
    assert "wf-line" in keys


def test_update_workflow_name(client):
    """PATCH /workflows/{wid} updates workflow name."""
    wf = client.post("/workflows", json={
        "key": "wf-rename",
        "name": "Old Name",
        "scope_path": "site/lineA",
    }).json()
    wid = wf["id"]
    resp = client.patch(f"/workflows/{wid}", json={"name": "New Name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


def test_duplicate_workflow(client):
    """POST /workflows/{wid}/duplicate creates an independent deep copy."""
    from engine.config.models import PrWorkflow

    wf = client.post("/workflows", json={
        "key": "wf-orig",
        "name": "Original",
        "scope_path": "site/lineA",
    }).json()
    wid = wf["id"]
    # Set a known draft_graph before duplicating
    client.put(f"/workflows/{wid}/draft", json={"graph": GOOD})
    resp = client.post(f"/workflows/{wid}/duplicate")
    assert resp.status_code == 200
    dup_id = resp.json()["id"]
    assert dup_id != wid
    # The duplicated workflow's draft_graph must equal the source's
    with db.db_session() as s:
        dup_graph = s.get(PrWorkflow, dup_id).draft_graph
    assert dup_graph == GOOD


def test_list_versions(client):
    """GET /workflows/{wid}/versions returns published versions."""
    wf = client.post("/workflows", json={
        "key": "wf-versions",
        "name": "Versioned WF",
        "scope_path": "site/lineA",
    }).json()
    wid = wf["id"]
    client.put(f"/workflows/{wid}/draft", json={"graph": GOOD})
    client.post(f"/workflows/{wid}/publish", json={})
    resp = client.get(f"/workflows/{wid}/versions")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["version"] == 1


def test_revert_version(client):
    """POST /workflows/{wid}/versions/{v}/revert restores the draft to the published graph."""
    from engine.config.models import PrWorkflow

    wf = client.post("/workflows", json={
        "key": "wf-revert",
        "name": "Revert WF",
        "scope_path": "site/lineA",
    }).json()
    wid = wf["id"]
    # Publish GOOD as v1
    client.put(f"/workflows/{wid}/draft", json={"graph": GOOD})
    client.post(f"/workflows/{wid}/publish", json={})
    # Overwrite draft with a DIFFERENT graph
    different = {"nodes": [
        {"uid": "x", "node_type": "begin", "key": "s", "config": {}},
        {"uid": "y", "node_type": "end", "key": "e", "config": {}},
    ], "edges": [{"from": "s", "to": "e", "branch": "default"}]}
    client.put(f"/workflows/{wid}/draft", json={"graph": different})
    # Revert to v1
    resp = client.post(f"/workflows/{wid}/versions/1/revert")
    assert resp.status_code == 200
    assert resp.json()["id"] == wid
    # Verify draft was restored to GOOD
    with db.db_session() as s:
        restored = s.get(PrWorkflow, wid).draft_graph
    assert restored == GOOD


def test_node_template_crud(client):
    """Create, update, and delete a node template."""
    tmpl = client.post("/node-templates", json={
        "key": "t1",
        "name": "Template 1",
        "base_kind": "human",
        "scope_path": "site/lineA",
        "config": {},
    })
    assert tmpl.status_code == 200, tmpl.text
    tid = tmpl.json()["id"]

    upd = client.patch(f"/node-templates/{tid}", json={"name": "Updated Template"})
    assert upd.status_code == 200

    del_resp = client.delete(f"/node-templates/{tid}")
    assert del_resp.status_code == 200
    assert del_resp.json()["ok"] is True

    # After delete, template should not appear in /node-types
    node_types = client.get("/node-types").json()
    template_keys = [t["key"] for t in node_types["templates"]]
    assert "t1" not in template_keys
