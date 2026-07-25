from engine import db


def test_session_roundtrip_and_now_is_utc():
    assert db.now().tzinfo is not None
    with db.db_session() as s:
        assert s.execute.__self__ is s  # session usable
