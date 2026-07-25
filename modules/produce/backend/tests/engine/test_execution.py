import jsonschema
import pytest

from engine import db
from engine.config import seed
from engine.core import auth, grant, scope
from engine.execution import models, service


def _worker(session, subject="w1", path="site/lineA"):
    sc = scope.create(session, path, kind="line", name=path)
    session.flush()
    session.add(grant.PrGrant(subject=subject, role="lead", scope_id=sc.id))
    session.flush()
    return auth.load_principal(session, subject)


def _setup(session):
    vid = seed.seed_demo_workflow(session)
    session.flush()
    p = _worker(session)
    wi = service.create_work_item(session, p, vid, "site/lineA/res1")
    session.flush()
    return p, wi


def test_happy_path_claim_execute_submit_complete():
    with db.db_session() as s:
        p, wi = _setup(s)
        service.claim(s, p, wi.id)
        assert wi.status == "claimed"

        r1 = service.start_step(s, p, wi.id, "prepare")
        service.submit_output(s, p, r1.id, {})
        r2 = service.start_step(s, p, wi.id, "measure")
        service.submit_output(s, p, r2.id, {"value": 5.0})
        r3 = service.start_step(s, p, wi.id, "finish")
        service.submit_output(s, p, r3.id, {})
        s.flush()
        assert s.get(models.PrWorkItem, wi.id).status == "completed"


def test_out_of_threshold_output_blocked():
    with db.db_session() as s:
        p, wi = _setup(s)
        service.claim(s, p, wi.id)
        r1 = service.start_step(s, p, wi.id, "prepare")
        service.submit_output(s, p, r1.id, {})
        r2 = service.start_step(s, p, wi.id, "measure")
        with pytest.raises(jsonschema.ValidationError):
            service.submit_output(s, p, r2.id, {"value": 99.0})


def test_out_of_order_step_blocked():
    with db.db_session() as s:
        p, wi = _setup(s)
        service.claim(s, p, wi.id)
        with pytest.raises(ValueError):
            service.start_step(s, p, wi.id, "measure")  # prepare not done


def test_override_records_event():
    from engine.core import eventlog as el

    with db.db_session() as s:
        p, wi = _setup(s)
        service.claim(s, p, wi.id)
        r1 = service.start_step(s, p, wi.id, "prepare")
        service.submit_output(s, p, r1.id, {})
        r2 = service.start_step(s, p, wi.id, "measure")
        run = service.submit_output(s, p, r2.id, {"value": 99.0}, override_reason="cal offset")
        s.flush()
        assert run.overridden is True
        assert s.query(el.PrEvent).filter_by(type="override.logged").count() == 1


def test_blocked_submit_persists_rejection_event():
    from engine.core import eventlog as el

    with db.db_session() as s:
        p, wi = _setup(s)
        service.claim(s, p, wi.id)
        r1 = service.start_step(s, p, wi.id, "prepare")
        service.submit_output(s, p, r1.id, {})
        r2 = service.start_step(s, p, wi.id, "measure")
        with pytest.raises(jsonschema.ValidationError):
            service.submit_output(s, p, r2.id, {"value": 99.0})  # no override
    # rejection event must survive despite the raised exception rolling back the session
    with db.db_session() as s2:
        assert s2.query(el.PrEvent).filter_by(type="step.rejected").count() == 1
