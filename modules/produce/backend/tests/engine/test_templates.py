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

def test_sibling_scope_template_not_visible():
    with db.db_session() as s:
        # Create lineB scope and grant configurator
        sc_b = scope.create(s, "site/lineB", kind="line", name="site/lineB"); s.flush()
        s.add(grant.PrGrant(subject="cfgB", role="configurator", scope_id=sc_b.id)); s.flush()
        p_b = auth.load_principal(s, "cfgB")

        ts.create_template(s, p_b, {"key": "lineB-tmpl", "name": "LineB Template",
            "base_kind": "human", "scope_path": "site/lineB",
            "config": {}}); s.flush()

        # lineA query must NOT see the lineB template
        visible = ts.list_templates(s, "site/lineA")
        assert all(t.scope_path != "site/lineB" for t in visible)
