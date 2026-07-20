"""Direct (non-MCP) UI SDK bridge contracts."""

import threading
import json

from minder.web.ui_sdk_bridge import DirectUiSdkBridge
from minder.core.agents.components.schemas.builtin import BUILTIN_TOOL_SCHEMAS


def test_bridge_describes_registered_module_and_resolves_ui_result() -> None:
    sent: list[dict] = []
    bridge = DirectUiSdkBridge(lambda message: sent.append(message))
    bridge.register(
        session_id="s1",
        module="module_template",
        descriptors=[{"name": "runtime", "kind": "read", "description": "Runtime state"}],
    )

    assert bridge.describe("s1") == {"module_template": [{"name": "runtime", "kind": "read", "description": "Runtime state"}]}

    result: dict = {}
    worker = threading.Thread(
        target=lambda: result.update(bridge.invoke("s1", "module_template", "__describe__", {})),
    )
    worker.start()
    while not sent:
        pass
    request_id = sent[0]["data"]["request_id"]
    assert bridge.resolve(request_id, {"runtime": {"mode": "ui-only"}}) is True
    worker.join(timeout=1)

    assert result == {"success": True, "output": {"runtime": {"mode": "ui-only"}}}


def test_direct_ui_tools_are_available_to_the_agent_schema() -> None:
    names = {schema["function"]["name"] for schema in BUILTIN_TOOL_SCHEMAS}

    assert {"ui_describe", "ui_act"}.issubset(names)


def test_final_decision_passes_gate_then_updates_browser(monkeypatch) -> None:
    sent: list[dict] = []
    bridge = DirectUiSdkBridge(lambda message: sent.append(message))
    bridge.register(
        session_id="s1",
        module="module_template",
        descriptors=[{"name": "approve_escalation", "kind": "action", "description": "Approve"}],
    )

    class Response:
        def read(self) -> bytes:
            return json.dumps({"approved": True}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    result: dict = {}
    worker = threading.Thread(target=lambda: result.update(bridge.invoke("s1", "module_template", "approve_escalation", {})))
    worker.start()
    while not sent:
        pass
    assert sent[0]["data"]["action"] == "approve_escalation"
    bridge.resolve(sent[0]["data"]["request_id"], {"status": "approved"})
    worker.join(timeout=1)

    assert result == {"success": True, "output": {"gate": {"approved": True}, "ui": {"status": "approved"}}}
