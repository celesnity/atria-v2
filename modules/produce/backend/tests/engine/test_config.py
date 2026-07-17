import jsonschema
import pytest

from engine import db
from engine.config import contract, models, seed


def test_seed_creates_published_version_with_dag():
    with db.db_session() as s:
        vid = seed.seed_demo_workflow(s)
        s.flush()
        v = s.get(models.PrWorkflowVersion, vid)
        assert v.status == "published"
        graph = v.graph
        # "prepare" is the entry step (no AND-join predecessors) and flows to "measure"
        assert contract.predecessors(graph, "prepare") == []
        assert contract.next_default(graph, "prepare") == "measure"


def test_validate_output_enforces_threshold():
    with db.db_session() as s:
        vid = seed.seed_demo_workflow(s)
        s.flush()
        graph = s.get(models.PrWorkflowVersion, vid).graph
        node = contract.node_by_key(graph, "measure")
        contract.validate_output(node, {"value": 5.0})  # within [0, 10]
        with pytest.raises(jsonschema.ValidationError):
            contract.validate_output(node, {"value": 99.0})  # over threshold
