import pytest

from engine import db
from engine.config.models import PrReasonCode
from engine.core import auth, grant, scope
from engine.exception import service


def _principal(session, subject, role, path="site/lineA"):
    from engine.core.scope import PrScope
    sc = session.query(PrScope).filter_by(path=path).first()
    if sc is None:
        sc = scope.create(session, path, kind="line", name=path)
        session.flush()
    session.add(grant.PrGrant(subject=subject, role=role, scope_id=sc.id))
    session.flush()
    return auth.load_principal(session, subject)


def _reason(session):
    rc = PrReasonCode(parent_id=None, code="MAT", label="Material shortage")
    session.add(rc)
    session.flush()
    return rc.id


def test_worker_raises_lead_resolves():
    with db.db_session() as s:
        worker = _principal(s, "w1", "worker")
        lead = _principal(s, "l1", "lead")
        rc = _reason(s)
        it = service.raise_interrupt(s, worker, "site/lineA/res1", rc)
        s.flush()
        assert it.status == "open" and it.started_at is not None
        done = service.resolve_interrupt(s, lead, it.id, disposition="fixed")
        assert done.status == "resolved" and done.disposition == "fixed"


def test_worker_cannot_resolve():
    with db.db_session() as s:
        worker = _principal(s, "w2", "worker")
        rc = _reason(s)
        it = service.raise_interrupt(s, worker, "site/lineA/res1", rc)
        s.flush()
        with pytest.raises(PermissionError):
            service.resolve_interrupt(s, worker, it.id, disposition="x")
