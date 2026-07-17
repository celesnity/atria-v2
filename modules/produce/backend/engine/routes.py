"""One thin router mapping HTTP to engine services. No business logic here."""

from __future__ import annotations

import copy

from fastapi import APIRouter, Body, Depends, HTTPException

from engine.analytics import service as an
from engine.config import service as cfg
from engine.config import template_service as tsvc
from engine.config.models import PrReasonCode, PrWorkflow, PrWorkflowVersion
from engine.core import auth
from engine.core.auth import Principal
from engine.db import db_session
from engine.exception import service as ex
from engine.execution import service as exe
from engine.http import get_principal
from engine.nodes import primitives_metadata

router = APIRouter()


def _wi(wi):
    return {"id": wi.id, "status": wi.status, "scope_path": wi.scope_path,
            "current_step_key": wi.current_step_key, "claimed_by": wi.claimed_by}


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/reason-codes")
def reason_codes():
    with db_session() as s:
        return [{"id": r.id, "code": r.code, "label": r.label}
                for r in s.query(PrReasonCode).all()]


@router.post("/work-items")
def create_work_item(body: dict = Body(...), principal: Principal = Depends(get_principal)):
    with db_session() as s:
        def go():
            wi = exe.create_work_item(s, principal, body["workflow_version_id"], body["scope_path"])
            s.flush()
            return _wi(wi)
        return _guard(go)


@router.get("/queue")
def queue(scope_path: str):
    from engine.execution.models import PrWorkItem

    with db_session() as s:
        rows = (
            s.query(PrWorkItem)
            .filter((PrWorkItem.scope_path == scope_path)
                    | (PrWorkItem.scope_path.like(scope_path + "/%")))
            .order_by(PrWorkItem.priority)
            .all()
        )
        return [_wi(w) for w in rows]


def _guard(fn):
    try:
        return fn()
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/work-items/{wid}/claim")
def claim(wid: int, principal: Principal = Depends(get_principal)):
    with db_session() as s:
        return _guard(lambda: _wi(exe.claim(s, principal, wid)))


@router.post("/work-items/{wid}/steps/{step_key}/start")
def start_step(wid: int, step_key: str, principal: Principal = Depends(get_principal)):
    with db_session() as s:
        def go():
            r = exe.start_step(s, principal, wid, step_key)
            s.flush()
            return {"step_run_id": r.id, "step_key": r.step_key}
        return _guard(go)


@router.post("/step-runs/{rid}/output")
def submit_output(rid: int, body: dict = Body(...),
                  principal: Principal = Depends(get_principal)):
    import jsonschema

    with db_session() as s:
        def go():
            r = exe.submit_output(s, principal, rid, body["data"],
                                  body.get("override_reason"))
            return {"step_run_id": r.id, "validated": r.validated,
                    "overridden": r.overridden}
        try:
            return _guard(go)
        except jsonschema.ValidationError as e:
            raise HTTPException(status_code=422, detail=e.message)


@router.post("/interrupts")
def raise_interrupt(body: dict = Body(...),
                    principal: Principal = Depends(get_principal)):
    with db_session() as s:
        def go():
            it = ex.raise_interrupt(s, principal, body["scope_path"],
                                    body["reason_code_id"], body.get("work_item_id"))
            s.flush()
            return {"id": it.id, "status": it.status}
        return _guard(go)


@router.post("/interrupts/{iid}/resolve")
def resolve_interrupt(iid: int, body: dict = Body(...),
                      principal: Principal = Depends(get_principal)):
    with db_session() as s:
        def go():
            it = ex.resolve_interrupt(s, principal, iid, body["disposition"])
            return {"id": it.id, "status": it.status, "disposition": it.disposition}
        return _guard(go)


@router.get("/dashboard")
def dashboard(scope_path: str, target: int = 0):
    with db_session() as s:
        return an.live_dashboard(s, scope_path, target=target)


@router.post("/periods")
def open_period(body: dict = Body(...), principal: Principal = Depends(get_principal)):
    with db_session() as s:
        def go():
            p = an.open_period(s, principal, body["scope_path"])
            s.flush()
            return {"id": p.id, "scope_path": p.scope_path}
        return _guard(go)


@router.post("/periods/{pid}/close")
def close_period(pid: int, body: dict = Body(...),
                 principal: Principal = Depends(get_principal)):
    with db_session() as s:
        def go():
            p = an.close_period(s, principal, pid, target=body.get("target", 0))
            return {"id": p.id, "summary": p.summary}
        return _guard(go)


# ---------------------------------------------------------------------------
# Builder / configuration endpoints
# ---------------------------------------------------------------------------


@router.get("/node-types")
def node_types(scope_path: str = "site"):
    """List all primitive node types and custom templates for a given scope."""
    with db_session() as s:
        templates = [
            {
                "id": t.id,
                "key": t.key,
                "name": t.name,
                "base_kind": t.base_kind,
                "config": t.config,
                "color": t.color,
                "icon": t.icon,
            }
            for t in tsvc.list_templates(s, scope_path)
        ]
    return {"primitives": primitives_metadata(), "templates": templates}


