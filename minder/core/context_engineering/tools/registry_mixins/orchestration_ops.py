"""Unified ``subagent`` fan-out orchestration for the tool registry."""

from __future__ import annotations

from typing import Any


class OrchestrationOpsMixin:
    """Lazily-built subagent orchestrator and its two tool handlers."""

    def _get_repo_dir(self) -> str:
        """Return the run's repo/working directory, defaulting to '.'."""
        return (
            str(self.file_ops.working_dir)
            if self.file_ops and getattr(self.file_ops, "working_dir", None)
            else "."
        )

    def _get_subagent_orchestrator(self, context: Any = None) -> Any:
        """Build (once per run) the SubagentOrchestrator from this run's context.

        Requires the run's TaskIQClient (attached to the subagent manager via
        ``attach_task_client``). Returns None when no task client is available —
        subagent delegation needs a running worker + Redis.
        """
        if getattr(self, "_subagent_orchestrator", None) is not None:
            return self._subagent_orchestrator
        mgr = self._subagent_manager
        task_client = getattr(mgr, "_task_client", None) if mgr is not None else None
        if task_client is None:
            return None

        from minder.core.context_engineering.tools.implementations.session_resolve import (
            resolve_session,
        )
        from minder.core.subagents.tools import build_subagent_orchestrator

        ui_callback = getattr(context, "ui_callback", None) if context else None
        progress_cb = None
        if ui_callback is not None and hasattr(ui_callback, "on_solver_event"):
            progress_cb = lambda stage, data: ui_callback.on_solver_event(  # noqa: E731
                "subagent", stage, data
            )

        session_id, working_dir = resolve_session(context)
        session_id = session_id or ""
        working_dir = working_dir or self._get_repo_dir()
        _sess_mgr = getattr(context, "session_manager", None) if context else None
        _current = getattr(_sess_mgr, "current_session", None) if _sess_mgr else None
        owner_id = (getattr(_current, "owner_id", None) or "") if _current else ""

        # Bid pool = every helper (incl. dynamically-registered module workers),
        # profiled by its capability_profile or, failing that, its description.
        # ask-user is a builtin UI action, never a volunteer.
        profiles: list[tuple[str, str]] = []
        if mgr is not None:
            for c in mgr.get_agent_configs():
                if c.name == "ask-user":
                    continue
                p = getattr(c, "capability_profile", None) or getattr(c, "description", None)
                if p:
                    profiles.append((c.name, p))

        self._subagent_orchestrator = build_subagent_orchestrator(
            task_client=task_client,
            config=self._app_config,
            owner_id=owner_id,
            session_id=session_id,
            working_dir=str(working_dir),
            progress_cb=progress_cb,
            helper_profiles=profiles,
        )
        return self._subagent_orchestrator

    def _execute_request_help(
        self, arguments: dict[str, Any], context: Any = None
    ) -> dict[str, Any]:
        """Dispatch the ``request_help`` tool: post a request + bid it out."""
        orch = self._get_subagent_orchestrator(context)
        if orch is None:
            return {
                "success": False,
                "error": "Help requests unavailable (no task client). "
                "Requires a running TaskIQ worker + Redis.",
                "output": None,
            }
        from minder.core.subagents.tools import execute_request_help

        return execute_request_help(arguments, orch)

    def _execute_get_help_responses(
        self, arguments: dict[str, Any], context: Any = None
    ) -> dict[str, Any]:
        """Dispatch ``get_help_responses``: collect responses + bids + notes digest."""
        orch = self._get_subagent_orchestrator(context)
        if orch is None:
            return {
                "success": False,
                "error": "Help requests unavailable (no task client).",
                "output": None,
            }
        from minder.core.subagents.tools import execute_get_help_responses

        return execute_get_help_responses(arguments, orch)
