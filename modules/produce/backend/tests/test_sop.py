"""E2 SOP tests — versioning + poka-yoke (in-memory SQLite)."""

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


def test_publish_retires_previous_approved():
    from domain.sop import service

    sop = service.create_sop("SOP-1", "Assembly")
    v1 = service.add_draft_version(sop["id"], steps=[{"name": "s1"}])
    service.publish_version(v1["id"])
    assert service.released_version(sop["id"])["version"] == 1

    v2 = service.add_draft_version(sop["id"], steps=[{"name": "s1 rev"}])
    service.publish_version(v2["id"])
    rel = service.released_version(sop["id"])
    assert rel["version"] == 2  # v1 retired, chỉ 1 bản approved


def test_pokayoke_blocks_out_of_range_value():
    from domain.sop import service

    sop = service.create_sop("SOP-2", "Torque")
    v = service.add_draft_version(
        sop["id"], steps=[{"name": "torque", "required": True, "min": 10, "max": 20}]
    )
    service.publish_version(v["id"])

    with pytest.raises(service.SopError):
        service.confirm_step(job_id=1, sop_version_id=v["id"], step_index=0, value=25)  # > max
    with pytest.raises(service.SopError):
        service.confirm_step(job_id=1, sop_version_id=v["id"], step_index=0)  # thiếu giá trị

    ok = service.confirm_step(job_id=1, sop_version_id=v["id"], step_index=0, value=15)
    assert ok["value"] == 15


def test_cannot_skip_required_step():
    from domain.sop import service

    sop = service.create_sop("SOP-3", "Multi")
    v = service.add_draft_version(
        sop["id"],
        steps=[{"name": "a", "required": True}, {"name": "b", "required": True}],
    )
    service.publish_version(v["id"])

    with pytest.raises(service.SopError):
        service.confirm_step(job_id=1, sop_version_id=v["id"], step_index=1)  # bỏ qua bước 0

    service.confirm_step(job_id=1, sop_version_id=v["id"], step_index=0)
    service.confirm_step(job_id=1, sop_version_id=v["id"], step_index=1)
    assert len(service.job_progress(1)) == 2