@router.get("/workflows")
def list_workflows(scope_path: str):
    """List workflows at or under the given scope path."""
    with db_session() as s:
        col = PrWorkflow.scope_path
        rows = (
            s.query(PrWorkflow)
            .filter((col == scope_path) | col.like(scope_path + "/%"))
            .all()
        )
        return [
            {
                "id": wf.id,
                "key": wf.key,
                "name": wf.name,
                "scope_path": wf.scope_path,
                "current_version_id": wf.current_version_id,
            }
            for wf in rows
        ]


@router.post("/workflows")
def create_workflow(body: dict = Body(...), principal: Principal = Depends(get_principal)):
    """Create a new workflow definition."""
    with db_session() as s:
        def go():
            auth.require(principal, "configure", body["scope_path"])
            wf = PrWorkflow(
                key=body["key"],
                name=body["name"],
                scope_path=body["scope_path"],
                draft_graph=body.get("graph", {"nodes": [], "edges": []}),
            )
            s.add(wf)
            s.flush()
            return {"id": wf.id, "key": wf.key, "name": wf.name}
        return _guard(go)


@router.patch("/workflows/{wid}")
def update_workflow(wid: int, body: dict = Body(default={}),
                    principal: Principal = Depends(get_principal)):
    """Update mutable workflow fields (currently: name)."""
    with db_session() as s:
        def go():
            wf = s.get(PrWorkflow, wid)
            auth.require(principal, "configure", wf.scope_path)
            if "name" in body:
                wf.name = body["name"]
            return {"id": wf.id, "name": wf.name}
        return _guard(go)


@router.post("/workflows/{wid}/duplicate")
def duplicate_workflow(wid: int, principal: Principal = Depends(get_principal)):
    """Duplicate a workflow (shallow copy of draft_graph)."""
    with db_session() as s:
        def go():
            src = s.get(PrWorkflow, wid)
            auth.require(principal, "configure", src.scope_path)
            dup = PrWorkflow(
                key=src.key + "-copy",
                name=src.name + " (copy)",
                scope_path=src.scope_path,
                draft_graph=copy.deepcopy(src.draft_graph),
            )
            s.add(dup)
            s.flush()
            return {"id": dup.id}
        return _guard(go)


@router.put("/workflows/{wid}/draft")
def put_draft(wid: int, body: dict = Body(...),
              principal: Principal = Depends(get_principal)):
    """Replace the draft graph of a workflow."""
    with db_session() as s:
        def go():
            wf = s.get(PrWorkflow, wid)
            auth.require(principal, "configure", wf.scope_path)
            wf.draft_graph = body["graph"]
            return {"id": wf.id}
        return _guard(go)


@router.post("/workflows/{wid}/validate")
def validate_workflow(wid: int):
    """Validate the current draft graph without publishing."""
    with db_session() as s:
        issues = cfg.validate_draft(s, wid)
    return {"issues": issues}


@router.post("/workflows/{wid}/publish")
def publish_workflow(wid: int, body: dict = Body(default={}),
                     principal: Principal = Depends(get_principal)):
    """Publish the current draft as an immutable version."""
    with db_session() as s:
        def go():
            v = cfg.publish(s, principal, wid, note=body.get("note", ""))
            return {"id": v.id, "version": v.version, "status": v.status}
        return _guard(go)


@router.get("/workflows/{wid}/versions")
def list_versions(wid: int):
    """List all published versions of a workflow ordered by version number."""
    with db_session() as s:
        rows = (
            s.query(PrWorkflowVersion)
            .filter_by(workflow_id=wid)
            .order_by(PrWorkflowVersion.version)
            .all()
        )
        return [
            {
                "id": v.id,
                "version": v.version,
                "status": v.status,
                "note": v.note,
                "published_at": v.published_at.isoformat() if v.published_at else None,
            }
            for v in rows
        ]


@router.post("/workflows/{wid}/versions/{v}/revert")
def revert_version(wid: int, v: int, principal: Principal = Depends(get_principal)):
    """Revert the workflow draft to a previously published version."""
    with db_session() as s:
        def go():
            wf = cfg.revert(s, principal, wid, v)
            return {"id": wf.id}
        return _guard(go)


@router.post("/node-templates")
def create_node_template(body: dict = Body(...),
                         principal: Principal = Depends(get_principal)):
    """Create a custom node template."""
    with db_session() as s:
        def go():
            t = tsvc.create_template(s, principal, body)
            s.flush()
            return {"id": t.id, "key": t.key, "name": t.name}
        return _guard(go)


@router.patch("/node-templates/{tid}")
def update_node_template(tid: int, body: dict = Body(default={}),
                         principal: Principal = Depends(get_principal)):
    """Update a custom node template."""
    with db_session() as s:
        def go():
            t = tsvc.update_template(s, principal, tid, body)
            return {"id": t.id}
        return _guard(go)


@router.delete("/node-templates/{tid}")
def delete_node_template(tid: int, principal: Principal = Depends(get_principal)):
    """Soft-delete a custom node template."""
    with db_session() as s:
        def go():
            tsvc.delete_template(s, principal, tid)
            return {"ok": True}
        return _guard(go)
