"""Module interactive dashboard routes.

Provides a subprocess gateway so a module's static dashboard (templates +
scripts) can invoke its own Python scripts via HTTP. Future tasks append
additional routes (artifact serving, websocket streams, etc.) to this same
router.
"""

from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from minder.core.modules import store as _store
from minder.core.modules.registry import ModuleRegistry
from minder.core.modules.store import InvalidModuleName, ModuleNotFound
from minder.core.services.module_chat_service import ModuleChatService
from minder.web.dependencies.modules import get_modules_registry
from minder.web.dependencies.services import get_module_chat_service

router = APIRouter(prefix="/api/modules", tags=["module-dashboard"])


# ── Concurrency tracking ──────────────────────────────────────────────────────

_MAX_INFLIGHT_PER_KEY = 4
_inflight_lock = threading.Lock()
_inflight: dict[tuple[str, str], int] = defaultdict(int)


def _try_acquire(session_id: str, module_name: str) -> bool:
    key = (session_id, module_name)
    with _inflight_lock:
        if _inflight[key] >= _MAX_INFLIGHT_PER_KEY:
            return False
        _inflight[key] += 1
        return True


def _release(session_id: str, module_name: str) -> None:
    key = (session_id, module_name)
    with _inflight_lock:
        if _inflight[key] > 0:
            _inflight[key] -= 1
        if _inflight[key] == 0:
            _inflight.pop(key, None)


# ── Request / response models ─────────────────────────────────────────────────


class RunBody(BaseModel):
    script: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    stdin: str | None = None
    timeout_ms: int = Field(default=30000, ge=1, le=120000)


class RunResponse(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


class RpcBody(BaseModel):
    method: str = Field(min_length=1)
    payload: dict = Field(default_factory=dict)
    timeout_ms: int = Field(default=30000, ge=1, le=120000)


class ChatBody(BaseModel):
    message: str = Field(min_length=1)
    chat_session_id: str | None = None
    # The caller's ACTIVE chat session (from $MINDER_SESSION_ID): used only to
    # attribute a newly created Minder session to the same user, so it shows
    # up in that user's history list.
    context_session_id: str | None = None
    # Preferred identity: the browser user resolved by /run and forwarded via
    # $MINDER_USER_ID (context_session_id remains as fallback).
    user_id: int | None = None


class ChatSaveBody(BaseModel):
    chat_session_id: str = Field(min_length=1)
    create_workspace: bool = False
    context_session_id: str | None = None
    user_id: int | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _resolve_session_id(request: Request) -> str:
    sid = request.cookies.get("session_id")
    if sid:
        return sid
    sid = request.headers.get("x-minder-session-id")
    if sid:
        return sid
    return "default"


async def _optional_user_id(request: Request) -> int | None:
    """Resolve the browser's logged-in user, or None (never raises).

    The module router is deliberately ungated, but dashboard fetches carry the
    ``minder_session`` cookie — resolving it lets module subprocesses (via
    ``MINDER_USER_ID``) attribute sessions/projects to the real user.
    """
    from minder.web.dependencies.auth import require_authenticated_user

    try:
        user = await require_authenticated_user(request)
        return user.id or None  # anonymous user id 0 -> None
    except HTTPException:
        return None
    except Exception:
        return None


def _resolve_script(module_dir: Path, script: str) -> Path:
    # Reject absolute paths up front.
    if script.startswith("/") or Path(script).is_absolute():
        raise HTTPException(
            status_code=400,
            detail={"kind": "path-escape", "message": f"absolute paths not allowed: {script!r}"},
        )
    scripts_dir = (module_dir / "scripts").resolve()
    candidate = (scripts_dir / script).resolve()
    try:
        candidate.relative_to(scripts_dir)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={
                "kind": "path-escape",
                "message": f"script path escapes scripts/: {script!r}",
            },
        ) from None
    return candidate


