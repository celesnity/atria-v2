"""E1 Giao việc & hàng đợi — REST routes human-facing.

Operator: hàng đợi (P-WORK-01), nhận task (P-WORK-02).
Tổ trưởng: gán/gán lại (P-WORK-04), board tổ (P-WORK-05).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import service

router = APIRouter(prefix="/work", tags=["work"])


class ShiftIn(BaseModel):
    line_id: int
    name: str = Field(min_length=1, max_length=64)
    supervisor_id: str | None = None


class TaskIn(BaseModel):
    line_id: int
    shift_id: int | None = None
    station_id: int | None = None
    operation_id: int | None = None
    part_id: int | None = None
    priority: int = 100


class AssignIn(BaseModel):
    assignee_id: str = Field(min_length=1, max_length=64)


class StatusIn(BaseModel):
    status: str


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.WorkError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/shifts")
def post_shift(body: ShiftIn) -> dict:
    return service.create_shift(body.line_id, body.name, body.supervisor_id)


@router.post("/tasks")
def post_task(body: TaskIn) -> dict:
    return service.create_task(
        body.line_id,
        shift_id=body.shift_id,
        station_id=body.station_id,
        operation_id=body.operation_id,
        part_id=body.part_id,
        priority=body.priority,
    )


@router.get("/queue/{assignee_id}")
def get_queue(assignee_id: str) -> list[dict]:
    """Hàng đợi của operator theo ưu tiên (P-WORK-01)."""
    return service.operator_queue(assignee_id)


@router.get("/board/{line_id}")
def get_board(line_id: int, shift_id: int | None = None) -> list[dict]:
    """Board trạng thái mọi task của tổ (P-WORK-05)."""
    return service.team_board(line_id, shift_id)


@router.get("/shift/{shift_id}/load")
def get_shift_load(shift_id: int) -> list[dict]:
    """Tải công việc mọi line trong ca — cho quản ca (P-WORK-06)."""
    return service.shift_load(shift_id)


@router.post("/tasks/{task_id}/assign")
def post_assign(task_id: int, body: AssignIn) -> dict:
    """Tổ trưởng gán/gán lại (P-WORK-04)."""
    return _guard(service.assign_task, task_id, body.assignee_id)


@router.post("/tasks/{task_id}/claim")
def post_claim(task_id: int, body: AssignIn) -> dict:
    """Operator nhận task, đánh dấu đang làm (P-WORK-02)."""
    return _guard(service.claim_task, task_id, body.assignee_id)


@router.post("/tasks/{task_id}/status")
def post_status(task_id: int, body: StatusIn) -> dict:
    return _guard(service.set_status, task_id, body.status)
