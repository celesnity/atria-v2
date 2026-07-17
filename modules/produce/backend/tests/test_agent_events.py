from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

pytest.importorskip("minder_python_sdk")

import db
import events as seam


@pytest.fixture(autouse=True)
def sqlite_engine(monkeypatch):
    eng = create_engine("sqlite://", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: eng)
    db.init_db()
    yield
    seam.clear()


def test_seam_forwards_to_connector_envelopes():
    import agent.events as agent_events
    from agent.connector import conn
    from domain.downtime import service as dt

    captured = []
    conn.on_event(lambda env: captured.append(env.type))
    agent_events.attach()

    d = dt.open_downtime(station_id=1, category="Mech")
    dt.close_downtime(d["id"])
    assert "downtime.opened" in captured
    assert "downtime.closed" in captured
