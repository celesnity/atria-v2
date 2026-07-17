from engine import db
from engine.config import template_service as ts
from engine.core import auth, grant, scope


def _cfg(s, path="site/lineA"):
    sc = scope.create(s, path, kind="line", name=path); s.flush()
    s.add(grant.PrGrant(subject="cfg", role="configurator", scope_id=sc.id)); s.flush()
    return auth.load_principal(s, "cfg")


def test_create_and_list_template():
    with db.db_session() as s:
        p = _cfg(s)
        t = ts.create_template(s, p, {"key": "torque", "name": "Torque check",
            "base_kind": "human", "scope_path": "site/lineA",
            "config": {"output_contract": {"type": "object"}}})
        s.flush()
        assert t.id
        got = ts.list_templates(s, "site/lineA/res1")   # nested scope sees it
        assert [x.key for x in got] == ["torque"]


def test_delete_hides_template():
    with db.db_session() as s:
        p = _cfg(s)
        t = ts.create_template(s, p, {"key": "k", "name": "n", "base_kind": "human",
            "scope_path": "site/lineA", "config": {}}); s.flush()
        ts.delete_template(s, p, t.id); s.flush()
        assert ts.list_templates(s, "site/lineA") == []
