"""Worker task smoke test (eager) — in-memory SQLite."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db

# Celery is a worker-container dependency; skip this smoke test when it's absent
# from the dev venv (same philosophy as skipping when no Postgres driver).
pytest.importorskip("celery")


@pytest.fixture(autouse=True)
def sqlite_engine(monkeypatch):
    eng = create_engine("sqlite://", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: eng)
    db.init_db()
    yield


def test_oee_snapshot_task_runs_eager():
    from domain.oee import service
    import tasks

    service.load_production_order(
        line_id=1, shift_id=1, ideal_cycle_time=60, target_count=500, planned_minutes=480
    )
    result = tasks.oee_snapshot.apply(args=(1, 400)).get()
    assert result["shift_id"] == 1
    assert 0.0 <= result["oee"] <= 1.0
