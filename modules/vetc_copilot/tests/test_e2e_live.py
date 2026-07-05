import os
from datetime import date
import pytest
from datastore import load_dataset
import autopilot
from config import load_brain_config
from client import BrainClient


@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="needs OPENAI_API_KEY")
def test_live_eval_all_scenarios_grounded():
    ds = load_dataset()  # the real committed data/
    assert ds.eval_scenarios, "materialized eval_scenarios.csv is required"
    client = BrainClient(load_brain_config())
    results = autopilot.run_eval(ds, date(2026, 7, 5), client)
    assert len(results) == len(ds.eval_scenarios)
    # Every 'ask'-routed scenario must be grounded or explicitly abstain.
    for r in results:
        res = r["result"]
        if "citations" in res:
            assert res["citations"] or res["needs_review"]
