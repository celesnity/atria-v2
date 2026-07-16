"""Seed one demo workflow: prepare -> measure -> finish, with a threshold."""

from __future__ import annotations

from sqlalchemy.orm import Session

from engine.config.models import PrWorkflow, PrWorkflowVersion

DEMO_GRAPH = {
    "nodes": [
        {
            "key": "prepare",
            "name": "Prepare",
            "assignment_rule": {"by": "role", "value": "worker"},
            "output_contract": {"type": "object"},
            "entry": [],
            "instructions": "Prepare the work item.",
        },
        {
            "key": "measure",
            "name": "Measure",
            "assignment_rule": {"by": "role", "value": "worker"},
            "output_contract": {
                "type": "object",
                "properties": {"value": {"type": "number", "minimum": 0, "maximum": 10}},
                "required": ["value"],
            },
            "entry": ["prepare"],
            "instructions": "Record the measured value (0-10).",
        },
        {
            "key": "finish",
            "name": "Finish",
            "assignment_rule": {"by": "role", "value": "worker"},
            "output_contract": {"type": "object"},
            "entry": ["measure"],
            "instructions": "Complete the work item.",
        },
    ],
    "edges": [
        {"from": "prepare", "to": "measure"},
        {"from": "measure", "to": "finish"},
    ],
}


def seed_demo_workflow(session: Session) -> int:
    wf = PrWorkflow(key="demo", name="Demo Workflow", scope_path="site/lineA")
    session.add(wf)
    session.flush()
    version = PrWorkflowVersion(
        workflow_id=wf.id, version=1, status="published", graph=DEMO_GRAPH
    )
    session.add(version)
    session.flush()
    wf.current_version_id = version.id
    return version.id
