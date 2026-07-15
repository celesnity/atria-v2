"""E11 Config tests — run against in-memory SQLite (no Postgres driver needed).

Rebinds the lazy engine to sqlite:///:memory: so pr_* tables are created and
exercised without a real database.
"""

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


def test_line_station_operation_flow():
    from domain.config import service

    line = service.create_line("L1", "Line 1")
    assert line["id"] and line["code"] == "L1"

    st = service.create_station(line["id"], "S1", "Station 1", seq=1)
    assert st["line_id"] == line["id"]
    assert service.list_stations(line["id"])[0]["code"] == "S1"

    op = service.create_operation(
        line["id"], "OP-10", "Assemble", steps=[{"name": "torque", "required": True}]
    )
    assert op["steps"][0]["required"] is True
    assert service.list_operations(line["id"])[0]["code"] == "OP-10"


def test_part_versioning_does_not_overwrite():
    from domain.config import service

    v1 = service.create_part_version("PN-1", "Widget", ideal_cycle_time=12.0)
    v2 = service.create_part_version("PN-1", "Widget rev B", ideal_cycle_time=11.5)
    assert v1["version"] == 1
    assert v2["version"] == 2
    assert service.latest_part("PN-1")["version"] == 2
    assert len(service.list_parts()) == 2


def test_threshold_and_skill_crud():
    from domain.config import service

    line = service.create_line("L9", "Line 9")["id"]
    th = service.create_threshold(line, "downtime_minutes", ">", 15)
    assert th["metric"] == "downtime_minutes" and th["op"] == ">"
    assert service.list_thresholds(line)[0]["value"] == 15

    sk = service.create_skill("WELD", "Welding")
    assert sk["code"] == "WELD"
    assert service.list_skills()[0]["name"] == "Welding"
