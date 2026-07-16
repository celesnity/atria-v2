"""E2 Thực thi có hướng dẫn & e-SOP — REST routes human-facing.

FDE/Admin: tạo SOP, version, phát hành bản duyệt (P-EXEC-06).
Operator: xem bản hành, xác nhận bước (P-EXEC-01/02/03/04).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import service

router = APIRouter(prefix="/sop", tags=["sop"])


class SopIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=128)
    operation_id: int | None = None


class VersionIn(BaseModel):
    steps: list[dict] = Field(default_factory=list)


class ConfirmIn(BaseModel):
    job_id: int
    sop_version_id: int
    step_index: int = Field(ge=0)
    value: float | None = None


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.SopError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/sops")
def get_sops() -> list[dict]:
    """All SOPs for pickers."""
    return service.list_sops()


@router.post("/sops")
def post_sop(body: SopIn) -> dict:
    return service.create_sop(body.code, body.title, body.operation_id)


@router.post("/sops/{sop_id}/versions")
def post_version(sop_id: int, body: VersionIn) -> dict:
    return service.add_draft_version(sop_id, body.steps)


@router.post("/versions/{version_id}/publish")
def post_publish(version_id: int) -> dict:
    return _guard(service.publish_version, version_id)


@router.get("/sops/{sop_id}/released")
def get_released(sop_id: int) -> dict | None:
    """Bản approved hiện hành (P-EXEC-01)."""
    return service.released_version(sop_id)


@router.post("/step-confirms")
def post_confirm(body: ConfirmIn) -> dict:
    """Xác nhận bước — poka-yoke chặn giá trị/bước sai (P-EXEC-02/03/04)."""
    return _guard(
        service.confirm_step, body.job_id, body.sop_version_id, body.step_index, body.value
    )


@router.get("/jobs/{job_id}/progress")
def get_progress(job_id: int) -> list[dict]:
    return service.job_progress(job_id)


@router.get("/sops/{sop_id}/diff")
def get_diff(sop_id: int) -> dict:
    """Cái gì đã đổi so với bản trước (P-EXEC-05)."""
    return _guard(service.diff_last_version, sop_id)
