"""E11 Config & master data — logic thuần trên DB (không side-effect ngoài DB).

FDE/Admin: định nghĩa line/station/operation (P-CFG-01) và master data part có
phiên bản (P-CFG-02). Part mới không ghi đè bản cũ — tạo version kế tiếp.
"""

from __future__ import annotations

from sqlalchemy import select

from db import db_session

from .models import PrLine, PrOperation, PrPart, PrStation


# --- Line -----------------------------------------------------------------------
def create_line(code: str, name: str) -> dict:
    with db_session() as s:
        line = PrLine(code=code, name=name)
        s.add(line)
        s.flush()
        return line.as_dict()


def list_lines() -> list[dict]:
    with db_session() as s:
        return [r.as_dict() for r in s.scalars(select(PrLine).order_by(PrLine.id)).all()]


# --- Station --------------------------------------------------------------------
def create_station(line_id: int, code: str, name: str, seq: int = 0) -> dict:
    with db_session() as s:
        st = PrStation(line_id=line_id, code=code, name=name, seq=seq)
        s.add(st)
        s.flush()
        return st.as_dict()


def list_stations(line_id: int) -> list[dict]:
    with db_session() as s:
        stmt = select(PrStation).where(PrStation.line_id == line_id).order_by(PrStation.seq)
        return [r.as_dict() for r in s.scalars(stmt).all()]


# --- Operation (P-CFG-01) -------------------------------------------------------
def create_operation(
    line_id: int, code: str, name: str, steps: list[dict] | None = None, station_id: int | None = None
) -> dict:
    with db_session() as s:
        op = PrOperation(
            line_id=line_id, code=code, name=name, steps=steps or [], station_id=station_id
        )
        s.add(op)
        s.flush()
        return op.as_dict()


def list_operations(line_id: int) -> list[dict]:
    with db_session() as s:
        stmt = select(PrOperation).where(PrOperation.line_id == line_id).order_by(PrOperation.id)
        return [r.as_dict() for r in s.scalars(stmt).all()]


# --- Part master data, versioned (P-CFG-02) -------------------------------------
def create_part_version(
    code: str, name: str, ideal_cycle_time: float | None = None
) -> dict:
    """Tạo bản version kế tiếp cho `code` (không ghi đè bản cũ)."""
    with db_session() as s:
        latest = s.scalars(
            select(PrPart).where(PrPart.code == code).order_by(PrPart.version.desc())
        ).first()
        next_version = (latest.version + 1) if latest else 1
        part = PrPart(
            code=code, version=next_version, name=name, ideal_cycle_time=ideal_cycle_time
        )
        s.add(part)
        s.flush()
        return part.as_dict()


def latest_part(code: str) -> dict | None:
    with db_session() as s:
        row = s.scalars(
            select(PrPart).where(PrPart.code == code).order_by(PrPart.version.desc())
        ).first()
        return row.as_dict() if row else None


def list_parts() -> list[dict]:
    with db_session() as s:
        return [r.as_dict() for r in s.scalars(select(PrPart).order_by(PrPart.code, PrPart.version)).all()]
