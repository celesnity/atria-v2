from engine import db
from engine.core import auth, grant, scope


def _principal(session, subject, role, path):
    sc = scope.create(session, path, kind="line", name=path)
    session.flush()
    session.add(grant.PrGrant(subject=subject, role=role, scope_id=sc.id))
    session.flush()
    return auth.load_principal(session, subject)


def test_worker_can_claim_in_scope_only():
    with db.db_session() as s:
        p = _principal(s, "u1", "worker", "site/lineA")
        assert auth.check(p, "claim", "site/lineA/res1") is True
        assert auth.check(p, "claim", "site/lineB") is False


def test_configurator_cannot_execute():
    with db.db_session() as s:
        p = _principal(s, "u2", "configurator", "site")
        assert auth.check(p, "configure", "site/lineA") is True
        assert auth.check(p, "execute", "site/lineA") is False


def test_require_raises_on_deny():
    import pytest

    with db.db_session() as s:
        p = _principal(s, "u3", "viewer", "site")
        with pytest.raises(PermissionError):
            auth.require(p, "claim", "site/lineA")
