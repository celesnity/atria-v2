"""E7 Setup & changeover — REST routes human-facing (Operator).

Changeover checklist (P-SETUP-01), thời gian (P-SETUP-02), first-piece
(P-SETUP-03); to_part_id = standard mới (P-SETUP-04).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import service

router = APIRouter(prefix="/setup", tags=["setup"])


class ChangeoverIn(BaseModel):
    line_id: int
    to_part_id: int
    checklist: list[dict] = Field(default_factory=list)
    station_id: int | None = None
    from_part_id: int | None = None


class FirstPieceIn(BaseModel):
    passed: bool
    note: str | None = None


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.SetupError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/changeovers")
def post_changeover(body: ChangeoverIn) -> dict:
    return service.start_changeover(
        body.line_id,
        body.to_part_id,
        body.checklist,
        station_id=body.station_id,
        from_part_id=body.from_part_id,
    )


@router.post("/changeovers/{changeover_id}/complete")
def post_complete(changeover_id: int) -> dict:
    return _guard(service.complete_changeover, changeover_id)


@router.post("/changeovers/{changeover_id}/first-piece")
def post_first_piece(changeover_id: int, body: FirstPieceIn) -> dict:
    return _guard(service.record_first_piece, changeover_id, body.passed, body.note)


@router.get("/line/{line_id}/open")
def get_open(line_id: int) -> list[dict]:
    return service.open_changeovers(line_id)
