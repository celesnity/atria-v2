"""Runtime-toggleable disabled-tool set for the LLM tool schema list.

Each tool schema costs tokens on EVERY request (the full ``tools`` array is
resent per call), so dropping unused tools reclaims context. Historically this
was a hard-coded frozenset in :mod:`normal_builder`; it is now a *dynamic* set
read from user settings so the web UI can toggle tools on/off without a restart.

Resolution (mirrors :func:`atria.core.modules.registry.load_disabled_modules`):

* The web UI persists a ``disabled_tools`` list into ``~/.atria/settings.json``.
* If that key is **present**, it is the source of truth (even when ``[]`` — an
  explicit "nothing disabled").
* If the key is **absent**, we fall back to :data:`DEFAULT_DISABLED_TOOLS` so a
  fresh install keeps today's behavior (web/subagents/todos/... stay off).
* The ``ATRIA_DISABLED_TOOLS`` env var is always unioned in, as a no-UI escape
  hatch and for parity with the modules pattern.

The set is read fresh on every :meth:`ToolSchemaBuilder.build` call (i.e. every
LLM request), so a toggle in the UI takes effect on the very next turn.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from atria.core.paths import get_paths

logger = logging.getLogger(__name__)

# Seed defaults — the tools this deployment historically shipped with disabled.
# Used only until the UI writes an explicit ``disabled_tools`` list. Keep in sync
# with the groups below when adding new always-off-by-default tools.
DEFAULT_DISABLED_TOOLS: frozenset[str] = frozenset(
    {
        # Web / browser / media. NOTE: send_image / send_editable_table /
        # send_table are intentionally NOT disabled — the data_copilot analytics
        # flow pushes charts and result/editable tables to the web chat with them.
        "fetch_url",
        "browser",
        "capture_web_screenshot",
        "web_search",
        "analyze_image",
        "render_component",
        "capture_screenshot",
        "open_browser",
        # Code symbol tools + notebook
        "find_symbol",
        "rename_symbol",
        "find_referencing_symbols",
        "replace_symbol_body",
        "insert_after_symbol",
        "insert_before_symbol",
        "notebook_edit",
        # Subagents — this deployment does not spawn or manage subagents.
        "spawn_subagent",
        "list_subagents",
        "list_agents",
        "get_subagent_output",
        # Uploaded-image artifacts — users don't upload images here.
        "list_artifact_images",
        "read_artifact_image",
        # Todo tracking — not used in this deployment.
        "write_todos",
        "update_todo",
        "complete_todo",
        "list_todos",
        "clear_todos",
        # Parallel-solve dispatch — off by default in this deployment.
        "solve",
        "get_solve_result",
        # Memory tools — off by default in this deployment.
        "memory_search",
        "memory_write",
    }
)


def _env_disabled() -> set[str]:
    """Parse ``ATRIA_DISABLED_TOOLS`` (comma/whitespace separated) into a set."""
    raw = os.environ.get("ATRIA_DISABLED_TOOLS", "")
    return {tok for tok in raw.replace(",", " ").split() if tok}


def load_disabled_tools() -> set[str]:
    """Return the effective set of tool names to strip from the schema list.

    Reads the global ``~/.atria/settings.json`` on every call (the file is tiny
    and this runs once per LLM request). Falls back to :data:`DEFAULT_DISABLED_TOOLS`
    when the ``disabled_tools`` key is absent or the file cannot be read.
    """
    env = _env_disabled()
    try:
        settings_path = get_paths().global_settings
        if settings_path.exists():
            raw = settings_path.read_text().strip()
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict) and "disabled_tools" in data:
                    value = data["disabled_tools"]
                    if isinstance(value, list):
                        return {str(t) for t in value} | env
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to read disabled_tools from settings, using defaults: %s", e)
    return set(DEFAULT_DISABLED_TOOLS) | env


# ── Tool metadata for the settings UI ──────────────────────────────────────────

# name -> category, derived from the builtin schema sub-modules so the UI can
# group tools the same way the codebase does.
def _build_category_map() -> dict[str, str]:
    from atria.core.agents.components.schemas.builtin import (
        agent_tools,
        artifact_tools,
        browser_media_tools,
        component_tools,
        file_tools,
        interaction_tools,
        knowledge_tools,
        orchestration_tools,
        process_tools,
        symbol_tools,
        system_tools,
        web_tools,
    )

    groups: list[tuple[str, Any]] = [
        ("File", file_tools),
        ("Process", process_tools),
        ("Web", web_tools),
        ("Interaction", interaction_tools),
        ("Browser & Media", browser_media_tools),
        ("System", system_tools),
        ("Code Symbols", symbol_tools),
        ("Knowledge", knowledge_tools),
        ("Agents", agent_tools),
        ("Orchestration", orchestration_tools),
        ("Artifacts", artifact_tools),
        ("Components", component_tools),
    ]
    mapping: dict[str, str] = {}
    for label, module in groups:
        for schema in getattr(module, "SCHEMAS", []):
            name = schema.get("function", {}).get("name")
            if name:
                mapping[name] = label
    return mapping


def all_builtin_tool_meta() -> list[dict[str, str]]:
    """List every built-in tool as ``{name, description, category}`` for the UI.

    ``description`` is trimmed to its first non-empty line to keep the payload and
    the settings list compact.
    """
    from atria.core.agents.components.schemas.definitions import _BUILTIN_TOOL_SCHEMAS

    categories = _build_category_map()
    meta: list[dict[str, str]] = []
    for schema in _BUILTIN_TOOL_SCHEMAS:
        fn = schema.get("function", {})
        name = fn.get("name")
        if not name:
            continue
        desc = (fn.get("description") or "").strip()
        first_line = next((ln.strip() for ln in desc.splitlines() if ln.strip()), "")
        meta.append(
            {
                "name": name,
                "description": first_line,
                "category": categories.get(name, "Other"),
            }
        )
    return meta
