"""Connector — turn a handful of Python functions into an Minder service-module.

The SDK generates the whole connector HTTP contract (docs/connector-contract.md)
from decorated handlers, so the service and the module's ``manifest.json`` can't
drift, and fail-closed behavior is built in. It never imports ``minder`` — the
service runs in its own slim container.

    from minder_python_sdk import Connector, ServiceUnavailable, card

    conn = Connector("my_module", version="1")

    @conn.tool(
        "my_module_query",
        description="Answer a question with grounded RAG.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        card_type="my_module_answer",
    )
    def query(query: str, **kwargs):
        result = run_pipeline(query)          # your logic
        return {"output": result, "card": card(result["answer"])}

    app = conn.asgi()                          # FastAPI app, ready for uvicorn

Handlers return either a plain value (becomes ``output``) or a dict with any of
``output`` / ``card`` / ``card_type`` / ``llm_suffix`` / ``success``. Raise
``ServiceUnavailable("qdrant")`` when a sidecar is down — the SDK converts it to
a fail-closed card + LLM suffix instead of a 500.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Iterator, Optional

if TYPE_CHECKING:
    from .client import MinderClient

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .cards import decision_packet, unavailable_card, unavailable_suffix
from .context import Note, _ContextRegistrar, _StateProvider, build_state_entries
from .envelope import (
    EventEnvelope,
    ToolError,
    actor_from,
    autonomy_allows,
    make_envelope,
    normalize_risk,
)
from .ui import Control, Form, Page, UiSurface, is_intent, navigate

logger = logging.getLogger("minder_python_sdk")

# v3 is a superset of v2: risk/autonomy gating, dry-run, idempotency, declared
# events, and auto-emitted envelopes are all optional. A v1/v2 module upgrades
# with zero code changes and a v2 Minder core (which sends no autonomy header)
# keeps every tool ungated.
CONTRACT_VERSION = "3"

# Caller autonomy when Minder core sends no ``X-Minder-Autonomy`` header — kept
# permissive so a pre-v3 core doesn't accidentally gate every action. Override
# per-connector or via ``MINDER_DEFAULT_AUTONOMY`` to fail-closed.
DEFAULT_AUTONOMY = "high"


class ServiceUnavailable(RuntimeError):
    """Raise from a handler when a downstream sidecar (LLM, vector DB, …) is down."""

    def __init__(self, service: str) -> None:
        super().__init__(f"service unavailable: {service}")
        self.service = service


@dataclass
class _Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., Any]
    card_type: Optional[str]
    streaming: bool
    requires_auth: bool = False
    params_model: Optional[type] = None
    risk: str = "low"
    reversible: Optional[bool] = None
    undo: Optional[str] = None
    idempotent: bool = False
    read_only: bool = False
    when_to_use: str = ""
    examples: list = field(default_factory=list)


@dataclass
class _Event:
    """A declared event type a module emits, advertised in the manifest so an
    agent knows what to subscribe to without scraping."""

    type: str
    description: str
    schema: dict


@dataclass
class Principal:
    """The acting Minder user, forwarded on each call (may be anonymous).

    Beyond identity, carries the user's ``roles`` and ``scopes`` so a handler can
    refuse to act beyond the user's authority instead of only knowing "is this
    someone logged in".
    """

    username: str = "unknown"
    email: str = ""
    roles: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)

    @property
    def is_authenticated(self) -> bool:
        return self.username not in ("", "unknown")

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


class Connector:
    """Builds an Minder service-module's connector app from decorated handlers."""

    def __init__(
        self,
        name: str,
        *,
        version: str = "1",
        display_name: Optional[str] = None,
        public_base_env: str = "MODULE_PUBLIC_BASE",
        dashboard_dist_env: str = "MODULE_DASHBOARD_DIST",
        min_core_version: Optional[str] = None,
        default_autonomy: Optional[str] = None,
    ) -> None:
        self.name = name
        self.version = version
        self.display_name = display_name or name.replace("_", " ").title()
        self.min_core_version = min_core_version
        self.default_autonomy = (
            default_autonomy or os.environ.get("MINDER_DEFAULT_AUTONOMY") or DEFAULT_AUTONOMY
        )
        self._tools: dict[str, _Tool] = {}
        self._events: dict[str, _Event] = {}
        self._health_probes: list[Callable[[], dict]] = []
        self._readiness_probes: list[Callable[[], Any]] = []
        self._extra_routes: list[tuple[str, list[str], Callable]] = []
        self._startup_hooks: list[Callable[[], None]] = []
        self._public_base_env = public_base_env
        self._dashboard_dist_env = dashboard_dist_env
        self._exposed_blocks: list[str] = []
        # Local event subscribers + an optional sink (e.g. MinderClient.emit_event)
        # that ships every emitted envelope to Minder's event log.
        self._event_listeners: list[Callable[[EventEnvelope], None]] = []
        self._event_sink: Optional[Callable[[EventEnvelope], None]] = None
        # Idempotency cache: (tool, request_key) -> response envelope. Bounded so a
        # long-lived connector can't leak memory on unique keys.
        self._idem_cache: "dict[tuple[str, str], dict]" = {}
        self._idem_cap = 1024
        self._decision_handler: Optional[Callable[..., Any]] = None
        # Optional Operational-Graph provider: answers a linked-context query
        # (node + depth) with {nodes, edges} so the agent reasons over connected
        # context instead of a single isolated read.
        self._graph_provider: Optional[Callable[..., Any]] = None
        # Declared UI surface (pages/forms/controls) + a per-session intent bus
        # the module frontend drains over SSE.
        self._ui = UiSurface()
        self._ui_bus: "dict[str, list[Any]]" = {}
        # Per-session declarative UI snapshot cache (page/data/actions) the agent
        # reads via /connector/context to see what's currently on screen.
        self._ui_snapshots: dict[str, dict] = {}
        # Declarative agent-facing context: live state providers + static
        # knowledge/notes, surfaced via /connector/context and the manifest.
        self._ctx_state: dict[str, _StateProvider] = {}
        self._ctx_knowledge: list[str] = []
        self._ctx_notes: list[Note] = []
        self.context = _ContextRegistrar(self)

    def expose_block(self, component_key: str) -> None:
        """Declare an extra Module-Federation exposed component (a chat block),
        so the manifest advertises it alongside ./Dashboard."""
        if component_key not in self._exposed_blocks:
            self._exposed_blocks.append(component_key)

    # -- registration ---------------------------------------------------------

    def tool(
        self,
        name: str,
        *,
        description: str = "",
        parameters: Optional[dict] = None,
        card_type: Optional[str] = None,
        streaming: bool = False,
        requires_auth: bool = False,
        params_model: Optional[type] = None,
        risk: str = "low",
        reversible: Optional[bool] = None,
        undo: Optional[str] = None,
        idempotent: bool = False,
        read_only: bool = False,
        when_to_use: str = "",
        examples: Optional[list] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register an agent tool. The decorated function's return becomes the
        tool result (see module docstring).

        ``risk`` ("none"|"low"|"medium"|"high"|"critical") is the action's blast
        radius; the SDK gates a call whose risk exceeds the caller's autonomy,
        returning a decision packet instead of running the handler. ``reversible``
        / ``idempotent`` are advertised so the agent can reason about retries and
        keep an escape hatch. ``undo`` says *how* to reverse it (a human-readable
        note or the name of the compensating tool) — advertised in the manifest,
        the context endpoint, and every decision packet so the agent (and the
        approving human) always keeps an escape route. ``read_only`` marks a pure
        read (implies risk "none")."""
        if params_model is not None and parameters is not None:
            raise ValueError("pass either params_model or parameters, not both")
        params = (
            params_model.model_json_schema()
            if params_model is not None  # type: ignore[attr-defined]
            else (parameters or {"type": "object", "properties": {}})
        )
        eff_risk = "none" if read_only else normalize_risk(risk)

        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._tools[name] = _Tool(
                name,
                description,
                params,
                fn,
                card_type,
                streaming,
                requires_auth=requires_auth,
                params_model=params_model,
                risk=eff_risk,
                reversible=reversible,
                undo=undo,
                idempotent=idempotent,
                read_only=read_only,
                when_to_use=when_to_use,
                examples=examples or [],
            )
            return fn

        return deco

    def read(
        self,
        name: str,
        *,
        description: str = "",
        parameters: Optional[dict] = None,
        card_type: Optional[str] = None,
        streaming: bool = False,
        params_model: Optional[type] = None,
        when_to_use: str = "",
        examples: Optional[list] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a typed *read* — a pure state query (queue, WIP, OEE, …). Same
        as :meth:`tool` but ``read_only`` (risk "none", never gated)."""
        return self.tool(
            name,
            description=description,
            parameters=parameters,
            card_type=card_type,
            streaming=streaming,
            params_model=params_model,
            read_only=True,
            when_to_use=when_to_use,
            examples=examples,
        )

    def event(
        self, event_type: str, *, description: str = "", schema: Optional[dict] = None
    ) -> "_Event":
        """Declare an event type this module emits, so the manifest advertises it
        (type + JSON schema) for an agent to subscribe to."""
        ev = _Event(event_type, description, schema or {"type": "object"})
        self._events[event_type] = ev
        return ev

    def on_event(
        self, fn: Callable[[EventEnvelope], None]
    ) -> Callable[[EventEnvelope], None]:
        """Register a local subscriber called with every emitted envelope."""
        self._event_listeners.append(fn)
        return fn

    def on_decision(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Register the handler that runs a human's decision on a proposed action.

        Called with the decision dict (``verdict``/``action``/``arguments``/``note``)
        and may accept ``principal``. If unset, ``/connector/decision`` falls back
        to re-invoking the named tool for an approve/modify (human approval
        bypasses the risk gate)."""
        self._decision_handler = fn
        return fn

    # -- operational graph (linked context) -----------------------------------

    def graph(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Register the Operational-Graph provider for this module.

        The provider answers a linked-context query — ``fn(node, depth)`` (it may
        also accept ``principal``) — and returns ``{"nodes": [...], "edges":
        [...]}`` describing the context connected to ``node`` out to ``depth``
        hops. Exposed at ``GET/POST /connector/graph`` so the agent can pull
        connected context instead of staring at one isolated read. Optional: with
        no provider the endpoint fail-closes to an empty graph."""
        self._graph_provider = fn
        return fn

    def query_graph(
        self, node: Optional[str] = None, depth: int = 1,
        principal: Optional[Principal] = None,
    ) -> dict:
        """Run the registered graph provider (fail-closed to an empty graph)."""
        if self._graph_provider is None:
            return {"nodes": [], "edges": [], "available": False}
        kwargs: dict = {}
        if _accepts_arg(self._graph_provider, "node") or _has_var_keyword(self._graph_provider):
            kwargs["node"] = node
        if _accepts_arg(self._graph_provider, "depth") or _has_var_keyword(self._graph_provider):
            kwargs["depth"] = depth
        if _accepts_principal(self._graph_provider):
            kwargs["principal"] = principal or Principal()
        result = self._graph_provider(**kwargs)
        if not isinstance(result, dict):
            result = {"nodes": [], "edges": []}
        result.setdefault("nodes", [])
        result.setdefault("edges", [])
        result.setdefault("available", True)
        return result

    # -- UI surface (agent drives the real UI) --------------------------------

    def page(self, id: str, *, path: str, label: Optional[str] = None,
             description: str = "") -> Page:
        """Declare a navigable page so the agent can `navigate` to it by id.

        Declaring the first page auto-exposes a ``<module>_navigate`` tool so the
        agent can move the user between the module's screens without any custom
        wiring — the tool pushes a ``navigate`` UI intent to the session's bus,
        which the ``minder-ui-sdk`` ``AgentDriverProvider`` applies to the real
        router. Re-declaring pages refreshes the tool's page enum.
        """
        p = Page(id, path, label or id.replace("_", " ").title(), description)
        self._ui.pages[id] = p
        self._ensure_navigate_tool()
        return p

    def _navigate_tool_name(self) -> str:
        """Module-scoped name so two ui-driving modules don't collide on one
        generic ``navigate`` tool when core merges every module's proxy tools."""
        safe = "".join(c if (c.isalnum() or c == "_") else "_" for c in self.name)
        return f"{safe}_navigate"

    def _ensure_navigate_tool(self) -> None:
        """Register (or refresh) the built-in navigation tool from declared pages."""
        pages = list(self._ui.pages.values())
        if not pages:
            return
        ids = [p.id for p in pages]
        listing = "; ".join(f"{p.id} ({p.label})" for p in pages)

        def _handler(page: str, session_id: Optional[str] = None, **_kw: Any) -> dict:
            if page not in self._ui.pages:
                raise ToolError(
                    "unknown_page",
                    f"no page {page!r}; declared pages: {ids}",
                    retryable=False,
                )
            # Mirror push_ui_intent's demo convention: the mounted dashboard
            # subscribes to "default"; a chat turn also carries its session id.
            for sid in {"default", session_id} - {None}:
                self.push_ui_intent(sid, navigate(page), actor={"kind": "agent"})
            target = self._ui.pages[page]
            return {"output": f"Opened the {target.label} screen."}

        self.tool(
            self._navigate_tool_name(),
            description=(
                "Move the user to one of this module's screens. Pages: "
                f"{listing}. Navigation only — it changes the visible screen and "
                "does not modify any data."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "page": {
                        "type": "string",
                        "enum": ids,
                        "description": "Id of the declared page to open.",
                    }
                },
                "required": ["page"],
            },
            risk="low",
            reversible=True,
            idempotent=True,
        )(_handler)

    def form(
        self,
        id: str,
        *,
        route: str,
        fields: list[dict],
        submit_tool: Optional[str] = None,
        risk: str = "low",
        reversible: Optional[bool] = None,
        undo: Optional[str] = None,
        instructions: str = "",
    ) -> Form:
        """Declare a typed form the agent can prefill. ``submit_tool`` is the
        gated action run on submit; ``instructions`` is the per-form playbook;
        ``undo`` says how the submit is reversed (kept alongside the gate)."""
        f = Form(
            id, route, fields, submit_tool, normalize_risk(risk), reversible, undo, instructions
        )
        self._ui.forms[id] = f
        return f

    def control(self, id: str, *, label: str, route: str = "", effect: str = "",
                risk: str = "low") -> Control:
        """Declare a named control the agent may ask the user to activate."""
        c = Control(id, label, route, effect, normalize_risk(risk))
        self._ui.controls[id] = c
        return c

    def push_ui_intent(
        self, session_id: str, intent: dict, *, actor: Optional[dict] = None
    ) -> dict:
        """Send a UI intent to a session's frontend. Validates it against the
        declared surface (warns, doesn't block), records a ``ui.intent`` event
        for ground truth, and enqueues it for the SSE bus + any event sink."""
        if not is_intent(intent):
            raise ValueError(f"not a UI intent: {intent!r}")
        err = self._ui.validate(intent)
        if err:
            logger.warning("ui intent targets undeclared surface: %s", err)
        self._dispatch(
            make_envelope(
                self.name,
                "ui.intent",
                {"intent": intent, "warning": err},
                source="agent" if actor and actor.get("kind") == "agent" else "module",
                actor=actor,
                session_id=session_id,
            )
        )
        for q in self._ui_bus.get(session_id, []):
            try:
                q.put_nowait(intent)
            except Exception:  # noqa: BLE001 — full/closed queue: drop for that consumer
                pass
        return {"ok": True, "warning": err}

    def apply_decision(self, decision: dict, principal: Optional[Principal] = None) -> dict:
        """Execute a human decision. approve/modify re-invokes the action with
        full autonomy (a human approved it); reject is a no-op record."""
        principal = principal or Principal()
        if self._decision_handler is not None:
            kwargs: dict = {"decision": decision}
            if _accepts_principal(self._decision_handler):
                kwargs["principal"] = principal
            return {"success": True, "output": self._decision_handler(**kwargs)}
        verdict = decision.get("verdict")
        action = decision.get("action")
        if verdict == "reject":
            return {"success": True, "output": f"rejected {action}", "verdict": "reject"}
        if verdict in ("approve", "modify") and action in self._tools:
            return self._call(
                self._tools[action],
                decision.get("arguments") or {},
                principal,
                autonomy="critical",  # human approval overrides the gate
                session_id=decision.get("session_id"),
            )
        return self._fail(f"cannot apply decision for action {action!r}")

    def set_event_sink(self, sink: Optional[Callable[[EventEnvelope], None]]) -> None:
        """Route every emitted envelope to ``sink`` (e.g.
        ``conn.minder_client().emit_event``) so it lands in Minder's event log."""
        self._event_sink = sink

    def emit_event(
        self,
        event_type: str,
        payload: Optional[dict] = None,
        *,
        source: str = "module",
        actor: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> EventEnvelope:
        """Build and dispatch an event envelope to local subscribers + the sink."""
        env = make_envelope(
            self.name,
            event_type,
            payload,
            source=source,
            actor=actor,
            session_id=session_id,
        )
        self._dispatch(env)
        return env

    def _dispatch(self, env: EventEnvelope) -> None:
        for fn in self._event_listeners:
            try:
                fn(env)
            except Exception as exc:  # noqa: BLE001 — a bad subscriber must not fail the action
                logger.warning("event listener failed: %s", exc)
        if self._event_sink is not None:
            try:
                self._event_sink(env)
            except Exception as exc:  # noqa: BLE001 — event-log push is best-effort
                logger.debug("event sink failed (ignoring): %s", exc)

    def health_probe(self, fn: Callable[[], dict]) -> Callable[[], dict]:
        """Register a probe returning ``{sidecar: 'ok'|'error: …'}`` for /health."""
        self._health_probes.append(fn)
        return fn

    def readiness_probe(self, fn: Callable[[], Any]) -> Callable[[], Any]:
        """Register a readiness check: () -> bool | {"ready": bool, ...}. While any
        probe reports not-ready, Minder keeps this module's tools OUT of the agent
        catalog (the connector is alive but not serving yet)."""
        self._readiness_probes.append(fn)
        return fn

    def _ready(self) -> bool:
        for probe in self._readiness_probes:
            try:
                res = probe()
                ok = res.get("ready", True) if isinstance(res, dict) else bool(res)
                if not ok:
                    return False
            except Exception as exc:  # noqa: BLE001 — a failing probe means not-ready
                logger.warning("readiness probe failed: %s", exc)
                return False
        return True

    def on_startup(self, fn: Callable[[], None]) -> Callable[[], None]:
        """Register a callback run once when the connector boots. It runs on a
        daemon thread (so it never blocks readiness) — use it for slow, best-
        effort work like ingesting a data directory. Exceptions are logged, not
        fatal."""
        self._startup_hooks.append(fn)
        return fn

    def route(
        self, path: str, *, methods: Iterable[str] = ("POST",)
    ) -> Callable[[Callable], Callable]:
        """Register an extra connector endpoint, reachable via Minder's passthrough
        at ``/api/modules/{name}/connector{path}``. Handler may take ``principal``.
        """

        def deco(fn: Callable) -> Callable:
            self._extra_routes.append((path, list(methods), fn))
            return fn

        return deco

    def block(
        self,
        component: str,
        props: Optional[dict] = None,
        *,
        height: Any = "auto",
        title: Optional[str] = None,
    ) -> dict:
        """Build a federated chat-block descriptor for THIS module — fills
        remote_name (self.name) and remote_entry ($MINDER_MODULE_REMOTE_ENTRY)."""
        from .cards import block as _b

        remote_entry = os.environ.get("MINDER_MODULE_REMOTE_ENTRY", "")
        return _b(
            component,
            props,
            remote_name=self.name,
            remote_entry=remote_entry,
            height=height,
            title=title,
        )

    # -- tool invocation ------------------------------------------------------

    def _normalize(self, tool: _Tool, raw: Any) -> dict:
        """Coerce a handler return into the tool-response envelope."""
        if isinstance(raw, dict) and (
            "output" in raw
            or "card" in raw
            or "blocks" in raw
            or "success" in raw
            or "llm_suffix" in raw
        ):
            card = raw.get("card")
            return {
                "success": bool(raw.get("success", True)),
                "output": raw.get("output", card if card is not None else raw),
                "card": card,
                "card_type": raw.get("card_type") or tool.card_type,
                "llm_suffix": raw.get("llm_suffix"),
                "blocks": raw.get("blocks"),
            }
        # A bare value: it's both the agent output and (if a dict) the card.
        card = raw if isinstance(raw, dict) else None
        return {
            "success": True,
            "output": raw,
            "card": card,
            "card_type": tool.card_type if card is not None else None,
            "llm_suffix": None,
            "blocks": None,
        }

    @staticmethod
    def _fail(output: str, *, error: Optional[dict] = None) -> dict:
        """A handled-failure envelope (never a 500)."""
        return {
            "success": False,
            "output": output,
            "card": None,
            "card_type": None,
            "llm_suffix": None,
            "blocks": None,
            "error": error,
        }

    def invoke(
        self,
        tool_name: str,
        arguments: dict,
        *,
        principal: Optional[Principal] = None,
        session_id: Optional[str] = None,
        autonomy: Optional[str] = None,
        agent_id: Optional[str] = None,
        request_key: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict:
        """Invoke a registered tool in-process (for unit tests) — bypasses HTTP.
        Returns the same envelope the /connector/tools/{name} endpoint returns."""
        tool = self._tools[tool_name]
        return self._call(
            tool,
            arguments,
            principal or Principal(),
            session_id=session_id,
            autonomy=autonomy,
            agent_id=agent_id,
            request_key=request_key,
            dry_run=dry_run,
        )

    def _call(
        self,
        tool: _Tool,
        arguments: dict,
        principal: Principal,
        *,
        session_id: Optional[str] = None,
        autonomy: Optional[str] = None,
        agent_id: Optional[str] = None,
        request_key: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict:
        if tool.params_model is not None:
            try:
                validated = tool.params_model(**arguments)
                arguments = validated.model_dump()
            except Exception as exc:  # noqa: BLE001 — pydantic ValidationError etc.
                return self._fail(f"invalid arguments: {exc}")
        if tool.requires_auth and not principal.is_authenticated:
            return self._fail("authentication required")

        # Idempotency: a retried call with the same key returns the first result
        # instead of acting twice. Only meaningful for tools declared idempotent.
        cache_key = (tool.name, request_key) if (request_key and tool.idempotent) else None
        if cache_key is not None and cache_key in self._idem_cache:
            return self._idem_cache[cache_key]

        # The safety gate (moat): an action whose risk exceeds the caller's
        # autonomy is NOT executed — the SDK returns a decision packet the human
        # must approve, so the agent can't silently exceed its authority.
        eff_autonomy = autonomy or self.default_autonomy
        if not autonomy_allows(tool.risk, eff_autonomy):
            return self._gated_response(tool, arguments)

        # Dry-run / preview: see the consequence before touching real state. If the
        # handler understands dry_run we pass it through; otherwise we refuse to
        # run and return a preview packet so a non-dry-run-aware handler is never
        # executed under a preview request.
        handler_dry = dry_run and (
            _accepts_arg(tool.handler, "dry_run") or _has_var_keyword(tool.handler)
        )
        if dry_run and not handler_dry:
            return self._preview_response(tool, arguments)

        kwargs = dict(arguments)
        if _accepts_principal(tool.handler):
            kwargs["principal"] = principal
        if session_id is not None and (
            _accepts_arg(tool.handler, "session_id") or _has_var_keyword(tool.handler)
        ):
            kwargs["session_id"] = session_id
        if _accepts_arg(tool.handler, "autonomy") or _has_var_keyword(tool.handler):
            kwargs["autonomy"] = eff_autonomy
        if handler_dry:
            kwargs["dry_run"] = True

        actor = actor_from(principal, agent_id)
        # Ground truth: announce the action is starting, so the event log records
        # the attempt even if the handler crashes.
        if not tool.read_only and not dry_run:
            self._dispatch(
                make_envelope(
                    self.name,
                    "action.invoked",
                    {"tool": tool.name, "risk": tool.risk, "arguments": arguments},
                    source="agent" if agent_id else "module",
                    actor=actor,
                    session_id=session_id,
                )
            )
        try:
            raw = tool.handler(**kwargs)
            # A streaming tool invoked via the non-stream endpoint: drain it and
            # use its final event (or last yielded value) instead of serializing
            # the generator into a list of events.
            if inspect.isgenerator(raw):
                raw = self._drain(raw)
            result = self._normalize(tool, raw)
        except ToolError as exc:
            result = self._fail(exc.message, error=exc.as_error())
        except ServiceUnavailable as exc:
            reason = (
                f"The {self.display_name} is unavailable ({exc.service} unreachable), "
                "so this request cannot be completed with grounded results right now."
            )
            result = {
                "success": True,
                "output": unavailable_card(reason, service=exc.service),
                "card": unavailable_card(reason, service=exc.service),
                "card_type": tool.card_type or f"{self.name}_card",
                "llm_suffix": unavailable_suffix(self.name, exc.service),
            }

        if not tool.read_only and not dry_run:
            ok = bool(result.get("success", True))
            self._dispatch(
                make_envelope(
                    self.name,
                    "action.completed" if ok else "action.failed",
                    {
                        "tool": tool.name,
                        "success": ok,
                        "risk": tool.risk,
                        "reversible": tool.reversible,
                        "error": result.get("error"),
                    },
                    source="agent" if agent_id else "module",
                    actor=actor,
                    session_id=session_id,
                )
            )
        if cache_key is not None:
            self._remember(cache_key, result)
        return result

    def _gated_response(self, tool: _Tool, arguments: dict) -> dict:
        """Refuse to auto-run: return a decision packet for human approval."""
        packet = decision_packet(
            tool.name,
            arguments,
            summary=(
                f"'{tool.name}' is a {tool.risk}-risk action above the current autonomy "
                "level and needs approval before it runs."
            ),
            risk=tool.risk,
            reversible=tool.reversible,
            undo=tool.undo,
            card_type="decision_packet",
        )
        return {
            "success": True,
            "output": (
                f"Action '{tool.name}' ({tool.risk} risk) exceeds the current autonomy "
                "level; proposing it for approval instead of executing."
            ),
            "card": packet,
            "card_type": "decision_packet",
            "llm_suffix": (
                "\n\n[SYSTEM: This action was NOT executed — it needs human approval and "
                "exceeds the current autonomy. A decision card is already on the user's "
                "screen; they approve or reject it there. Tell the user it is awaiting their "
                "approval on that card and STOP. Do NOT send a message, notification, "
                "webhook, or email, and do NOT use any channel or other tool to request "
                "approval — the on-screen card IS the approval. Do not claim it is done.]"
            ),
            "requires_approval": True,
        }

    def _preview_response(self, tool: _Tool, arguments: dict) -> dict:
        """A dry-run against a handler that doesn't implement dry_run: describe
        the action without executing it."""
        packet = decision_packet(
            tool.name,
            arguments,
            summary=f"Preview of '{tool.name}' — not executed (dry run).",
            risk=tool.risk,
            reversible=tool.reversible,
            undo=tool.undo,
            card_type="decision_packet",
        )
        return {
            "success": True,
            "output": f"[dry-run] '{tool.name}' would run with {arguments!r}; not executed.",
            "card": packet,
            "card_type": "decision_packet",
            "llm_suffix": None,
            "dry_run": True,
        }

    def _remember(self, key: "tuple[str, str]", result: dict) -> None:
        if len(self._idem_cache) >= self._idem_cap:
            self._idem_cache.pop(next(iter(self._idem_cache)))
        self._idem_cache[key] = result

    @staticmethod
    def _drain(gen: Iterator[Any]) -> Any:
        """Consume a generator handler, returning its ``final`` event payload
        (minus the ``event`` key) or the last yielded value."""
        last: Any = None
        for evt in gen:
            if isinstance(evt, dict) and evt.get("event") == "final":
                return {k: v for k, v in evt.items() if k != "event"}
            if isinstance(evt, dict) and evt.get("event") in ("progress", "partial", "error"):
                continue
            last = evt
        return last

    # -- health ---------------------------------------------------------------

    def _sidecars(self) -> dict:
        out: dict = {}
        for probe in self._health_probes:
            try:
                res = probe()
                if isinstance(res, dict):
                    out.update(res)
            except Exception as exc:  # noqa: BLE001
                out["probe"] = f"error: {exc}"
        return out

    def _capabilities(self) -> dict:
        return {
            "streaming": any(t.streaming for t in self._tools.values()),
            "cards": any(t.card_type for t in self._tools.values()),
            "ui_driving": not self._ui.is_empty(),
            "graph": self._graph_provider is not None,
        }

    # -- app assembly ---------------------------------------------------------

    def _run_startup_hooks(self) -> None:
        """Fire each on_startup callback on its own daemon thread (never blocks
        readiness; a failing hook is logged, not fatal)."""
        import threading

        for fn in self._startup_hooks:

            def _run(f=fn) -> None:
                try:
                    f()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("startup hook %s failed: %s", getattr(f, "__name__", f), exc)

            threading.Thread(target=_run, name=f"{self.name}-startup", daemon=True).start()

    def asgi(self, *, cors_origins: Optional[list[str]] = None) -> FastAPI:
        """Build the FastAPI app implementing the full connector contract."""
        from .announce import resolve_announce_config, announce, deregister, start_heartbeat

        @asynccontextmanager
        async def _lifespan(_app):  # type: ignore[no-untyped-def]
            cfg = resolve_announce_config()
            stop_heartbeat = None
            if cfg is not None:
                try:
                    announce(self.name, cfg)
                except Exception as exc:  # noqa: BLE001 — don't crash the module on a flaky Minder
                    logger.warning("announce failed: %s", exc)
                # Keep re-announcing so a restarted Minder re-learns this live module.
                stop_heartbeat = start_heartbeat(self.name, cfg)
                self._maybe_wire_event_sink()
            self._run_startup_hooks()
            yield
            if stop_heartbeat is not None:
                stop_heartbeat()
            if cfg is not None:
                deregister(self.name, cfg)

        app = FastAPI(title=f"{self.name}-connector", lifespan=_lifespan)
        origins = (
            cors_origins
            or [o for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o]
            or ["*"]
        )
        app.add_middleware(
            CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"]
        )

        @app.get("/connector/health")
        def health() -> dict:
            return {
                "ok": True,
                "module": self.name,
                "version": self.version,
                "capabilities": self._capabilities(),
                "sidecars": self._sidecars(),
                "ready": self._ready(),
            }

        @app.get("/connector/context")
        def context(request: Request) -> dict:
            """What the agent may do here: the caller's autonomy + identity/scope,
            and each action's risk — so it can plan without probing by trial."""
            principal = _principal_from_headers(request)
            autonomy = _autonomy_from_headers(request) or self.default_autonomy
            session = _session_from_headers(request) or "default"
            return {
                "module": self.name,
                "autonomy": autonomy,
                "principal": {
                    "username": principal.username,
                    "authenticated": principal.is_authenticated,
                    "roles": principal.roles,
                    "scopes": principal.scopes,
                },
                "actions": [
                    {
                        "name": t.name,
                        "risk": t.risk,
                        "read_only": t.read_only,
                        "reversible": t.reversible,
                        "undo": t.undo,
                        "allowed": autonomy_allows(t.risk, autonomy),
                    }
                    for t in self._tools.values()
                ],
                "ui_snapshot": self._ui_snapshots.get(session),
                "state": build_state_entries(self._ctx_state, principal, session),
            }

        @app.get("/connector/manifest")
        def manifest() -> dict:
            base = os.environ.get(self._public_base_env, "").rstrip("/")
            remote = None
            if base:
                exposed = {"dashboard": "./Dashboard"}
                exposed.update({k: k for k in self._exposed_blocks})
                remote = {
                    "name": self.name,
                    "remoteEntry": f"{base}/dashboard/remoteEntry.js",
                    "exposed": exposed,
                }
            return {
                "name": self.name,
                "display_name": self.display_name,
                "version": self.version,
                "tools": self._tool_specs(),
                "events": self._event_specs(),
                "remote": remote,
                "card_types": sorted({t.card_type for t in self._tools.values() if t.card_type}),
                "ui": self._ui.to_dict(),
                "context": self._context_spec(),
                "contract_version": CONTRACT_VERSION,
                "min_core_version": self.min_core_version,
                "default_autonomy": self.default_autonomy,
            }

        @app.get("/connector/events")
        def events() -> StreamingResponse:
            """SSE stream of this module's event envelopes — the agent's
            subscription to state changes (backlog B2)."""
            import queue as _queue

            q: "_queue.Queue[EventEnvelope]" = _queue.Queue(maxsize=256)

            def listener(env: EventEnvelope) -> None:
                try:
                    q.put_nowait(env)
                except _queue.Full:  # slow consumer — drop rather than block the action
                    pass

            self._event_listeners.append(listener)

            def gen() -> Iterator[bytes]:
                try:
                    yield b": ok\n\n"
                    while True:
                        try:
                            env = q.get(timeout=15)
                            yield f"data: {json.dumps(env.to_dict())}\n\n".encode()
                        except _queue.Empty:
                            yield b": ping\n\n"
                finally:
                    try:
                        self._event_listeners.remove(listener)
                    except ValueError:
                        pass

            return StreamingResponse(gen(), media_type="text/event-stream")

        @app.get("/connector/ui/intents")
        def ui_intents(request: Request) -> StreamingResponse:
            """SSE stream of UI intents for one session — the module frontend's
            command bus (the agent drives the real UI through this)."""
            import queue as _queue

            session = request.query_params.get("session") or "default"
            q: "_queue.Queue[dict]" = _queue.Queue(maxsize=256)
            self._ui_bus.setdefault(session, []).append(q)

            def gen() -> Iterator[bytes]:
                try:
                    yield b": ok\n\n"
                    while True:
                        try:
                            intent = q.get(timeout=15)
                            yield f"data: {json.dumps(intent)}\n\n".encode()
                        except _queue.Empty:
                            yield b": ping\n\n"
                finally:
                    subs = self._ui_bus.get(session, [])
                    if q in subs:
                        subs.remove(q)

            return StreamingResponse(gen(), media_type="text/event-stream")

        @app.post("/connector/ui/intent")
        async def ui_intent(request: Request) -> dict:
            """Accept a UI intent from Minder core (agent-originated) and route it
            to the target session's frontend bus."""
            body = await _json_body(request)
            session = body.get("session_id") or "default"
            intent = body.get("intent") or {}
            actor = body.get("actor")
            try:
                return self.push_ui_intent(session, intent, actor=actor)
            except ValueError as exc:
                return self._fail(str(exc))

        @app.post("/connector/ui/snapshot")
        async def ui_snapshot(request: Request) -> dict:
            """Cache the frontend's declarative UI snapshot for one session so the
            agent can read what's currently on screen via ``/connector/context``."""
            body = await _json_body(request)
            session = body.get("session_id") or "default"
            self._ui_snapshots[session] = body.get("snapshot") or {}
            return {"ok": True}

        @app.post("/connector/decision")
        async def decision(request: Request) -> dict:
            """Receive a human's approve/modify/reject on a proposed action and
            apply it (backlog D2)."""
            body = await _json_body(request)
            principal = _principal_from_headers(request)
            try:
                return self.apply_decision(body, principal)
            except Exception as exc:  # noqa: BLE001 — never 500 the UI
                logger.exception("decision apply failed")
                return self._fail(f"decision failed: {exc}")

        @app.api_route("/connector/graph", methods=["GET", "POST"])
        async def graph(request: Request) -> dict:
            """Query the module's Operational Graph for linked context around a
            node (BE-SDK-10). ``node``/``depth`` come from the query string (GET)
            or the JSON body (POST). Fail-closed to an empty graph when the module
            declared no provider."""
            principal = _principal_from_headers(request)
            body = await _json_body(request) if request.method == "POST" else {}
            node = body.get("node") or request.query_params.get("node")
            raw_depth = body.get("depth") or request.query_params.get("depth")
            try:
                depth = int(raw_depth) if raw_depth is not None else 1
            except (TypeError, ValueError):
                depth = 1
            try:
                return self.query_graph(node, depth, principal)
            except Exception as exc:  # noqa: BLE001 — never 500 the agent
                logger.exception("graph query failed")
                return {"nodes": [], "edges": [], "available": True, "error": str(exc)}

        @app.post("/connector/tools/{name}")
        async def call_tool(name: str, request: Request) -> dict:
            tool = self._tools.get(name)
            if tool is None:
                raise HTTPException(404, f"unknown tool {name!r}")
            body = await _json_body(request)
            principal = _principal_from_headers(request)
            ctx = _call_ctx_from_headers(request)
            try:
                return self._call(tool, body.get("arguments") or {}, principal, **ctx)
            except HTTPException:
                raise
            except Exception as exc:  # noqa: BLE001 — never 500 the agent
                logger.exception("tool %s failed", name)
                return {
                    "success": False,
                    "output": f"{name} failed: {exc}",
                    "card": None,
                    "card_type": None,
                    "llm_suffix": None,
                }

        @app.post("/connector/tools/{name}/stream")
        async def stream_tool(name: str, request: Request) -> StreamingResponse:
            tool = self._tools.get(name)
            if tool is None:
                raise HTTPException(404, f"unknown tool {name!r}")
            body = await _json_body(request)
            principal = _principal_from_headers(request)
            ctx = _call_ctx_from_headers(request)
            args = body.get("arguments") or {}
            return StreamingResponse(
                self._sse(tool, args, principal, **ctx),
                media_type="text/event-stream",
            )

        for path, methods, fn in self._extra_routes:
            self._mount_extra(app, path, methods, fn)

        self._mount_dashboard(app)

        return app

    def _context_spec(self) -> dict:
        """Static agent context for the manifest: domain knowledge + area notes."""
        return {
            "knowledge": list(self._ctx_knowledge),
            "notes": [{"name": n.name, "text": n.text} for n in self._ctx_notes],
        }

    def _tool_specs(self) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                "streaming": t.streaming,
                "risk": t.risk,
                "read_only": t.read_only,
                "reversible": t.reversible,
                "undo": t.undo,
                "idempotent": t.idempotent,
                "when_to_use": t.when_to_use,
                "examples": t.examples,
            }
            for t in self._tools.values()
        ]

    def _event_specs(self) -> list[dict]:
        return [
            {"type": e.type, "description": e.description, "schema": e.schema}
            for e in self._events.values()
        ]

    def _sse(
        self,
        tool: _Tool,
        args: dict,
        principal: Principal,
        *,
        session_id: Optional[str] = None,
        autonomy: Optional[str] = None,
        agent_id: Optional[str] = None,
        request_key: Optional[str] = None,
        dry_run: bool = False,
    ) -> Iterator[bytes]:
        def emit(obj: dict) -> bytes:
            return f"data: {json.dumps(obj)}\n\n".encode()

        # The safety gate applies to streaming too: a generator handler bypasses
        # _call, so gate/dry-run here before consuming it.
        eff_autonomy = autonomy or self.default_autonomy
        if not autonomy_allows(tool.risk, eff_autonomy):
            yield emit({"event": "final", **self._gated_response(tool, args)})
            return
        if dry_run and not (
            _accepts_arg(tool.handler, "dry_run") or _has_var_keyword(tool.handler)
        ):
            yield emit({"event": "final", **self._preview_response(tool, args)})
            return

        # If the handler is a generator, stream its yields; else run once + final.
        try:
            if inspect.isgeneratorfunction(tool.handler):
                kwargs = dict(args)
                if _accepts_principal(tool.handler):
                    kwargs["principal"] = principal
                if session_id is not None and (
                    _accepts_arg(tool.handler, "session_id") or _has_var_keyword(tool.handler)
                ):
                    kwargs["session_id"] = session_id
                if _accepts_arg(tool.handler, "autonomy") or _has_var_keyword(tool.handler):
                    kwargs["autonomy"] = eff_autonomy
                if dry_run:
                    kwargs["dry_run"] = True
                last: Any = None
                for evt in tool.handler(**kwargs):
                    if isinstance(evt, dict) and evt.get("event"):
                        yield emit(evt)
                        if evt["event"] in ("final", "error"):
                            return
                    else:
                        last = evt
                final = self._normalize(tool, last)
                yield emit({"event": "final", **final})
            else:
                final = self._call(
                    tool,
                    args,
                    principal,
                    session_id=session_id,
                    autonomy=autonomy,
                    agent_id=agent_id,
                    request_key=request_key,
                    dry_run=dry_run,
                )
                yield emit({"event": "final", **final})
        except Exception as exc:  # noqa: BLE001
            logger.exception("stream tool %s failed", tool.name)
            yield emit({"event": "error", "message": str(exc)})

    def _mount_extra(self, app: FastAPI, path: str, methods: list[str], fn: Callable) -> None:
        async def endpoint(request: Request) -> Any:
            principal = _principal_from_headers(request)
            kwargs: dict = {}
            if _accepts_principal(fn):
                kwargs["principal"] = principal
            if request.method != "GET" and _accepts_arg(fn, "body"):
                kwargs["body"] = await _json_body(request)
            result = fn(**kwargs)
            return await result if inspect.isawaitable(result) else result

        app.add_api_route(f"/connector{path}", endpoint, methods=methods)

    def minder_client(self) -> "MinderClient":
        """Build a reverse-push client for this module (needs MINDER_URL + a
        module-push service token). Raises MinderClientError if unconfigured."""
        from .announce import resolve_announce_config
        from .client import MinderClient, MinderClientError

        cfg = resolve_announce_config()
        if cfg is None:
            raise MinderClientError("announce config absent (MINDER_URL/CONNECTOR_URL unset)")
        return MinderClient(self.name, cfg)

    def _maybe_wire_event_sink(self) -> None:
        """When ``MINDER_MODULE_EMIT_EVENTS`` is truthy, ship every emitted
        envelope to Minder's event log on a daemon thread (best-effort, never
        blocks the request). Off by default so existing modules see no new
        network traffic until they opt in."""
        if os.environ.get("MINDER_MODULE_EMIT_EVENTS", "").lower() not in ("1", "true", "yes"):
            return
        try:
            client = self.minder_client()
        except Exception as exc:  # noqa: BLE001 — no push creds ⇒ just don't wire a sink
            logger.debug("event sink not wired: %s", exc)
            return

        import threading

        def sink(env: EventEnvelope) -> None:
            threading.Thread(
                target=lambda: client.emit_event(env), name=f"{self.name}-event", daemon=True
            ).start()

        self.set_event_sink(sink)

    def _mount_dashboard(self, app: FastAPI) -> None:
        dist = Path(os.environ.get(self._dashboard_dist_env, "/app/frontend_dist"))
        if dist.is_dir():
            app.mount("/dashboard", StaticFiles(directory=str(dist)), name="dashboard")


# -- helpers ------------------------------------------------------------------


def _accepts_principal(fn: Callable) -> bool:
    return _accepts_arg(fn, "principal") or _has_var_keyword(fn)


def _accepts_arg(fn: Callable, arg: str) -> bool:
    try:
        return arg in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def _has_var_keyword(fn: Callable) -> bool:
    try:
        return any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in inspect.signature(fn).parameters.values()
        )
    except (TypeError, ValueError):
        return False


async def _json_body(request: Request) -> dict:
    if not await request.body():
        return {}
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _session_from_headers(request: Request) -> Optional[str]:
    return request.headers.get("X-Minder-Session") or None


def _autonomy_from_headers(request: Request) -> Optional[str]:
    return request.headers.get("X-Minder-Autonomy") or None


def _call_ctx_from_headers(request: Request) -> dict:
    """The per-call safety context Minder core forwards: session, autonomy level,
    acting agent id, idempotency key, and a dry-run flag. All optional — a pre-v3
    core sends none and behavior is unchanged (default autonomy, no gating)."""
    dry = (request.headers.get("X-Minder-Dry-Run") or "").lower() in ("1", "true", "yes")
    return {
        "session_id": _session_from_headers(request),
        "autonomy": _autonomy_from_headers(request),
        "agent_id": request.headers.get("X-Minder-Agent") or None,
        "request_key": request.headers.get("X-Minder-Request-Key") or None,
        "dry_run": dry,
    }


def _str_list(val: Any) -> list[str]:
    return [str(x) for x in val] if isinstance(val, list) else []


def _principal_from_headers(request: Request) -> Principal:
    raw = request.headers.get("X-Minder-Principal")
    if not raw:
        return Principal()
    try:
        data = json.loads(raw)
        return Principal(
            username=str(data.get("username") or "unknown"),
            email=str(data.get("email") or ""),
            roles=_str_list(data.get("roles")),
            scopes=_str_list(data.get("scopes")),
        )
    except (ValueError, AttributeError):
        return Principal()
