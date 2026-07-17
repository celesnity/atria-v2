"""Batch 5: handover verify (P-HAND-04), material request (P-EXCP-04),
SOP diff (P-EXEC-05), report why-late/trend (P-RPT-04/03)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db


@pytest.fixture(autouse=True)
def sqlite_engine(monkeypatch):
    eng = create_engine("sqlite://", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: eng)
    db.init_db()
    yield


def test_handover_verify_standard():
    from domain.handover import service
    from domain.oee import service as oee

    v0 = service.verify_standard(1)
    assert v0["loaded"] is False

    oee.load_production_order(
        line_id=1, shift_id=1, ideal_cycle_time=60, target_count=500, planned_minutes=480
    )
    v1 = service.verify_standard(1)
    assert v1["loaded"] is True and v1["issues"] == []


def test_material_request_boundary():
    from domain.exception import service

    r = service.request_material(station_id=1, part_code="PN-1", qty=10, requested_by="op1")
    assert r["status"] == "requested"
    assert len(service.open_material_requests()) == 1


def test_sop_diff_last_version():
    from domain.sop import service

    sop = service.create_sop("SOP-D", "Diff")
    service.add_draft_version(sop["id"], steps=[{"name": "a"}, {"name": "b"}])
    v2 = service.add_draft_version(sop["id"], steps=[{"name": "a"}, {"name": "c"}])
    service.publish_version(v2["id"])

    diff = service.diff_last_version(sop["id"])
    assert diff["added"] == ["c"]
    assert diff["removed"] == ["b"]
    assert diff["current_version"] == 2 and diff["previous_version"] == 1


def test_report_why_late_and_trend():
    from domain.downtime import service as dt
    from domain.exception import service as exc
    from domain.oee import service as oee
    from domain.report import service

    dt.raise_andon(line_id=1, station_id=1)  # noise, not counted
    exc.raise_exception(line_id=1, reason="máy hỏng")
    dt.open_downtime(station_id=1, category="Mech", shift_id=1)

    wl = service.why_late(line_id=1, shift_id=1)
    assert len(wl["open_exceptions"]) == 1
    assert "top_downtime_reasons" in wl

    oee.load_production_order(
        line_id=1, shift_id=1, ideal_cycle_time=60, target_count=500, planned_minutes=480
    )
    tr = service.trend([{"shift_id": 1, "total_count": 400}, {"shift_id": 9, "total_count": 0}])
    assert tr[0]["oee"] is not None
    assert tr[1]["oee"] is None  # shift 9 has no production order