def run_module_rpc(
    reg: ModuleRegistry,
    name: str,
    method: str,
    payload: dict,
    session_id: str,
    timeout_ms: int = 30000,
) -> dict:
    """Run a module's ``scripts/rpc.py`` with the given method/payload/session_id on stdin.

    Returns ``{"ok": True, "data": ...}`` on success, ``{"ok": False, "error": ...}`` on
    failure. Raises ``HTTPException`` for unknown module / missing handler.
    """
    try:
        module = reg.get(name)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail={"kind": "unknown-module", "message": f"module {name!r} not found"},
        ) from None

    module_dir = module.dir.resolve()
    target = _resolve_script(module_dir, "rpc.py")
    if not target.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "kind": "unknown-rpc-handler",
                "message": f"module {name!r} has no scripts/rpc.py",
            },
        )

    env = os.environ.copy()
    env["MINDER_SESSION_ID"] = session_id
    env["MINDER_MODULE_ROOT"] = str(module_dir)
    env.setdefault("MINDER_API_BASE", "http://127.0.0.1:8000")
    stdin = json.dumps({"method": method, "payload": payload, "session_id": session_id})
    try:
        proc = subprocess.run(
            [sys.executable, str(target)],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000.0,
            env=env,
            cwd=str(module_dir),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"rpc timeout after {timeout_ms} ms"}
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or "non-zero exit").strip()}
    try:
        return {"ok": True, "data": json.loads(proc.stdout or "null")}
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"rpc stdout not valid JSON: {exc}"}


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/{name}/run", response_model=RunResponse)
def run_script(
    name: str,
    body: RunBody,
    request: Request,
    reg: ModuleRegistry = Depends(get_modules_registry),
    user_id: int | None = Depends(_optional_user_id),
) -> RunResponse:
    try:
        module = reg.get(name)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail={"kind": "unknown-module", "message": f"module {name!r} not found"},
        ) from None

    module_dir = module.dir.resolve()
    root_resolved = reg.root.resolve()
    try:
        module_dir.relative_to(root_resolved)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={"kind": "unknown-module", "message": f"module {name!r} not found"},
        ) from None
    if not module_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail={"kind": "unknown-module", "message": f"module {name!r} not found"},
        )

    target = _resolve_script(module_dir, body.script)
    if not target.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "kind": "unknown-script",
                "message": f"script {body.script!r} not found in module {name!r}",
            },
        )

    session_id = _resolve_session_id(request)
    if not _try_acquire(session_id, name):
        raise HTTPException(
            status_code=429,
            detail={
                "kind": "rate-limited",
                "message": (
                    f"too many in-flight runs for session/module " f"(max {_MAX_INFLIGHT_PER_KEY})"
                ),
            },
        )

    try:
        env = os.environ.copy()
        env["MINDER_SESSION_ID"] = session_id
        env["MINDER_MODULE_ROOT"] = str(module_dir)
        if user_id is not None:
            env["MINDER_USER_ID"] = str(user_id)
        env.setdefault("MINDER_API_BASE", "http://127.0.0.1:8000")
        # Force UTF-8 on both sides of the pipe: Windows otherwise falls back
        # to the ANSI code page and non-ASCII payloads (e.g. Vietnamese CSV
        # imports) raise UnicodeEncodeError before the script even runs.
        env.setdefault("PYTHONIOENCODING", "utf-8")

        cmd = [sys.executable, str(target), *body.args]
        timeout_s = body.timeout_ms / 1000.0
        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                input=body.stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
                env=env,
                cwd=str(module_dir),
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            return RunResponse(
                exit_code=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            stdout = (
                e.stdout if isinstance(e.stdout, str) else (e.stdout.decode() if e.stdout else "")
            )
            stderr = (
                e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else "")
            )
            stderr = (stderr or "") + f"\n[minder] script timeout after {body.timeout_ms} ms"
            return RunResponse(
                exit_code=-1,
                stdout=stdout or "",
                stderr=stderr,
                duration_ms=duration_ms,
            )
    finally:
        _release(session_id, name)


@router.post("/{name}/rpc")
def module_rpc(
    name: str,
    body: RpcBody,
    request: Request,
    reg: ModuleRegistry = Depends(get_modules_registry),
) -> dict:
    session_id = _resolve_session_id(request)
    if not _try_acquire(session_id, name):
        raise HTTPException(
            status_code=429,
            detail={"kind": "rate-limited", "message": "too many in-flight runs"},
        )
    try:
        return run_module_rpc(reg, name, body.method, body.payload, session_id, body.timeout_ms)
    finally:
        _release(session_id, name)


