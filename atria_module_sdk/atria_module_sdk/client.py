"""AtriaClient — a module's proactive channel back into Atria (reverse-push).

Never imports ``atria``; httpx + env only. Use it to push/update/remove a
federated chat block into a live session outside a tool call (e.g. an async job
reporting progress). Requires the Keycloak realm role ``module-push``.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from .announce import AnnounceConfig, _auth_headers

logger = logging.getLogger("atria_module_sdk.client")


class AtriaClientError(RuntimeError):
    """A reverse-push call to Atria failed."""


class AtriaClient:
    def __init__(self, module: str, cfg: AnnounceConfig) -> None:
        self.module = module
        self.cfg = cfg

    def _post(self, path: str, payload: dict) -> httpx.Response:
        url = f"{self.cfg.atria_url}{path}"
        try:
            resp = httpx.post(url, json=payload, headers=_auth_headers(self.cfg), timeout=15)
            resp.raise_for_status()
            return resp
        except httpx.HTTPError as exc:
            logger.warning("atria client %s failed: %s", path, exc)
            raise AtriaClientError(str(exc)) from exc

    def push_block(self, session_id: str, component: str, props: Optional[dict] = None, *,
                   remote_entry: Optional[str] = None, height: Any = "auto",
                   title: Optional[str] = None, block_id: Optional[str] = None) -> str:
        entry = remote_entry or self.cfg.remote_entry or ""
        api_base = entry.split("/dashboard/")[0] if "/dashboard/" in entry else None
        payload = {"session_id": session_id, "module": self.module,
                   "remote_name": self.module, "remote_entry": entry,
                   "component": component, "props": props or {}, "block_id": block_id,
                   "api_base": api_base, "height": height, "title": title, "persist": True}
        return self._post("/api/blocks/remote/push", payload).json()["block_id"]

    def update_block(self, session_id: str, block_id: str, props: dict) -> None:
        self._post("/api/blocks/remote/update",
                   {"session_id": session_id, "block_id": block_id, "props": props})

    def remove_block(self, session_id: str, block_id: str) -> None:
        self._post("/api/blocks/remote/remove",
                   {"session_id": session_id, "block_id": block_id})

    def push_artifact(self, session_id: str, filename: str, content: bytes,
                      type: str = "report") -> int:
        import base64
        payload = {"session_id": session_id, "filename": filename,
                   "content_b64": base64.b64encode(content).decode(), "type": type}
        return self._post("/api/artifacts/remote/push", payload).json()["artifact_id"]
