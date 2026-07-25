"""Auto-fire decision nodes after a human step completes."""
from __future__ import annotations

from sqlalchemy.orm import Session

from engine.config import contract
from engine.core import eventlog as el
from engine.core.conditions import evaluate_condition
from engine.core.expressions import resolve
from engine.db import now
from engine.execution.models import PrStepRun


def _completed_outputs(session: Session, wi_id: int) -> dict[str, dict]:
    rows = (session.query(PrStepRun)
            .filter_by(work_item_id=wi_id, status="completed")
            .order_by(PrStepRun.id).all())
    return {r.step_key: (r.output or {}) for r in rows}


def resolve_decisions(session: Session, wi, graph: dict, from_key: str, actor: str) -> None:
    """Walk default edges from `from_key`; fire each decision until a human/end/dead-end.

    A decision that loops back (else → …) must route to a human step that re-produces
    the output its condition reads, or the loop cannot converge.
    """
    cur = contract.next_default(graph, from_key)
    guard = len(graph["nodes"]) + 10
    while cur is not None and guard > 0:
        guard -= 1
        node = contract.node_by_key(graph, cur)
        if node["node_type"] != "decision":
            return  # human (or other) node — operator drives it; stop
        cond = dict(node["config"]["condition"])
        outs = _completed_outputs(session, wi.id)
        cond["left"] = resolve(cond.get("left"), outs, {})
        cond["right"] = resolve(cond.get("right"), outs, {})
        branch = "pass" if evaluate_condition(cond) else "else"
        run = PrStepRun(
            work_item_id=wi.id, step_key=cur, status="completed",
            started_at=now(), completed_at=now(), assignee=actor,
            output={"branch": branch}, validated=True,
        )
        session.add(run)
        session.flush()
        el.emit(
            session, type=el.STEP_OUTPUT_SUBMITTED, scope_path=wi.scope_path,
            actor_subject=actor, payload={"step_run_id": run.id},
            work_item_id=wi.id, step_run_id=run.id,
        )
        target = contract.branch_target(graph, cur, branch)
        if target is None:
            return
        tnode = contract.node_by_key(graph, target)
        if tnode["node_type"] == "end":
            wi.status = "completed"
            wi.current_step_key = None
            el.emit(
                session, type=el.WORK_ITEM_COMPLETED, scope_path=wi.scope_path,
                actor_subject=actor, payload={"work_item_id": wi.id}, work_item_id=wi.id,
            )
            return
        cur = target if tnode["node_type"] == "decision" else None
