"""Session-scoped direct browser bridge for UI SDK tools (no MCP/relay)."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import urllib.request
import uuid
from typing import Any, Callable


class DirectUiSdkBridge:
    """Broker browser UI descriptors and correlated action results for an agent turn."""

    def __init__(self, emit: Callable[[dict[str, Any]], None]) -> None:
        self._emit = emit
        self._registries: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self._pending: dict[str, tuple[threading.Event, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def register(self, *, session_id: str, module: str, descriptors: list[dict[str, Any]]) -> None:
        safe = [d for d in descriptors if isinstance(d, dict) and isinstance(d.get("name"), str)]
        with self._lock:
            self._registries.setdefault(session_id, {})[module] = safe

    def describe(self, session_id: str) -> dict[str, list[dict[str, Any]]]:
        with self._lock:
            return {module: [dict(d) for d in descriptors] for module, descriptors in self._registries.get(session_id, {}).items()}

    def invoke(
        self, session_id: str, module: str, action: str, args: dict[str, Any], timeout: float = 120.0
    ) -> dict[str, Any]:
        """Invoke a browser action, allowing a human approval gate to resolve."""
        if timeout < 1.0:
            raise ValueError("timeout must be at least one second")
        if module == "module_template" and action in {"approve_escalation", "reject_escalation"}:
            gate_result = self._invoke_embinder_gate(session_id, action, args, timeout)
            if not gate_result["success"]:
                return gate_result
            ui_result = self._invoke_browser(session_id, module, action, args, timeout)
            if not ui_result["success"]:
                return ui_result
            return {"success": True, "output": {"gate": gate_result["output"], "ui": ui_result["output"]}}
        return self._invoke_browser(session_id, module, action, args, timeout)

    def _invoke_browser(
        self, session_id: str, module: str, action: str, args: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        """Invoke a registered browser descriptor and wait for its correlated result."""
        with self._lock:
            descriptors = self._registries.get(session_id, {}).get(module)
            allowed = action == "__describe__" or any(d.get("name") == action for d in descriptors or [])
        if not descriptors or not allowed:
            return {"success": False, "error": "ui_action_not_registered", "output": None}

        request_id = uuid.uuid4().hex
        event = threading.Event()
        holder: dict[str, Any] = {}
        with self._lock:
            self._pending[request_id] = (event, holder)
        try:
            self._emit(
                {
                    "type": "ui_sdk_invoke",
                    "data": {
                        "request_id": request_id,
                        "session_id": session_id,
                        "module": module,
                        "action": action,
                        "args": args,
                    },
                }
            )
            if not event.wait(timeout):
                return {"success": False, "error": "ui_action_timeout", "output": None}
            if holder.get("success"):
                return {"success": True, "output": holder.get("output")}
            return {"success": False, "error": holder.get("error", "ui_action_failed"), "output": None}
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    @staticmethod
    def _invoke_embinder_gate(
        session_id: str, action: str, args: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        """Route destructive Module Template actions through Embinder's no-MCP gate."""
        url = os.getenv(
            "MODULE_TEMPLATE_EMBINDER_DIRECT_URL",
            "http://module-template-embinder-relay:7331/internal/direct-call",
        )
        token = os.getenv("MODULE_TEMPLATE_EMBINDER_DIRECT_TOKEN", "module-template-direct")
        request = urllib.request.Request(
            url,
            data=json.dumps({"name": action, "args": args, "session": session_id}).encode(),
            headers={"Content-Type": "application/json", "x-embinder-direct-token": token},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return {"success": True, "output": json.loads(response.read())}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": f"embinder_gate_failed: {exc}", "output": None}

    def resolve(self, request_id: str, payload: dict[str, Any]) -> bool:
        with self._lock:
            pending = self._pending.get(request_id)
        if pending is None:
            return False
        event, holder = pending
        holder.update({"success": True, "output": payload})
        event.set()
        return True

    def reject(self, request_id: str, error: str) -> bool:
        with self._lock:
            pending = self._pending.get(request_id)
        if pending is None:
            return False
        event, holder = pending
        holder.update({"success": False, "error": error})
        event.set()
        return True


_bridge: DirectUiSdkBridge | None = None


def get_ui_sdk_bridge() -> DirectUiSdkBridge:
    """Return the process bridge, scheduling browser broadcasts on the web loop."""
    global _bridge
    if _bridge is None:
        def emit(message: dict[str, Any]) -> None:
            from minder.web.state import get_state

            state = get_state()
            if state.ws_manager is None or state._event_loop is None:
                raise RuntimeError("browser UI bridge is unavailable")
            future = asyncio.run_coroutine_threadsafe(state.ws_manager.broadcast(message), state._event_loop)
            future.result(timeout=2)

        _bridge = DirectUiSdkBridge(emit)
    return _bridge
