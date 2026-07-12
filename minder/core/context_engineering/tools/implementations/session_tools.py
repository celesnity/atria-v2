"""Session inspection tools — list active subagents."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SessionTools:
    """Inspect active subagents."""

    def list_subagents(
        self,
        subagent_manager: Any,
    ) -> dict[str, Any]:
        """List active and recent subagents with status.

        Args:
            subagent_manager: SubAgentManager instance

        Returns:
            Result dict with subagent list
        """
        if not subagent_manager:
            return {
                "success": True,
                "output": "No subagent manager configured. No subagents are running.",
                "subagents": [],
            }

        try:
            # Check if manager tracks background tasks
            subagents = []
            if hasattr(subagent_manager, "get_active_tasks"):
                tasks = subagent_manager.get_active_tasks()
                for task in tasks:
                    subagents.append(
                        {
                            "id": task.get("id", "unknown"),
                            "status": task.get("status", "unknown"),
                            "description": task.get("description", ""),
                            "type": task.get("type", "general-purpose"),
                        }
                    )

            if not subagents:
                return {
                    "success": True,
                    "output": "No active subagents.",
                    "subagents": [],
                }

            output_parts = [f"Active subagents ({len(subagents)}):\n"]
            for sa in subagents:
                output_parts.append(
                    f"  [{sa['id'][:8]}] {sa['type']} — {sa['status']}: {sa['description']}"
                )

            return {
                "success": True,
                "output": "\n".join(output_parts),
                "subagents": subagents,
            }
        except Exception as e:
            logger.error("Failed to list subagents: %s", e, exc_info=True)
            return {"success": False, "error": f"Failed to list subagents: {e}", "output": None}