# ── Module dashboard chat (real agent, synchronous reply) ───────────────────


@router.post("/{name}/chat")
async def module_chat(
    name: str,
    body: ChatBody,
    reg: ModuleRegistry = Depends(get_modules_registry),
) -> dict:
    """Run one turn of the REAL main-chat agent for a module dashboard.

    Module iframes cannot open WebSockets (sandboxed, bridge-only), so this
    route awaits ``AgentExecutor.execute_query`` — the same pipeline behind
    ``/ws`` and ``/api/chat/query`` — and returns the final reply in the
    response body. Each dashboard conversation runs in its own dedicated
    session (auto-titled from the first message, visible in history); the
    app's "current session" pointer is preserved so the open chat UI is
    never hijacked. Lives on the ungated module router by design (same
    posture as ``/{name}/run``).
    """
    # Inline imports mirror chat.py/websocket.py to avoid module-load-order
    # issues between sibling web modules.
    from minder.models.message import ChatMessage, Role
    from minder.web.agent_executor import AgentExecutor
    from minder.web.state import get_state
    from minder.web.websocket import ws_manager

    try:
        module = reg.get(name)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail={"kind": "unknown-module", "message": f"module {name!r} not found"},
        ) from None

    message = body.message.strip()
    if not message:
        raise HTTPException(
            status_code=400,
            detail={"kind": "bad-request", "message": "message cannot be empty"},
        )

    state = get_state()
    sm = state.session_manager

    session = None
    session_id = body.chat_session_id
    if session_id:
        if state.is_session_running(session_id):
            raise HTTPException(
                status_code=409,
                detail={"kind": "busy", "message": "session is already running"},
            )
        try:
            session = await sm.get_session_by_id(session_id)
        except FileNotFoundError:
            session = None
    try:
        if session is None:
            # Attribute the new session to the browser's logged-in user
            # (forwarded via MINDER_USER_ID), else the caller's active chat
            # session's owner; else the provisioned default.
            owner_id = None
            user_id = None
            if body.user_id:
                user_id = int(body.user_id)
                owner_id = str(user_id)
            elif body.context_session_id:
                try:
                    ctx = await sm.get_session_by_id(body.context_session_id)
                    if ctx is not None and ctx.owner_id and str(ctx.owner_id).isdigit():
                        owner_id = str(ctx.owner_id)
                        user_id = int(ctx.owner_id)
                except (FileNotFoundError, ValueError):
                    pass

            # Start the chat "on the warehouse": the session's working
            # directory IS the module folder, so the agent's bash cwd holds
            # scripts/inventory.py + data/warehouse.db — it reads live data
            # directly (python scripts/inventory.py snapshot) instead of
            # exploring an empty folder, and any report it writes lands here
            # and shows in the conversation's Files tab.
            try:
                working_directory = str(module.dir)
            except Exception:
                working_directory = None
            # Keep the user's workspace project for history visibility + Save.
            project_id = None
            if user_id is not None:
                from minder.web.dependencies.workspace import ensure_user_workspace

                try:
                    ws = await ensure_user_workspace(user_id)
                    project_id = ws.project_id
                except Exception:  # workspace provisioning is best-effort
                    project_id = None

            prev_current = await sm.get_current_session()
            session = await sm.create_session(
                working_directory=working_directory,
                channel="web",
                owner_id=owner_id,
                user_id=user_id,
                project_id=project_id,
            )
            sm.current_session = prev_current
            session_id = session.id

        session.add_message(ChatMessage(role=Role.USER, content=message))
        await sm.save_session(session)

        if not hasattr(state, "_agent_executor") or state._agent_executor is None:
            state._agent_executor = AgentExecutor(state)

        if not _try_acquire(session_id, name):
            raise HTTPException(
                status_code=429,
                detail={"kind": "rate-limited", "message": "too many in-flight runs"},
            )
        try:
            # Thinking OFF: the warehouse chat should give fast, data-based
            # answers (read the CLI, reply) without a separate reasoning pass.
            result = await state._agent_executor.execute_query(
                message, ws_manager, session_id=session_id, session=session,
                thinking_level_override="Off",
            )
        finally:
            _release(session_id, name)
    except HTTPException:
        raise
    except Exception as exc:  # surface the cause — this gateway has no UI logs
        import logging

        logging.getLogger("minder.web").exception("module chat failed")
        raise HTTPException(
            status_code=500,
            detail={"kind": "chat-failed", "message": f"{type(exc).__name__}: {exc}"},
        ) from exc

    if result is None:
        result = {"summary": "", "error": "agent execution failed (see server log)"}

    # ReactExecutor's "summary" is the last operation label (e.g. a tool call
    # description) — the actual answer is the final assistant message the run
    # persisted to the session transcript.
    reply = ""
    try:
        fresh = await sm.get_session_by_id(session_id)
    except FileNotFoundError:
        fresh = session
    for m in reversed(list(getattr(fresh, "messages", None) or [])):
        role = getattr(m, "role", None)
        role_val = str(getattr(role, "value", role) or "").lower()
        content = getattr(m, "content", None)
        if role_val == "assistant" and content and str(content).strip():
            reply = str(content).strip()
            break
    if not reply:
        reply = result.get("summary") or ""

    return {
        "reply": reply,
        "error": result.get("error"),
        "latency_ms": result.get("latency_ms"),
        "session_id": session_id,
    }


