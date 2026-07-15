"""E11 Config & master data — REST routes human-facing (FDE/Admin).

P-CFG-01 line/station/operation · P-CFG-02 master data part có phiên bản.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from . import service

router = APIRouter(prefix="/config", tags=["config"])


# --- request bodies -------------------------------------------------------------
class LineIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)


class StationIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    seq: int = 0


class OperationIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    steps: list[dict] = Field(default_factory=list)
    station_id: int | None = None


class PartIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    ideal_cycle_time: float | None = None


# --- lines ----------------------------------------------------------------------
@router.get("/lines")
def get_lines() -> list[dict]:
    return service.list_lines()


@router.post("/lines")
def post_line(body: LineIn) -> dict:
    return service.create_line(body.code, body.name)


# --- stations -------------------------------------------------------------------
@router.get("/lines/{line_id}/stations")
def get_stations(line_id: int) -> list[dict]:
    return service.list_stations(line_id)


@router.post("/lines/{line_id}/stations")
def post_station(line_id: int, body: StationIn) -> dict:
    return service.create_station(line_id, body.code, body.name, body.seq)


# --- operations (P-CFG-01) ------------------------------------------------------
@router.get("/lines/{line_id}/operations")
def get_operations(line_id: int) -> list[dict]:
    return service.list_operations(line_id)


@router.post("/lines/{line_id}/operations")
def post_operation(line_id: int, body: OperationIn) -> dict:
    return service.create_operation(line_id, body.code, body.name, body.steps, body.station_id)


# --- parts, versioned (P-CFG-02) ------------------------------------------------
@router.get("/parts")
def get_parts() -> list[dict]:
    return service.list_parts()


@router.get("/parts/{code}/latest")
def get_latest_part(code: str) -> dict | None:
    return service.latest_part(code)


@router.post("/parts")
def post_part(body: PartIn) -> dict:
    """Tạo version kế tiếp cho part `code` (không ghi đè)."""
    return service.create_part_version(body.code, body.name, body.ideal_cycle_time)


class ThresholdIn(BaseModel):
    metric: str = Field(min_length=1, max_length=32)
    op: str = Field(default=">", max_length=4)
    value: float


class SkillIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)


@router.get("/lines/{line_id}/thresholds")
def get_thresholds(line_id: int) -> list[dict]:
    return service.list_thresholds(line_id)


@router.post("/lines/{line_id}/thresholds")
def post_threshold(line_id: int, body: ThresholdIn) -> dict:
    return service.create_threshold(line_id, body.metric, body.op, body.value)


@router.get("/skills")
def get_skills() -> list[dict]:
    return service.list_skills()


@router.post("/skills")
def post_skill(body: SkillIn) -> dict:
    return service.create_skill(body.code, body.name)
