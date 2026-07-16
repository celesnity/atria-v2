from engine import db
from engine.analytics import service as an
from engine.config import seed
from engine.config.models import PrReasonCode
from engine.core import auth, grant, scope
from engine.exception import service as ex
from engine.execution import service as exe


def _principal(session, subject, role, path="site/lineA"):
    from engine.core.scope import PrScope
    sc = session.query(PrScope).filter_by(path=path).first()
    if sc is None:
        sc = scope.create(session, path, kind="line", name=path)
        session.flush()
    session.add(grant.PrGrant(subject=subject, role=role, scope_id=sc.id))
    session.flush()
    return auth.load_principal(session, subject)


def _complete_one_item(session, principal):
    vid = seed.seed_demo_workflow(session)
    session.flush()
    wi = exe.create_work_item(session, vid, "site/lineA/res1")
    session.flush()
    exe.claim(session, principal, wi.id)
    for key in ("prepare", "measure", "finish"):
        r = exe.start_step(session, principal, wi.id, key)
        exe.submit_output(session, principal, r.id, {"value": 5.0} if key == "measure" else {})


def test_dashboard_counts_throughput_and_open_interrupts():
    with db.db_session() as s:
        sup = _principal(s, "s1", "supervisor")
        _complete_one_item(s, sup)
        rc = PrReasonCode(parent_id=None, code="MAT", label="Mat")
        s.add(rc)
        s.flush()
        ex.raise_interrupt(s, sup, "site/lineA/res1", rc.id)
        s.flush()
        dash = an.live_dashboard(s, "site/lineA", target=1)
        assert dash["throughput"] == 1
        assert dash["open_interrupts"] == 1
        assert dash["target"] == 1


def test_close_period_snapshots_summary():
    with db.db_session() as s:
        sup = _principal(s, "s2", "supervisor")
        _complete_one_item(s, sup)
        p = an.open_period(s, "site/lineA")
        s.flush()
        closed = an.close_period(s, sup, p.id, target=1)
        assert closed.closed_at is not None
        assert closed.summary["throughput"] == 1
