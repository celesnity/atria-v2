"""One thin router mapping HTTP to engine services. No business logic here."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from engine.analytics import service as an
from engine.config.models import PrReasonCode
from engine.core.auth import Principal
from engine.db import db_session
from engine.exception import service as ex
from engine.execution import service as exe
from engine.http import get_principal

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
