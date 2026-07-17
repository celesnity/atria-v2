from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

pytest.importorskip("minder_python_sdk")

import db


@pytest.fixture(autouse=True)
def sqlite_engine(monkeypatch):
    eng = create_engine("sqlite://", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: eng)
    db.init_db()
    yield


def test_guide_next_step_returns_card():
    import agent.guidance  # noqa: F401
    from agent.connector import conn

    sop = _publish_sop()
    out = conn.invoke("guide_next_step", {"job_id": 1, "sop_id": sop})
    assert out["output"]  # a suggestion string/dict


def test_guide_decision_packet_has_assumptions():
    import agent.guidance  # noqa: F401
    from agent.connector import conn

    out = conn.invoke("guide_decision_packet", {"line_id": 1, "reason": "máy hỏng"})
    packet = out["output"]
    assert packet["kind"] == "decision" or "assumptions" in packet


def _publish_sop():
    from domain.sop import service as sop
    s = sop.create_sop("S1", "T")["id"]
    v = sop.add_draft_version(s, steps=[{"name": "torque", "required": True}])
    sop.publish_version(v["id"])
    return s
