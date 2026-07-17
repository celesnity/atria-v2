import pytest

from engine import db
from engine.core import eventlog as el


def test_emit_valid_event_persists_with_seq():
    with db.db_session() as s:
        ev = el.emit(
            s,
            type=el.WORK_ITEM_CLAIMED,
            scope_path="site/lineA",
            actor_subject="u1",
            payload={"work_item_id": 1},
            work_item_id=1,
        )
        s.flush()
        assert ev.seq >= 1 and ev.type == "work_item.claimed"


def test_unknown_type_rejected():
    with db.db_session() as s:
        with pytest.raises(ValueError):
            el.emit(s, type="made.up", scope_path="x", actor_subject="u1")


def test_bad_payload_rejected():
    import jsonschema

    with db.db_session() as s:
        with pytest.raises(jsonschema.ValidationError):
            # interrupt.raised requires reason_code_id (int); send wrong type
            el.emit(
                s,
                type=el.INTERRUPT_RAISED,
                scope_path="site/lineA",
                actor_subject="u1",
                payload={"reason_code_id": "not-an-int"},
            )
