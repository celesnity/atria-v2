"""E3 WIP & bước sản xuất — REST routes human-facing (Operator).

Job start/complete (P-WIP-01), count (P-WIP-02), station status (P-WIP-03),
quét QR lot (P-WIP-06).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import service

router = APIRouter(prefix="/wip", tags=["wip"])


class JobIn(BaseModel):
    task_id: int
    station_id: int | None = None
    operator_id: str | None = None


class StepIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    seq: int = 0


class CountIn(BaseModel):
    station_id: int
    qty: int = Field(ge=0)
    job_id: int | None = None


class StationStatusIn(BaseModel):
    status: str


class ScanIn(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    kind: str = "lot"


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.WipError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/jobs")
def post_job(body: JobIn) -> dict:
    return service.start_job(body.task_id, body.station_id, body.operator_id)


@router.post("/jobs/{job_id}/complete")
def post_complete(job_id: int) -> dict:
    return _guard(service.complete_job, job_id)


@router.post("/jobs/{job_id}/steps")
def post_step(job_id: int, body: StepIn) -> dict:
    return service.add_job_step(job_id, body.name, body.seq)


@router.post("/jobs/{job_id}/scan")
def post_scan(job_id: int, body: ScanIn) -> dict:
    return service.scan_lot(job_id, body.code, body.kind)


@router.get("/jobs/{job_id}/lots")
def get_lots(job_id: int) -> list[dict]:
    return service.job_lots(job_id)


@router.post("/counts")
def post_count(body: CountIn) -> dict:
    return service.record_count(body.station_id, body.qty, body.job_id)


@router.get("/stations/{station_id}/total")
def get_total(station_id: int) -> dict:
    return {"station_id": station_id, "total": service.station_total(station_id)}


@router.put("/stations/{station_id}/status")
def put_station_status(station_id: int, body: StationStatusIn) -> dict:
    return _guard(service.set_station_status, station_id, body.status)


@router.get("/stations/{station_id}/status")
def get_station_status(station_id: int) -> dict | None:
    return service.get_station_status(station_id)
