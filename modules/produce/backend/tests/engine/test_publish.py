from engine import db
from engine.config.models import PrWorkflow


def test_draft_graph_defaults_to_empty_dict():
    with db.db_session() as s:
        wf = PrWorkflow(key="k", name="n", scope_path="site/lineA")
        s.add(wf)
        s.flush()
        assert wf.draft_graph == {}