def _strip_minder_preamble(text: str) -> str:
    """Drop the widget's grounding preamble from a user message (for titles).

    The preamble ends with a ``\\nUser: `` marker; the real question follows it.
    """
    stripped = text.lstrip()
    if stripped.startswith("[You are Minder") or stripped.startswith(
        "[Warehouse assistant"
    ) or stripped.startswith("[You are answering inside"):
        marker = "\nUser: "
        idx = text.rfind(marker)
        if idx != -1:
            return text[idx + len(marker):]
        _, sep, rest = text.partition("]\n\n")
        if sep:
            return rest
    return text


def _summary_title_prompt(messages: list) -> list[dict]:
    """Build the LLM messages for summarizing a chat into a short title."""
    lines = []
    for m in messages[-6:]:
        role = str(getattr(getattr(m, "role", None), "value", getattr(m, "role", "")) or "")
        content = _strip_minder_preamble(str(getattr(m, "content", "") or "")).strip()
        if not content or role not in ("user", "assistant"):
            continue
        lines.append(f"{role}: {content[:300]}")
    convo = "\n".join(lines) or "(empty conversation)"
    return [
        {
            "role": "user",
            "content": (
                "Summarize this warehouse-assistant conversation into a short "
                "title of at most 50 characters, in the same language the user "
                "wrote in. Reply with the title only — no quotes, no period.\n\n"
                + convo
            ),
        }
    ]


def _generate_title_sync(messages: list) -> str | None:
    """Call the configured LLM for a title. Returns None on any failure."""
    try:
        from minder.core.agents.components.api.configuration import create_http_client
        from minder.core.runtime import ConfigManager

        cfg = ConfigManager(os.getcwd()).get_config()
        client = create_http_client(cfg)
        payload = {
            "model": cfg.model,
            "messages": _summary_title_prompt(messages),
            "max_tokens": 60,
            "temperature": 0,
        }
        data = client.post_json(payload)
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        text = text.strip().strip('"').strip()
        # Strip qwen-style chat-template artifacts, keep it single-line.
        text = text.split("\n")[0].strip()
        return text[:50] or None
    except Exception:
        return None


