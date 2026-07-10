"""Connector — turn a handful of Python functions into an Atria service-module.

The SDK generates the whole connector HTTP contract (docs/connector-contract.md)
from decorated handlers, so the service and the module's ``manifest.json`` can't
drift, and fail-closed behavior is built in. It never imports ``atria`` — the
service runs in its own slim container.

    from atria_module_sdk import Connector, ServiceUnavailable, card

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .cards import unavailable_card, unavailable_suffix

logger = logging.getLogger("atria_module_sdk")


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


@dataclass
class Principal:
    """The acting Atria user, forwarded on each call (may be anonymous)."""

    username: str = "unknown"
    email: str = ""

    @property
    def is_authenticated(self) -> bool:
        return self.username not in ("", "unknown")


class Connector:
    """Builds an Atria service-module's connector app from decorated handlers."""

    def __init__(self, name: str, *, version: str = "1",
                 display_name: Optional[str] = None,
                 public_base_env: str = "MODULE_PUBLIC_BASE",
                 dashboard_dist_env: str = "MODULE_DASHBOARD_DIST") -> None:
        self.name = name
        self.version = version
        self.display_name = display_name or name.replace("_", " ").title()
        self._tools: dict[str, _Tool] = {}
        self._health_probes: list[Callable[[], dict]] = []
        self._extra_routes: list[tuple[str, list[str], Callable]] = []
        self._public_base_env = public_base_env
        self._dashboard_dist_env = dashboard_dist_env

    # -- registration ---------------------------------------------------------

    def tool(self, name: str, *, description: str = "", parameters: Optional[dict] = None,
             card_type: Optional[str] = None, streaming: bool = False
             ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register an agent tool. The decorated function's return becomes the
        tool result (see module docstring)."""
        params = parameters or {"type": "object", "properties": {}}

        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._tools[name] = _Tool(name, description, params, fn, card_type, streaming)
            return fn

        return deco

    def health_probe(self, fn: Callable[[], dict]) -> Callable[[], dict]:
        """Register a probe returning ``{sidecar: 'ok'|'error: …'}`` for /health."""
        self._health_probes.append(fn)
        return fn

    def route(self, path: str, *, methods: Iterable[str] = ("POST",)
              ) -> Callable[[Callable], Callable]:
        """Register an extra connector endpoint, reachable via Atria's passthrough
        at ``/api/modules/{name}/connector{path}``. Handler may take ``principal``.
        """
        def deco(fn: Callable) -> Callable:
            self._extra_routes.append((path, list(methods), fn))
            return fn

        return deco

    # -- tool invocation ------------------------------------------------------

    def _normalize(self, tool: _Tool, raw: Any) -> dict:
        """Coerce a handler return into the tool-response envelope."""
        if isinstance(raw, dict) and (
            "output" in raw or "card" in raw or "success" in raw or "llm_suffix" in raw
        ):
            card = raw.get("card")
            return {
                "success": bool(raw.get("success", True)),
                "output": raw.get("output", card if card is not None else raw),
                "card": card,
                "card_type": raw.get("card_type") or tool.card_type,
                "llm_suffix": raw.get("llm_suffix"),
            }
        # A bare value: it's both the agent output and (if a dict) the card.
        card = raw if isinstance(raw, dict) else None
        return {"success": True, "output": raw, "card": card,
                "card_type": tool.card_type if card is not None else None,
                "llm_suffix": None}

    def _call(self, tool: _Tool, arguments: dict, principal: Principal) -> dict:
        kwargs = dict(arguments)
        if _accepts_principal(tool.handler):
            kwargs["principal"] = principal
        try:
            raw = tool.handler(**kwargs)
            # A streaming tool invoked via the non-stream endpoint: drain it and
            # use its final event (or last yielded value) instead of serializing
            # the generator into a list of events.
            if inspect.isgenerator(raw):
                raw = self._drain(raw)
            return self._normalize(tool, raw)
        except ServiceUnavailable as exc:
            reason = (f"The {self.display_name} is unavailable ({exc.service} unreachable), "
                      "so this request cannot be completed with grounded results right now.")
            return {"success": True, "output": unavailable_card(reason, service=exc.service),
                    "card": unavailable_card(reason, service=exc.service),
                    "card_type": tool.card_type or f"{self.name}_card",
                    "llm_suffix": unavailable_suffix(self.name, exc.service)}

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
        return {"streaming": any(t.streaming for t in self._tools.values()),
                "cards": any(t.card_type for t in self._tools.values())}

    # -- app assembly ---------------------------------------------------------

    def asgi(self, *, cors_origins: Optional[list[str]] = None) -> FastAPI:
        """Build the FastAPI app implementing the full connector contract."""
        app = FastAPI(title=f"{self.name}-connector")
        origins = cors_origins or [
            o for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o
        ] or ["*"]
        app.add_middleware(CORSMiddleware, allow_origins=origins,
                           allow_methods=["*"], allow_headers=["*"])

        @app.get("/connector/health")
        def health() -> dict:
            return {"ok": True, "module": self.name, "version": self.version,
                    "capabilities": self._capabilities(), "sidecars": self._sidecars()}

        @app.get("/connector/manifest")
        def manifest() -> dict:
            base = os.environ.get(self._public_base_env, "").rstrip("/")
            remote = None
            if base:
                remote = {"name": self.name,
                          "remoteEntry": f"{base}/dashboard/remoteEntry.js",
                          "exposed": {"dashboard": "./Dashboard"}}
            return {"name": self.name, "display_name": self.display_name,
                    "version": self.version, "tools": self._tool_specs(),
                    "remote": remote}

        @app.post("/connector/tools/{name}")
        async def call_tool(name: str, request: Request) -> dict:
            tool = self._tools.get(name)
            if tool is None:
                raise HTTPException(404, f"unknown tool {name!r}")
            body = await _json_body(request)
            principal = _principal_from_headers(request)
            try:
                return self._call(tool, body.get("arguments") or {}, principal)
            except HTTPException:
                raise
            except Exception as exc:  # noqa: BLE001 — never 500 the agent
                logger.exception("tool %s failed", name)
                return {"success": False, "output": f"{name} failed: {exc}",
                        "card": None, "card_type": None, "llm_suffix": None}

        @app.post("/connector/tools/{name}/stream")
        async def stream_tool(name: str, request: Request) -> StreamingResponse:
            tool = self._tools.get(name)
            if tool is None:
                raise HTTPException(404, f"unknown tool {name!r}")
            body = await _json_body(request)
            principal = _principal_from_headers(request)
            args = body.get("arguments") or {}
            return StreamingResponse(self._sse(tool, args, principal),
                                     media_type="text/event-stream")

        for path, methods, fn in self._extra_routes:
            self._mount_extra(app, path, methods, fn)

        self._mount_dashboard(app)
        return app

    def _tool_specs(self) -> list[dict]:
        return [{"name": t.name, "description": t.description, "parameters": t.parameters}
                for t in self._tools.values()]

    def _sse(self, tool: _Tool, args: dict, principal: Principal) -> Iterator[bytes]:
        def emit(obj: dict) -> bytes:
            return f"data: {json.dumps(obj)}\n\n".encode()

        # If the handler is a generator, stream its yields; else run once + final.
        try:
            if inspect.isgeneratorfunction(tool.handler):
                kwargs = dict(args)
                if _accepts_principal(tool.handler):
                    kwargs["principal"] = principal
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
                final = self._call(tool, args, principal)
                yield emit({"event": "final", **final})
        except Exception as exc:  # noqa: BLE001
            logger.exception("stream tool %s failed", tool.name)
            yield emit({"event": "error", "message": str(exc)})

    def _mount_extra(self, app: FastAPI, path: str, methods: list[str],
                     fn: Callable) -> None:
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
        return any(p.kind == inspect.Parameter.VAR_KEYWORD
                   for p in inspect.signature(fn).parameters.values())
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


def _principal_from_headers(request: Request) -> Principal:
    raw = request.headers.get("X-Atria-Principal")
    if not raw:
        return Principal()
    try:
        data = json.loads(raw)
        return Principal(username=str(data.get("username") or "unknown"),
                         email=str(data.get("email") or ""))
    except (ValueError, AttributeError):
        return Principal()
