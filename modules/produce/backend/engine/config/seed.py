"""Seed one demo workflow: prepare -> measure -> finish, with a threshold."""

from __future__ import annotations

from sqlalchemy.orm import Session

from engine.config.models import PrWorkflow, PrWorkflowVersion

DEMO_GRAPH = {
    "nodes": [
        {"uid": "n-prepare", "node_type": "human", "key": "prepare", "label": "Prepare",
         "position": {"x": 0, "y": 0},
         "config": {"output_contract": {"type": "object"},
                    "instructions": "Prepare the work item.",
                    "assignment_rule": {"by": "role", "value": "worker"}}},
        {"uid": "n-measure", "node_type": "human", "key": "measure", "label": "Measure",
         "position": {"x": 200, "y": 0},
         "config": {"output_contract": {"type": "object",
                        "properties": {"value": {"type": "number", "minimum": 0, "maximum": 10}},
                        "required": ["value"]},
                    "instructions": "Record the measured value (0-10).",
                    "assignment_rule": {"by": "role", "value": "worker"}}},
        {"uid": "n-finish", "node_type": "human", "key": "finish", "label": "Finish",
         "position": {"x": 400, "y": 0},
         "config": {"output_contract": {"type": "object"},
                    "instructions": "Complete the work item.",
                    "assignment_rule": {"by": "role", "value": "worker"}}},
    ],
    "edges": [
        {"from": "prepare", "to": "measure", "branch": "default"},
        {"from": "measure", "to": "finish", "branch": "default"},
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
