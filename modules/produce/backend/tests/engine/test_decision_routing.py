"""Tests for decision auto-fire routing."""
from __future__ import annotations

import pytest

from engine import db
from engine.config.models import PrWorkflow, PrWorkflowVersion
from engine.core import auth, grant, scope
from engine.execution import models, service

# ---------------------------------------------------------------------------
# Local test graph
# ---------------------------------------------------------------------------

_GRAPH_COMPLETE_ON_PASS = {
    "nodes": [
        {
            "uid": "n1", "key": "measure", "node_type": "human",
            "config": {
                "output_contract": {
                    "type": "object",
                    "properties": {"value": {"type": "number"}},
                    "required": ["value"],
                }
            },
        },
        {
            "uid": "n2", "key": "check", "node_type": "decision",
            "config": {
                "condition": {
                    "left": "{{ nodes.measure.output.value }}",
                    "operator": "<=",
                    "right": 10,
                }
            },
        },
        {
            "uid": "n3", "key": "rework", "node_type": "human",
            "config": {"output_contract": {"type": "object"}},
        },
        {
            "uid": "n4", "key": "done", "node_type": "end",
            "config": {},
        },
    ],
    "edges": [
        {"from": "measure", "to": "check", "branch": "default"},
        {"from": "check", "to": "done", "branch": "pass"},
        {"from": "check", "to": "rework", "branch": "else"},
        {"from": "rework", "to": "check", "branch": "default"},
    ],
}

_GRAPH_PACK = {
    "nodes": [
        {
            "uid": "n1", "key": "measure", "node_type": "human",
            "config": {
                "output_contract": {
                    "type": "object",
                    "properties": {"value": {"type": "number"}},
                    "required": ["value"],
                }
            },
        },
        {
            "uid": "n2", "key": "check", "node_type": "decision",
            "config": {
                "condition": {
                    "left": "{{ nodes.measure.output.value }}",
                    "operator": "<=",
                    "right": 10,
                }
            },
        },
        {
            "uid": "n3", "key": "rework", "node_type": "human",
            "config": {"output_contract": {"type": "object"}},
        },
        {
            "uid": "n4", "key": "pack", "node_type": "human",
            "config": {"output_contract": {"type": "object"}},
        },
        {
            "uid": "n5", "key": "done", "node_type": "end",
            "config": {},
        },
    ],
    "edges": [
        {"from": "measure", "to": "check", "branch": "default"},
        {"from": "check", "to": "pack", "branch": "pass"},
        {"from": "check", "to": "rework", "branch": "else"},
        {"from": "rework", "to": "check", "branch": "default"},
        {"from": "pack", "to": "done", "branch": "default"},
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lead(s, subject: str = "w1", path: str = "site/lineA"):
    sc = scope.create(s, path, kind="line", name=path)
    s.flush()
    s.add(grant.PrGrant(subject=subject, role="lead", scope_id=sc.id))
    s.flush()
    return auth.load_principal(s, subject)


def _seed(s, complete_on_pass: bool) -> int:
    graph = _GRAPH_COMPLETE_ON_PASS if complete_on_pass else _GRAPH_PACK
    wf = PrWorkflow(key="dec", name="Dec", scope_path="site/lineA")
    s.add(wf)
    s.flush()
    ver = PrWorkflowVersion(
        workflow_id=wf.id, version=1, status="published", graph=graph
    )
    s.add(ver)
    s.flush()
    return ver.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_pass_completes():
    """value=5 <=10 -> check fires 'pass' -> done -> work item completed."""
    with db.db_session() as s:
        principal = _lead(s)
        ver_id = _seed(s, complete_on_pass=True)
        s.flush()

        wi = service.create_work_item(s, principal, ver_id, "site/lineA")
        s.flush()
        wi_id = wi.id
        service.claim(s, principal, wi_id)
        service.start_step(s, principal, wi_id, "measure")
        service.submit_output(s, principal,
                              s.query(models.PrStepRun)
                               .filter_by(work_item_id=wi_id, step_key="measure")
                               .one().id,
                              {"value": 5.0})
        s.flush()

        check_run = (s.query(models.PrStepRun)
                      .filter_by(work_item_id=wi_id, step_key="check", status="completed")
                      .one())
        assert check_run.output == {"branch": "pass"}

        wi = s.query(models.PrWorkItem).filter_by(id=wi_id).one()
        assert wi.status == "completed"


def test_pass_branch_reachability():
    """value=5 <=10 -> check='pass' -> pack reachable; rework raises ValueError."""
    with db.db_session() as s:
        principal = _lead(s)
        ver_id = _seed(s, complete_on_pass=False)
        s.flush()

        wi = service.create_work_item(s, principal, ver_id, "site/lineA")
        s.flush()
        wi_id = wi.id
        service.claim(s, principal, wi_id)
        service.start_step(s, principal, wi_id, "measure")
        service.submit_output(s, principal,
                              s.query(models.PrStepRun)
                               .filter_by(work_item_id=wi_id, step_key="measure")
                               .one().id,
                              {"value": 5.0})
        s.flush()

        check_run = (s.query(models.PrStepRun)
                      .filter_by(work_item_id=wi_id, step_key="check", status="completed")
                      .one())
        assert check_run.output == {"branch": "pass"}

        # pack is on the taken branch - should succeed
        service.start_step(s, principal, wi_id, "pack")

        # rework is NOT on the taken branch - should raise
        with pytest.raises(ValueError):
            service.start_step(s, principal, wi_id, "rework")


def test_else_routes_to_rework():
    """value=42 >10 -> check='else' -> rework reachable; pack raises ValueError."""
    with db.db_session() as s:
        principal = _lead(s)
        ver_id = _seed(s, complete_on_pass=False)
        s.flush()

        wi = service.create_work_item(s, principal, ver_id, "site/lineA")
        s.flush()
        wi_id = wi.id
        service.claim(s, principal, wi_id)
        service.start_step(s, principal, wi_id, "measure")
        service.submit_output(s, principal,
                              s.query(models.PrStepRun)
                               .filter_by(work_item_id=wi_id, step_key="measure")
                               .one().id,
                              {"value": 42})
        s.flush()

        check_run = (s.query(models.PrStepRun)
                      .filter_by(work_item_id=wi_id, step_key="check", status="completed")
                      .one())
        assert check_run.output == {"branch": "else"}

        # rework is on the taken branch - should succeed
        service.start_step(s, principal, wi_id, "rework")

        # pack is NOT on the taken branch - should raise
        with pytest.raises(ValueError):
            service.start_step(s, principal, wi_id, "pack")
