"""E7 Setup & changeover — logic thuần trên DB.

Bắt đầu changeover theo checklist (P-SETUP-01), ghi thời gian (P-SETUP-02), kiểm
first-piece trước khi chạy loạt (P-SETUP-03). to_part_id là standard mới cho ca
sau (P-SETUP-04). Không đóng changeover nếu checklist còn bước chưa done.
"""

from __future__ import annotations

from sqlalchemy import select

from db import db_session, now

from .models import PrChangeover, PrFirstPiece


class SetupError(Exception):
    """Vi phạm luật nghiệp vụ E7."""


def start_changeover(
    line_id: int,
    to_part_id: int,
    checklist: list[dict],
    *,
    station_id: int | None = None,
    from_part_id: int | None = None,
) -> dict:
    with db_session() as s:
        c = PrChangeover(
            line_id=line_id,
            to_part_id=to_part_id,
            checklist=checklist,
            station_id=station_id,
            from_part_id=from_part_id,
        )
        s.add(c)
        s.flush()
        return c.as_dict()


def complete_changeover(changeover_id: int) -> dict:
    with db_session() as s:
        c = s.get(PrChangeover, changeover_id)
        if c is None:
            raise SetupError(f"changeover {changeover_id} không tồn tại")
        if any(not step.get("done") for step in (c.checklist or [])):
            raise SetupError("checklist changeover còn bước chưa hoàn thành")
        c.ended_at = now()
        s.flush()
        return c.as_dict()


def record_first_piece(changeover_id: int, passed: bool, note: str | None = None) -> dict:
    """Kiểm first-piece (P-SETUP-03) — chạy loạt chỉ khi passed."""
    with db_session() as s:
        if s.get(PrChangeover, changeover_id) is None:
            raise SetupError(f"changeover {changeover_id} không tồn tại")
        fp = PrFirstPiece(changeover_id=changeover_id, passed=passed, note=note)
        s.add(fp)
        s.flush()
        return fp.as_dict()


def open_changeovers(line_id: int) -> list[dict]:
    with db_session() as s:
        stmt = (
            select(PrChangeover)
            .where(PrChangeover.line_id == line_id, PrChangeover.ended_at.is_(None))
            .order_by(PrChangeover.started_at)
        )
        return [r.as_dict() for r in s.scalars(stmt).all()]
