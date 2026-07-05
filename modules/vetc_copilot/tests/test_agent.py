from datetime import date

from datastore import Dataset
from agent import run_agent, parse_tool_call


def _ds() -> Dataset:
    return Dataset(
        users=[{"user_id": "U001", "primary_vehicle_id": "VEH001"}],
        vehicles=[
            {
                "vehicle_id": "VEH001",
                "user_id": "U001",
                "vehicle_type": "Car",
                "fuel_type": "Gasoline",
                "vehicle_age_years": "8",
                "roadside_assistance_status": "Inactive",
                "inspection_expiry": "2026-07-20",
                "civil_liability_expiry": "2026-08-15",
                "registration_expiry": "2029-01-10",
            }
        ],
        documents=[],
        services=[{"service_id": "SVC001", "service_name": "Civil Liability Insurance Renewal"}],
        knowledge=[
            {
                "knowledge_id": "K001",
                "question": "đăng kiểm",
                "answer": "Theo tuổi xe.",
                "topic": "Đăng kiểm",
            }
        ],
    )


class ScriptedClient:
    """Brain client that replays a fixed list of chat responses (no network)."""

    available = True

    def __init__(self, replies):
        self._replies = list(replies)

    def chat(self, messages, **kw):
        return self._replies.pop(0)


def test_parse_tool_call_variants():
    assert (
        parse_tool_call('{"tool":"recommend_services","args":{}}')["tool"] == "recommend_services"
    )
    assert (
        parse_tool_call('```json\n{"tool":"get_deadlines","args":{}}\n```')["tool"]
        == "get_deadlines"
    )
    assert parse_tool_call("Chào bạn, xe của bạn vẫn ổn.") is None


def test_parse_tool_call_ignores_trailing_prose_and_nested_braces():
    # Weak models emit the tool JSON then extra prose; nested {} in args must not break parsing.
    raw = '{"tool": "get_deadlines", "args": {}}Xin chào, đây là câu trả lời thừa.'
    call = parse_tool_call(raw)
    assert call["tool"] == "get_deadlines"
    assert call["args"] == {}
    raw2 = '{"tool": "renew_service", "args": {"vehicle_id": "VEH001", "service_id": "SVC001"}} ok'
    assert parse_tool_call(raw2)["args"]["vehicle_id"] == "VEH001"


def test_agent_calls_tool_then_answers():
    client = ScriptedClient(
        ['{"tool": "get_deadlines", "args": {}}', "Xe của bạn sắp hết hạn đăng kiểm trong 15 ngày."]
    )
    out = run_agent(
        _ds(),
        "U001",
        [{"role": "user", "content": "Xe tôi có hạn gì sắp tới?"}],
        date(2026, 7, 5),
        client,
    )
    assert out["steps"][0]["tool"] == "get_deadlines"
    assert out["steps"][0]["result"]["vehicles"]  # real radar data flowed through
    assert "đăng kiểm" in out["reply"].lower()


def test_agent_renew_tool_executes_hands():
    client = ScriptedClient(
        [
            '{"tool": "renew_service", "args": {"vehicle_id": "VEH001", "service_id": "SVC001"}}',
            "Đã gia hạn bảo hiểm cho bạn.",
        ]
    )
    out = run_agent(
        _ds(),
        "U001",
        [{"role": "user", "content": "Đồng ý, gia hạn giúp tôi"}],
        date(2026, 7, 5),
        client,
    )
    step = out["steps"][0]
    assert step["tool"] == "renew_service"
    assert step["result"]["ok"] is True
    assert step["result"]["policy_id"].startswith("POL-")


def test_agent_without_client_returns_notice():
    out = run_agent(
        _ds(), "U001", [{"role": "user", "content": "chào"}], date(2026, 7, 5), client=None
    )
    assert out["steps"] == []
    assert "LLM" in out["reply"]


class _BoomClient:
    available = True

    def chat(self, messages, **kw):
        raise RuntimeError("429 rate limited")


def test_agent_survives_llm_error(monkeypatch):
    import agent as agent_mod

    monkeypatch.setattr(agent_mod.time, "sleep", lambda *a, **k: None)
    out = run_agent(
        _ds(), "U001", [{"role": "user", "content": "chào"}], date(2026, 7, 5), _BoomClient()
    )
    assert out["steps"] == []
    assert "thử lại" in out["reply"].lower() or "bận" in out["reply"].lower()


class _FlakyClient:
    """Returns a tool call first, then fails on the phrasing call."""

    available = True

    def __init__(self):
        self.n = 0

    def chat(self, messages, **kw):
        self.n += 1
        if self.n == 1:
            return '{"tool": "get_deadlines", "args": {}}'
        raise RuntimeError("429 rate limited")


def test_agent_degrades_to_tool_summary_when_final_call_fails(monkeypatch):
    import agent as agent_mod

    monkeypatch.setattr(agent_mod.time, "sleep", lambda *a, **k: None)
    out = run_agent(
        _ds(),
        "U001",
        [{"role": "user", "content": "hạn gì sắp tới"}],
        date(2026, 7, 5),
        _FlakyClient(),
    )
    assert out["steps"][0]["tool"] == "get_deadlines"
    assert "ngày" in out["reply"]  # deterministic summary from the gathered radar data
