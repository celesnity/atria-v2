import importlib
import os
import sys

BACKEND = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, BACKEND)


def _fresh(monkeypatch, tmp_path):
    monkeypatch.setenv("MT_TEST", "1")
    monkeypatch.setenv("MT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    import db, celery_app, tasks
    importlib.reload(db); importlib.reload(celery_app); importlib.reload(tasks)
    db.init_db()
    return db, tasks


def test_run_job_completes_and_updates_db(monkeypatch, tmp_path):
    db, tasks = _fresh(monkeypatch, tmp_path)
    monkeypatch.setattr(tasks, "_client", lambda: None)      # no reverse-push in unit test
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)  # fast
    with db.db_session() as s:
        s.add(db.MtJob(id=1, kind="demo", status="queued", pct=0))
    res = tasks.run_job.apply(args=(1, None, 2)).get()  # eager
    assert res["ok"] is True
    with db.db_session() as s:
        assert s.get(db.MtJob, 1).status == "done"


def test_run_job_reverse_pushes_when_session(monkeypatch, tmp_path):
    db, tasks = _fresh(monkeypatch, tmp_path)
    pushed = {"updates": 0, "artifact": 0}

    class _FakeClient:
        def push_block(self, sid, comp, props): return "b1"
        def update_block(self, sid, bid, props): pushed["updates"] += 1
        def push_artifact(self, sid, name, data): pushed["artifact"] += 1; return 9

    monkeypatch.setattr(tasks, "_client", lambda: _FakeClient())
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)
    with db.db_session() as s:
        s.add(db.MtJob(id=1, kind="demo", status="queued", pct=0))
    tasks.run_job.apply(args=(1, "sess-1", 3)).get()
    assert pushed["updates"] == 3 and pushed["artifact"] == 1
