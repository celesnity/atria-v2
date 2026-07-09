"""Skill tools for the maps_search module: user profile lookup."""

from __future__ import annotations

import json
from typing import Any

from atria.core.context_engineering.search import pg
from atria.core.skill_tools import SkillToolContext, ToolSpec


def _get_user_profile(user_id: str, **_ignored: Any) -> dict[str, Any]:
    """Fetch a map user's stored profile row.

    Args:
        user_id: Profile id in the Track 8 dataset, e.g. 'U001'.
        **_ignored: Extra keyword arguments the tool caller may pass;
            accepted and discarded so the handler tolerates a wider call
            signature than it strictly needs.

    Returns:
        On success, `{"success": True, "output": <JSON string of the
        profile row>}`. When no profile exists for `user_id`,
        `{"success": False, "error": <message>, "output": None}`.
    """
    rows = pg.fetch_all("SELECT * FROM map_user_profiles WHERE user_id = $1", [user_id])
    if not rows:
        return {"success": False, "error": f"No profile for user {user_id!r}", "output": None}
    return {"success": True, "output": json.dumps(rows[0], ensure_ascii=False)}


def register(ctx: SkillToolContext | None) -> list[ToolSpec]:
    """Skill-tool entry point for the maps_search module.

    Args:
        ctx: Cross-cutting services shared across skill tools. Unused by
            this module — profile lookup needs no runtime services — so
            `None` (as passed by tests, or by a minimal host) is accepted.

    Returns:
        A single-element list containing the `get_user_profile` ToolSpec.
    """
    return [
        ToolSpec(
            name="get_user_profile",
            description=(
                "Fetch a map user's stored profile (persona, current_location, preferences, "
                "avoid, budget_level). Use it to personalize place searches: fold preferences "
                "into the knowledge_search query and respect the avoid list."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "Profile id, e.g. 'U001'."}
                },
                "required": ["user_id"],
            },
            handler=_get_user_profile,
        )
    ]
