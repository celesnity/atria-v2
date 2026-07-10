"""Atria-side client for a module's out-of-process connector service.

Registration is deterministic from the committed manifest; this client is only
touched at *call time*. A dead connector fails closed with a structured card,
never a crash and never freelancing over the corpus.

Contract: docs/connector-contract.md. v2 adds (all backward-compatible):
  * ``card_type`` on tool responses so any module gets its own UI renderer
    (v1 modules broadcast as ``{module}_card``).
  * best-effort identity/secret headers on every call.
  * streaming tool calls over SSE (``/connector/tools/{name}/stream``).
  * manifest reconciliation against the live ``/connector/manifest``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any, Callable, Iterator, Optional

import httpx

logger = logging.getLogger(__name__)

# Connector contract version this core speaks (docs/connector-contract.md). A
# module can declare service.min_core_version; core warns if it needs a newer one.
CORE_CONNECTOR_VERSION = 2


def _needs_newer_core(min_core_version: Optional[str]) -> bool:
    if not min_core_version:
        return False
    try:
        return int(str(min_core_version).split(".")[0]) > CORE_CONNECTOR_VERSION
    except (ValueError, TypeError):
        return False


class ConnectorUnreachable(RuntimeError):
    """The connector service could not be reached over the network."""

    service = "connector"


# Connector-down directive for the model. Generic (not module-specific): tells the
# model the service is down and not to answer from its own knowledge. A module can
# ship a more specific suffix in its own graceful-unavailable response (llm_suffix);
# this is only used when the whole container is unreachable.
UNAVAILABLE_SUFFIX = (
    "\n\n[SYSTEM: The {module} module service is unavailable (connector unreachable). "
    "Tell the user this tool cannot answer right now and that the card above explains "
    "why. Do NOT answer the question from your own knowledge, and do NOT read or grep "
    "the module's data files to work around the outage.]"
)

_UNAVAILABLE_ANSWER = (
    "The {module} service is currently unavailable (connector unreachable), so this "
    "request cannot be completed right now. Please retry once the service is restored."
)


def unavailable_card(query: str, connector_name: str) -> dict:
    """A deps-free, fail-closed card. Generic across modules."""
    return {
        "query": query,
        "answer": _UNAVAILABLE_ANSWER.format(module=connector_name),
        "answer_type": "clarification_needed",
        "exact_quote": "",
        "is_sensitive": False,
        "related_suggestions": [],
        "data_collection_requirement": {"needs_user_input": False, "missing_fields": []},
        "citations": [],
        "confidence": 0.0,
        "confidence_band": "low",
        "review_required": True,
        "advisory_note": "",
        "validation_warnings": [f"connector_unreachable:{connector_name}"],
        "structured": {},
    }


def _module_token(name: str) -> Optional[str]:
    """Per-module shared secret, if configured via env.

    Looked up as ``ATRIA_MODULE_TOKEN_<UPPER_NAME>`` then ``ATRIA_MODULE_TOKEN``.
    Lets a module authenticate that a call really came from Atria core.
    """
    return os.environ.get(f"ATRIA_MODULE_TOKEN_{name.upper()}") or os.environ.get(
        "ATRIA_MODULE_TOKEN"
    )


def _auth_headers(name: str, principal: Optional[dict], session_id: Optional[str] = None) -> dict:
    """Best-effort identity + secret headers for a connector call (v2)."""
    headers: dict[str, str] = {}
    token = _module_token(name)
    if token:
        headers["X-Atria-Module-Token"] = token
    if principal:
        try:
            headers["X-Atria-Principal"] = json.dumps(principal, separators=(",", ":"))
        except (TypeError, ValueError):
            pass
    if session_id:
        headers["X-Atria-Session"] = session_id
    return headers


class RemoteConnector:
    """Thin HTTP client for one module's connector service."""

    def __init__(
        self, name: str, connector_url: str, health_path: str = "/connector/health"
    ) -> None:
        self.name = name
        self.base_url = connector_url.rstrip("/")
        self.health_path = health_path
        self._client = httpx.Client(base_url=self.base_url)

    # -- health / capabilities ------------------------------------------------

    def is_healthy(self, timeout: float = 2.0) -> bool:
        try:
            r = self._client.get(self.health_path, timeout=timeout)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def health(self, timeout: float = 2.0) -> dict:
        """Full health payload: ``{ok, version, capabilities, sidecars}`` or an
        error dict. Never raises — used for the UI status dot."""
        try:
            r = self._client.get(self.health_path, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else {"ok": True}
        except (httpx.HTTPError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    # -- tool calls -----------------------------------------------------------

    def call_tool(
        self, tool: str, arguments: dict, timeout: float = 110.0,
        principal: Optional[dict] = None, session_id: Optional[str] = None
    ) -> dict:
        try:
            r = self._client.post(
                f"/connector/tools/{tool}",
                json={"arguments": arguments},
                headers=_auth_headers(self.name, principal, session_id),
                timeout=timeout,
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            logger.warning("connector %s call_tool(%s) failed: %s", self.name, tool, exc)
            raise ConnectorUnreachable(str(exc)) from exc

    # ponytail: no Atria-side stream client — the ReAct tool loop is sync
    def stream_tool(self, tool: str, arguments: dict,
                    timeout: float = 300.0, principal: Optional[dict] = None,
                    session_id: Optional[str] = None) -> "Iterator[dict]":
        """Yield decoded SSE events from ``/connector/tools/{tool}/stream``.

        The tool handler consumes these synchronously (pumping progress/card
        events to the UI, then returning the ``final``), so the ReAct loop stays
        request/response while the UI sees live progress. Raises
        ``ConnectorUnreachable`` if the stream can't be opened.
        """
        try:
            with self._client.stream("POST", f"/connector/tools/{tool}/stream",
                                     json={"arguments": arguments},
                                     headers={**_auth_headers(self.name, principal, session_id),
                                              "Accept": "text/event-stream"},
                                     timeout=timeout) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].strip()
                    if not payload:
                        continue
                    try:
                        yield json.loads(payload)
                    except ValueError:
                        logger.debug("connector %s stream: bad event %r", self.name, payload)
        except httpx.HTTPError as exc:
            logger.warning("connector %s stream_tool(%s) failed: %s", self.name, tool, exc)
            raise ConnectorUnreachable(str(exc)) from exc

    # -- generic passthrough (used by the core proxy route) -------------------

    def get_json(self, path: str, timeout: float = 5.0, principal: Optional[dict] = None) -> dict:
        try:
            r = self._client.get(path, headers=_auth_headers(self.name, principal), timeout=timeout)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            logger.warning("connector %s GET %s failed: %s", self.name, path, exc)
            raise ConnectorUnreachable(str(exc)) from exc

    def post_json(
        self, path: str, payload: dict, timeout: float = 15.0, principal: Optional[dict] = None
    ) -> dict:
        try:
            r = self._client.post(
                path, json=payload, headers=_auth_headers(self.name, principal), timeout=timeout
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            logger.warning("connector %s POST %s failed: %s", self.name, path, exc)
            raise ConnectorUnreachable(str(exc)) from exc

    # -- manifest reconciliation ---------------------------------------------

    def fetch_manifest(self, timeout: float = 3.0) -> Optional[dict]:
        """Fetch the live ``/connector/manifest`` (authoritative tool specs), or
        None if the service is down / doesn't expose it."""
        try:
            r = self._client.get("/connector/manifest", timeout=timeout)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else None
        except (httpx.HTTPError, ValueError):
            return None


if TYPE_CHECKING:  # avoid import cycles / heavy imports at module load
    from atria.core.modules.store import Module
    from atria.core.skill_tools import SkillToolContext, ToolSpec


def _card_type(resp: dict, module_name: str) -> str:
    """Pick the UI renderer key: explicit ``card_type`` else ``{module}_card``."""
    ct = resp.get("card_type")
    return ct if isinstance(ct, str) and ct.strip() else f"{module_name}_card"


def _broadcast_card(ctx: "SkillToolContext", card_type: str, card: dict) -> None:
    if not (card and ctx.broadcaster):
        return
    try:
        ctx.broadcaster({"type": card_type, **card})
    except Exception as exc:  # noqa: BLE001
        ctx.logger.warning("card broadcast failed: %s", exc)


def _broadcast_progress(ctx: "SkillToolContext", module: str, evt: dict) -> None:
    """Push a streaming progress/partial event to the UI (live, mid-tool-call)."""
    if not ctx.broadcaster:
        return
    try:
        ctx.broadcaster({"type": "module_progress", "module": module,
                         "message": evt.get("message", ""), "pct": evt.get("pct"),
                         "output": evt.get("output")})
    except Exception as exc:  # noqa: BLE001
        ctx.logger.warning("progress broadcast failed: %s", exc)


def _emit_response(ctx: "SkillToolContext", conn: "RemoteConnector", resp: dict) -> dict:
    """Broadcast a response's card + blocks and shape the agent-facing result."""
    _broadcast_card(ctx, _card_type(resp, conn.name), resp.get("card"))
    for block in resp.get("blocks") or []:
        if ctx.push_block and block.get("remote_entry"):
            try:
                ctx.push_block(block, conn.name)
            except Exception as exc:  # noqa: BLE001 — a block push must never fail the tool
                ctx.logger.warning("block push failed for %s: %s", conn.name, exc)
    out: dict = {"success": bool(resp.get("success", True)), "output": resp.get("output")}
    if resp.get("llm_suffix"):
        out["_llm_suffix"] = resp["llm_suffix"]
    return out


def _unavailable_result(ctx: "SkillToolContext", conn: "RemoteConnector", query: str) -> dict:
    card = unavailable_card(query, conn.name)
    _broadcast_card(ctx, f"{conn.name}_card", card)
    return {"success": True, "output": card,
            "_llm_suffix": UNAVAILABLE_SUFFIX.format(module=conn.name)}


def _run_stream(ctx: "SkillToolContext", conn: "RemoteConnector",
                tool_name: str, kwargs: dict, query: str) -> dict:
    """Consume the tool's SSE stream: pump progress/card events to the UI live,
    then return the ``final`` result to the agent. Falls back to the non-stream
    endpoint if the connector doesn't actually stream."""
    final: Optional[dict] = None
    try:
        for evt in conn.stream_tool(tool_name, kwargs,
                                    principal=ctx.principal, session_id=ctx.session_id):
            etype = evt.get("event")
            if etype == "card":
                _broadcast_card(ctx, _card_type(evt, conn.name), evt.get("card") or {})
            elif etype in ("progress", "partial"):
                _broadcast_progress(ctx, conn.name, evt)
            elif etype == "block":
                blk = evt.get("block") or {}
                if ctx.push_block and blk.get("remote_entry"):
                    try:
                        ctx.push_block(blk, conn.name)
                    except Exception as exc:  # noqa: BLE001 — a block push must never break the stream
                        ctx.logger.warning("stream block push failed for %s: %s", conn.name, exc)
            elif etype == "final":
                final = evt
            elif etype == "error":
                final = {"success": False, "output": evt.get("message", "stream error")}
    except ConnectorUnreachable:
        return _unavailable_result(ctx, conn, query)
    if final is None:
        return {"success": False, "output": "tool stream ended without a final event"}
    return _emit_response(ctx, conn, final)


def _make_handler(
    ctx: "SkillToolContext", conn: "RemoteConnector", tool_name: str, streaming: bool = False
) -> Callable[..., dict]:
    def handler(**kwargs: Any) -> dict:
        query = str(kwargs.get("query") or kwargs.get("text") or "")
        # Identity (username/email via ctx.principal + session via ctx.session_id)
        # is forwarded first-party from the session context on every call.
        if streaming:
            return _run_stream(ctx, conn, tool_name, kwargs, query)
        try:
            resp = conn.call_tool(tool_name, kwargs,
                                  principal=ctx.principal, session_id=ctx.session_id)
        except ConnectorUnreachable:
            return _unavailable_result(ctx, conn, query)
        return _emit_response(ctx, conn, resp)

    return handler


def reconcile_manifest(module: "Module", conn: "RemoteConnector") -> None:
    """Warn if the committed manifest's tool specs drift from the live service.

    Non-fatal, best-effort — the committed manifest remains authoritative for
    registration; this only surfaces skew in logs so it gets fixed.
    """
    live = conn.fetch_manifest()
    if not live:
        return
    svc = getattr(module.manifest, "service", None) if module.manifest else None
    committed = {t.get("name") for t in (svc.tools if svc else []) if t.get("name")}
    live_tools = {
        t.get("name") for t in live.get("tools", []) if isinstance(t, dict) and t.get("name")
    }
    missing = committed - live_tools
    extra = live_tools - committed
    if missing:
        logger.warning(
            "connector %s: manifest declares tools the service lacks: %s",
            module.name,
            sorted(missing),
        )
    if extra:
        logger.warning(
            "connector %s: service exposes tools not in manifest: %s", module.name, sorted(extra)
        )


def build_remote_tool_specs(ctx: "SkillToolContext", _modules: "list[Module]") -> "list[ToolSpec]":
    """Build proxy ToolSpecs for every READY service-module connector, from its
    live ``/connector/manifest`` tool schemas (not the committed manifest).
    The ``_modules`` param is accepted for API compatibility but unused; tools
    come from the connector registry."""
    from atria.core.skill_tools import ToolSpec  # local import: avoid cycle at module load
    from atria.core.modules.registry import get_registry, ConnectorState

    reg = get_registry()
    specs: list[ToolSpec] = []
    for rec in reg.connector_records():
        if rec.state is not ConnectorState.READY:
            continue
        conn = RemoteConnector(rec.name, rec.connector_url)
        for tool in rec.tools:
            name = tool.get("name")
            if not name:
                continue
            specs.append(
                ToolSpec(
                    name=name,
                    description=tool.get("description", ""),
                    parameters=tool.get("parameters", {"type": "object", "properties": {}}),
                    handler=_make_handler(ctx, conn, name, bool(tool.get("streaming"))),
                )
            )
    return specs
