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
        assert contract.entry_step(graph)["key"] == "prepare"
        assert contract.next_steps(graph, "prepare") == ["measure"]


def test_validate_output_enforces_threshold():
    with db.db_session() as s:
        vid = seed.seed_demo_workflow(s)
        s.flush()
        graph = s.get(models.PrWorkflowVersion, vid).graph
        step = contract.get_step(graph, "measure")
        contract.validate_output(step, {"value": 5.0})  # within [0, 10]
        with pytest.raises(jsonschema.ValidationError):
            contract.validate_output(step, {"value": 99.0})  # over threshold
