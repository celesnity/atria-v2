"""seal_unanswered_tool_calls — guards against orphaned tool_call_ids that would
otherwise 400 the next OpenAI request and brick the session."""
from __future__ import annotations

from atria.core.agents.main_agent.run_loop import seal_unanswered_tool_calls


def _tc(cid: str, name: str) -> dict:
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": "{}"}}


def test_seals_unanswered_tool_call():
    tool_calls = [_tc("call_a", "request_help"), _tc("call_b", "task_complete")]
    # Only call_a got a result (e.g. task_complete was rejected via a continue).
    messages = [
        {"role": "assistant", "tool_calls": tool_calls},
        {"role": "tool", "tool_call_id": "call_a", "content": "posted"},
        {"role": "user", "content": "you must finish your todos first"},
    ]

    sealed = seal_unanswered_tool_calls(messages, tool_calls)

    assert sealed == 1
    answered = {m["tool_call_id"] for m in messages if m.get("role") == "tool"}
    # Every declared tool_call now has a matching tool result.
    assert answered == {"call_a", "call_b"}
    synthetic = [m for m in messages if m.get("tool_call_id") == "call_b"][0]
    assert "no result recorded for task_complete" in synthetic["content"]


def test_noop_when_all_answered():
    tool_calls = [_tc("call_a", "read_file")]
    messages = [
        {"role": "assistant", "tool_calls": tool_calls},
        {"role": "tool", "tool_call_id": "call_a", "content": "ok"},
    ]

    sealed = seal_unanswered_tool_calls(messages, tool_calls)

    assert sealed == 0
    assert sum(1 for m in messages if m.get("role") == "tool") == 1


def test_ignores_prior_turn_tool_results():
    # A tool result from an earlier turn must not count as answering this turn.
    tool_calls = [_tc("call_new", "template_start_job")]
    messages = [
        {"role": "tool", "tool_call_id": "call_old", "content": "old"},
        {"role": "assistant", "tool_calls": tool_calls},
    ]

    sealed = seal_unanswered_tool_calls(messages, tool_calls)

    assert sealed == 1
    assert any(m.get("tool_call_id") == "call_new" for m in messages)
