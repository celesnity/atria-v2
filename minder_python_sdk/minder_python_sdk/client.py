"""MinderClient — a module's proactive channel back into Minder (reverse-push).

Never imports ``minder``; httpx + env only. Use it to push/update/remove a
federated chat block into a live session outside a tool call (e.g. an async job
reporting progress). Requires the Keycloak realm role ``module-push``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from .announce import AnnounceConfig, _auth_headers
from .envelope import EventEnvelope, make_envelope

logger = logging.getLogger("minder_python_sdk.client")


class MinderClientError(RuntimeError):
    """A reverse-push call to Minder failed."""


class MinderClient:
    def __init__(self, module: str, cfg: AnnounceConfig) -> None:
        self.module = module
        self.cfg = cfg

    def _post(self, path: str, payload: dict) -> httpx.Response:
        url = f"{self.cfg.minder_url}{path}"
        try:
            resp = httpx.post(url, json=payload, headers=_auth_headers(self.cfg), timeout=15)
            resp.raise_for_status()
            return resp
        except httpx.HTTPError as exc:
            logger.warning("minder client %s failed: %s", path, exc)
            raise MinderClientError(str(exc)) from exc

    def push_block(
        self,
        session_id: str,
        component: str,
        props: Optional[dict] = None,
        *,
        remote_entry: Optional[str] = None,
        height: Any = "auto",
        title: Optional[str] = None,
        block_id: Optional[str] = None,
    ) -> str:
        entry = remote_entry or self.cfg.remote_entry or ""
        api_base = entry.split("/dashboard/")[0] if "/dashboard/" in entry else None
        payload = {
            "session_id": session_id,
            "module": self.module,
            "remote_name": self.module,
            "remote_entry": entry,
            "component": component,
            "props": props or {},
            "block_id": block_id,
            "api_base": api_base,
            "height": height,
            "title": title,
            "persist": True,
        }
        return self._post("/api/blocks/remote/push", payload).json()["block_id"]

    def update_block(self, session_id: str, block_id: str, props: dict) -> None:
        self._post(
            "/api/blocks/remote/update",
            {"session_id": session_id, "block_id": block_id, "props": props},
        )

    def remove_block(self, session_id: str, block_id: str) -> None:
        self._post("/api/blocks/remote/remove", {"session_id": session_id, "block_id": block_id})

    def emit_event(
        self,
        event: "EventEnvelope | str",
        payload: Optional[dict] = None,
        *,
        session_id: Optional[str] = None,
        actor: Optional[dict] = None,
        source: str = "module",
    ) -> str:
        """Write an event envelope to Minder's event log so the Operational Graph
        records it as ground truth. Accepts a prebuilt :class:`EventEnvelope` or a
        (type, payload) pair. Returns the stored event id."""
        env = (
            event
            if isinstance(event, EventEnvelope)
            else make_envelope(
                self.module,
                event,
                payload,
                source=source,
                actor=actor,
                session_id=session_id,
            )
        )
        self._post("/api/events", env.to_dict())
        return env.event_id

    def push_ui_intent(
        self, session_id: str, intent: dict, *, actor: Optional[dict] = None
    ) -> None:
        """Send a UI intent (navigate/fill/focus/…) to a session's frontend via
        Minder core, which forwards it to the module dashboard mounted in that
        session — the reverse-push path for driving the real UI."""
        self._post(
            "/api/ui/intent",
            {"session_id": session_id, "module": self.module, "intent": intent, "actor": actor},
        )

    def query_graph(
        self,
        query: Optional[str] = None,
        *,
        node: Optional[str] = None,
        depth: int = 1,
        limit: int = 50,
    ) -> dict:
        """Query Minder's Operational Graph for linked context (neighbors of a
        node, or a free-text lookup) so the agent reasons on connected data rather
        than a single row. Returns the host's graph response payload."""
        payload = {"query": query, "node": node, "depth": depth, "limit": limit}
        return self._post("/api/graph/query", payload).json()

    def get_context(self, session_id: str) -> dict:
        """Fetch the agent's current context for a session (autonomy level, scope)
        from the host."""
        return self._post("/api/agent/context", {"session_id": session_id}).json()

    def push_artifact(self, session_id: str, filename: str, content: bytes) -> int:
        import base64

        payload = {
            "session_id": session_id,
            "filename": filename,
            "content_b64": base64.b64encode(content).decode(),
        }
        return self._post("/api/artifacts/remote/push", payload).json()["artifact_id"]
