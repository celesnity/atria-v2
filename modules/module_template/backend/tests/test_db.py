import importlib
import os
import sys

BACKEND = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, BACKEND)


def _fresh_db(monkeypatch, tmp_path):
    monkeypatch.setenv("MT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    import db
    importlib.reload(db)
    db.init_db()
    return db


def test_mtjob_roundtrip(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    with db.db_session() as s:
        s.add(db.MtJob(kind="demo", status="queued", pct=0))
    with db.db_session() as s:
        row = s.query(db.MtJob).one()
        assert row.status == "queued" and row.as_dict()["pct"] == 0


def test_atria_reads_degrade_when_tables_absent(monkeypatch, tmp_path):
    # SQLite has no `conversations`/`artifacts` tables → helpers must degrade, not raise.
    db = _fresh_db(monkeypatch, tmp_path)
    assert db.list_conversations() == []
    assert db.count_artifacts() == 0
    assert db.recent_artifacts() == []
