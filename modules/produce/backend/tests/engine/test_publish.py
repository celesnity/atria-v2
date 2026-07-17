import pytest

from engine import db
from engine.config import service as cfg
from engine.config.models import PrWorkflow, PrWorkflowVersion
from engine.core import auth, grant, scope

GOOD = {
    "nodes": [
        {"uid": "a", "node_type": "begin", "key": "start", "config": {}},
        {"uid": "b", "node_type": "human", "key": "m", "config": {"output_contract": {"type": "object"}}},
        {"uid": "d", "node_type": "decision", "key": "chk",
         "config": {"condition": {"left": 1, "operator": "<=", "right": 10}}},
        {"uid": "z", "node_type": "end", "key": "done", "config": {}},
    ],
    "edges": [
        {"from": "start", "to": "m", "branch": "default"},
        {"from": "m", "to": "chk", "branch": "default"},
        {"from": "chk", "to": "done", "branch": "pass"},
        {"from": "chk", "to": "done", "branch": "else"},
    ],
}


def _cfg_principal(s, path="site/lineA"):
    sc = scope.create(s, path, kind="line", name=path)
    s.flush()
    s.add(grant.PrGrant(subject="cfg", role="configurator", scope_id=sc.id))
    s.flush()
    return auth.load_principal(s, "cfg")


def test_draft_graph_defaults_to_empty_dict():
    with db.db_session() as s:
        wf = PrWorkflow(key="k", name="n", scope_path="site/lineA")
        s.add(wf)
        s.flush()
        assert wf.draft_graph == {}


def test_publish_freezes_immutable_version():
    with db.db_session() as s:
        p = _cfg_principal(s)
        wf = PrWorkflow(key="k", name="n", scope_path="site/lineA", draft_graph=GOOD)
        s.add(wf)
        s.flush()
        v = cfg.publish(s, p, wf.id, note="v1")
        assert v.status == "published" and v.version == 1 and v.graph == GOOD
        assert wf.current_version_id == v.id and v.note == "v1"


def test_publish_rejects_invalid_graph():
    with db.db_session() as s:
        p = _cfg_principal(s)
        wf = PrWorkflow(key="k", name="n", scope_path="site/lineA",
                        draft_graph={"nodes": [], "edges": []})
        s.add(wf)
        s.flush()
        with pytest.raises(ValueError):
            cfg.publish(s, p, wf.id)
