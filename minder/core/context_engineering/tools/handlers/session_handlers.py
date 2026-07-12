"""Handler for session inspection tools."""

from __future__ import annotations

from typing import Any, Union

from minder.core.context_engineering.tools.implementations.session_tools import SessionTools


class SessionToolHandler:
    """Handles the list_subagents tool."""

    def __init__(self) -> None:
        self._tools = SessionTools()
        self._subagent_manager: Union[Any, None] = None

    def set_subagent_manager(self, manager: Any) -> None:
        """Set the subagent manager reference."""
        self._subagent_manager = manager

    def list_subagents(self, arguments: dict[str, Any], context: Any = None) -> dict[str, Any]:
        """Execute list_subagents tool."""
        return self._tools.list_subagents(subagent_manager=self._subagent_manager)