@router.post("/{name}/chat/save")
async def module_chat_save(
    name: str,
    body: ChatSaveBody,
    reg: ModuleRegistry = Depends(get_modules_registry),
    service: "ModuleChatService" = Depends(get_module_chat_service),
) -> dict:
    """Store a Minder conversation in the module's workspace project.

    Thin adapter: resolve the module (registry concern) and the workspace name,
    then delegate all DB/session orchestration to :class:`ModuleChatService`.
    Service failures raise :class:`ServiceError` carrying the widget ``kind``;
    we reproduce the exact ``{"kind", "message"}`` payload the widget expects.
    """
    from minder.core.services.errors import ServiceError

    try:
        module = reg.get(name)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail={"kind": "unknown-module", "message": f"module {name!r} not found"},
        ) from None

    manifest = getattr(module, "manifest", None)
    workspace_name = (getattr(manifest, "display_name", None) or name.capitalize()).strip()

    try:
        return await service.save_chat(
            workspace_name=workspace_name,
            chat_session_id=body.chat_session_id,
            create_workspace=body.create_workspace,
            context_session_id=body.context_session_id,
            user_id=body.user_id,
            generate_title=_generate_title_sync,
            strip_preamble=_strip_minder_preamble,
        )
    except ServiceError as exc:
        raise HTTPException(
            status_code=exc.status,
            detail={"kind": getattr(exc, "kind", "save-failed"), "message": exc.detail},
        ) from exc


# ── Virtual platform assets ─────────────────────────────────────────────────

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "dashboard_assets"

_VIRTUAL_MIME = {
    "__bridge.js": "application/javascript; charset=utf-8",
    "__base.css": "text/css; charset=utf-8",
}


def _err(status: int, kind: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"kind": kind, "message": message})


def _serve_asset(rel: str, mime: str) -> Response:
    p = (_ASSETS_DIR / rel).resolve()
    try:
        p.relative_to(_ASSETS_DIR)
    except ValueError:
        raise _err(404, "not-found", "asset not found") from None
    if not p.is_file():
        raise _err(404, "not-found", "asset not found")
    return Response(
        content=p.read_bytes(),
        media_type=mime,
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/{name}/__bridge.js")
def serve_bridge(name: str) -> Response:
    return _serve_asset("__bridge.js", _VIRTUAL_MIME["__bridge.js"])


@router.get("/{name}/__base.css")
def serve_base_css(name: str) -> Response:
    return _serve_asset("__base.css", _VIRTUAL_MIME["__base.css"])


@router.get("/{name}/__vendor/{lib}/{filename:path}")
def serve_vendor(name: str, lib: str, filename: str) -> Response:
    rel = f"vendor/{lib}/{filename}"
    mime, _ = mimetypes.guess_type(filename)
    if mime is None:
        mime = "application/octet-stream"
    return _serve_asset(rel, mime)


# ── Module-owned physical files ─────────────────────────────────────────────


def _serve_module_file(reg: ModuleRegistry, name: str, rel: str) -> Response:
    try:
        data = _store.read_file(reg.root, name, rel)
    except InvalidModuleName as exc:
        raise _err(400, "invalid-module-name", str(exc)) from None
    except ModuleNotFound:
        raise _err(404, "unknown-module", f"module {name!r} not found") from None
    except FileNotFoundError:
        raise _err(404, "not-found", "file not found") from None
    except ValueError as exc:
        raise _err(400, "path-escape", str(exc)) from None
    mime, _ = mimetypes.guess_type(rel)
    if mime is None:
        mime = "application/octet-stream"
    return Response(content=data, media_type=mime, headers={"Cache-Control": "no-cache"})


@router.get("/{name}/dashboard.html")
def serve_dashboard_html(
    name: str, reg: ModuleRegistry = Depends(get_modules_registry)
) -> Response:
    return _serve_module_file(reg, name, "dashboard.html")


@router.get("/{name}/icon.svg")
def serve_icon_svg(name: str, reg: ModuleRegistry = Depends(get_modules_registry)) -> Response:
    return _serve_module_file(reg, name, "icon.svg")


@router.get("/{name}/blocks/{filename:path}")
def serve_block_file(
    name: str, filename: str, reg: ModuleRegistry = Depends(get_modules_registry)
) -> Response:
    return _serve_module_file(reg, name, f"blocks/{filename}")


@router.get("/{name}/vendor/{filename:path}")
def serve_module_vendor(
    name: str, filename: str, reg: ModuleRegistry = Depends(get_modules_registry)
) -> Response:
    return _serve_module_file(reg, name, f"vendor/{filename}")
