from atria.core.subagents.tools import execute_get_subagent_output, execute_subagent_fanout


class _Orch:
    def __init__(self):
        self.started = None

    def start(self, tasks):
        self.started = tasks
        return "job123"

    def collect(self, job_id, block=True, timeout_ms=30000):
        return {"status": "done", "tasks": [], "digest": ""}


def test_fanout_requires_tasks():
    out = execute_subagent_fanout({}, _Orch())
    assert out["success"] is False and "tasks" in out["error"]


def test_fanout_starts_job():
    orch = _Orch()
    out = execute_subagent_fanout({"tasks": [{"subagent_type": "solver", "prompt": "p"}]}, orch)
    assert out["success"] is True and out["job_id"] == "job123"
    assert orch.started[0]["prompt"] == "p"


def test_get_output_requires_job_id():
    out = execute_get_subagent_output({}, _Orch())
    assert out["success"] is False


def test_get_output_returns_collect():
    out = execute_get_subagent_output({"job_id": "job123"}, _Orch())
    assert out["success"] is True and out["output"]["status"] == "done"
