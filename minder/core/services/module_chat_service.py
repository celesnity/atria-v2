"""Business logic for persisting a module (Minder) chat into a workspace project.

Owns the session/user resolution, project ensure-or-create, conversation
re-parenting, and LLM title generation that saving a module chat requires. The
route is a thin adapter: it resolves the module from the registry, calls
:meth:`ModuleChatService.save_chat`, and returns the result verbatim.

Transport-free by design — no imports from ``minder.web`` and no
``HTTPException``. Failures raise :class:`ServiceError`; the ``kind`` used by
the widget protocol is carried on the exception so the route can reproduce the
exact error payload.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from minder.core.services.errors import ServiceError
from minder.core.workspace.manager import ensure_path, project_path, slugify
from minder.db.repositories.conversation_repo import ConversationRepository
from minder.db.repositories.project_repo import ProjectRepository
from minder.db.repositories.user_repo import UserRepository


def _service_error(status: int, kind: str, message: str) -> ServiceError:
    """Build a :class:`ServiceError` that also carries the widget ``kind``."""
    err = ServiceError(status, message)
    err.kind = kind  # type: ignore[attr-defined]
    return err


class ModuleChatService:
    """Use case: store a Minder conversation in the module's workspace project."""

    def __init__(self, sessionmaker: Any, session_manager: Any = None) -> None:
        self._sessionmaker = sessionmaker
        self._sessions = session_manager

    async def save_chat(
        self,
        *,
        workspace_name: str,
        chat_session_id: str,
        create_workspace: bool = False,
        context_session_id: str | None = None,
        user_id: int | None = None,
        generate_title: Callable[[list], str | None],
        strip_preamble: Callable[[str], str],
    ) -> dict:
        """Persist the chat, ensuring/creating its workspace project.

        ``workspace_name`` is the module's display name (resolved by the route
        from the registry). ``generate_title`` and ``strip_preamble`` are the
        route's title helpers, injected so this service stays web-free.
        """
        sm = self._sessions
        try:
            try:
                session = await sm.get_session_by_id(chat_session_id)
            except FileNotFoundError:
                raise _service_error(
                    404,
                    "unknown-session",
                    f"session {chat_session_id!r} not found",
                ) from None

            # Resolve the owning user: browser user (via /run) wins, then the
            # session's owner, then the caller's context session.
            resolved_user_id = int(user_id) if user_id else None
            for candidate in (getattr(session, "owner_id", None), context_session_id):
                if resolved_user_id is not None:
                    break
                if candidate is None:
                    continue
                if str(candidate).isdigit():
                    resolved_user_id = int(candidate)
                else:
                    try:
                        ctx = await sm.get_session_by_id(str(candidate))
                        if ctx is not None and str(ctx.owner_id or "").isdigit():
                            resolved_user_id = int(ctx.owner_id)
                    except FileNotFoundError:
                        pass
            if resolved_user_id is None:
                raise _service_error(400, "no-user", "cannot resolve the conversation's owner")

            db = self._sessionmaker
            project_repo = ProjectRepository(db)
            projects = await project_repo.list_by_user(resolved_user_id)
            target = next(
                (
                    p
                    for p in projects
                    if str(p.get("title", "")).strip().lower() == workspace_name.lower()
                ),
                None,
            )

            if target is None:
                if not create_workspace:
                    return {"ok": False, "needs_workspace": True, "workspace_name": workspace_name}
                user_row = await UserRepository(db).get_by_id(resolved_user_id)
                email = str(user_row["email"]) if user_row else f"user-{resolved_user_id}"
                user_slug = slugify(email.split("@")[0])
                path = project_path(user_slug, workspace_name)
                ensure_path(path)
                project_id = await project_repo.create(
                    user_id=resolved_user_id, title=workspace_name, workspace_path=str(path)
                )
            else:
                project_id = int(target["id"])

            conv_repo = ConversationRepository(db)
            await conv_repo.set_project(int(chat_session_id), project_id)

            # LLM title with heuristic fallback (first user message, 50 chars).
            loop = asyncio.get_event_loop()
            messages = list(getattr(session, "messages", None) or [])
            title = await loop.run_in_executor(None, generate_title, messages)
            if not title:
                last_user = next(
                    (
                        strip_preamble(str(getattr(m, "content", "") or ""))
                        for m in reversed(messages)
                        if str(
                            getattr(getattr(m, "role", None), "value", getattr(m, "role", "")) or ""
                        )
                        == "user"
                    ),
                    "",
                )
                title = (last_user.strip()[:50] or f"{workspace_name} chat").strip()
            await sm.set_title(chat_session_id, title)

            return {
                "ok": True,
                "workspace": workspace_name,
                "title": title,
                "project_id": project_id,
                "session_id": chat_session_id,
            }
        except ServiceError:
            raise
        except Exception as exc:
            import logging

            logging.getLogger("minder.web").exception("module chat save failed")
            raise _service_error(500, "save-failed", f"{type(exc).__name__}: {exc}") from exc
