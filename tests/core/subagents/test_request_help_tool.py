from minder.core.subagents.tools import execute_get_help_responses, execute_request_help


class FakeOrch:
    def start(self, prompt, max_helpers=3):
        assert prompt == "find the parser"
        return "job123"

    def collect(self, request_id, block=True, timeout_ms=30000):
        return {
            "status": "done",
            "responses": [{"responder": "Planner", "content": "x"}],
            "bids": [],
            "digest": "",
        }


def test_execute_request_help():
    out = execute_request_help({"prompt": "find the parser"}, FakeOrch())
    assert out["success"] is True
    assert out["request_id"] == "job123"


def test_execute_get_help_responses():
    out = execute_get_help_responses({"request_id": "job123"}, FakeOrch())
    assert out["success"] is True
    assert out["output"]["responses"][0]["responder"] == "Planner"
