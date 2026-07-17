from engine import db
from engine.core import scope


def test_prefix_containment():
    assert scope.contains("site/lineA", "site/lineA") is True
    assert scope.contains("site/lineA", "site/lineA/res1") is True
    assert scope.contains("site/lineA", "site/lineB") is False
    assert scope.contains("site/lineA", "site/lineAB") is False  # not a path boundary


def test_create_and_persist():
    with db.db_session() as s:
        row = scope.create(s, "site/lineA/res1", kind="resource", name="Resource 1")
        s.flush()
        assert row.id and row.path == "site/lineA/res1" and row.kind == "resource"
