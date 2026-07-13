"""Unit tests for early tool-call notification during SSE streaming."""

import json

from minder.core.agents.components.api.http_client import AgentHttpClient


class _FakeResponse:
    """Minimal stand-in for httpx.Response.iter_lines()."""

    def __init__(self, lines):
        self._lines = lines

    def iter_lines(self):
        yield from self._lines


def _sse(obj) -> str:
    return "data: " + json.dumps(obj)


def _delta_chunk(delta):
    return _sse({"choices": [{"delta": delta, "finish_reason": None}]})


def test_on_tool_call_start_fires_once_with_name_and_id():
    client = AgentHttpClient.__new__(AgentHttpClient)  # no network; call the reader directly
    started = []

    lines = [
        # opening tool_call chunk: id + function name together
        _delta_chunk(
            {"tool_calls": [{"index": 0, "id": "call_abc",
                             "type": "function",
                             "function": {"name": "read_file", "arguments": ""}}]}
        ),
        # argument fragments arrive later — must NOT fire again
        _delta_chunk(
            {"tool_calls": [{"index": 0, "function": {"arguments": "{\"path\":"}}]}
        ),
        _delta_chunk(
            {"tool_calls": [{"index": 0, "function": {"arguments": " \"a.py\"}"}}]}
        ),
        "data: [DONE]",
    ]

    result = client._consume_sse(
        _FakeResponse(lines),
        task_monitor=None,
        on_content_delta=None,
        counter={"emitted": 0},
        on_tool_call_start=lambda name, cid: started.append((name, cid)),
    )

    assert started == [("read_file", "call_abc")]
    msg = result.data["choices"][0]["message"]
    assert msg["tool_calls"][0]["function"]["name"] == "read_file"
    assert msg["tool_calls"][0]["function"]["arguments"] == '{"path": "a.py"}'
