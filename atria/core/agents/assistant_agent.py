"""Assistant deployment agent: conversational, knowledge tools only.

A restricted MainAgent for assistant deployments: the LLM sees only
skill/module tools (knowledge_search, get_user_profile, ...) plus ask_user,
and the system prompt is assistant-first instead of coding-first. Selected
via the `agent_mode` config field (env: ATRIA_AGENT_MODE=assistant).
"""

from __future__ import annotations

import logging
from typing import Any

from atria.core.agents.main_agent.agent import MainAgent, _build_skill_schemas

logger = logging.getLogger(__name__)

_BASE_TOOLS = ["ask_user"]


def assistant_allowed_tools(tool_registry: Any) -> list[str]:
    """Skill/module tool names plus conversational basics — nothing else.

    Args:
        tool_registry: Registry exposing `get_skill_specs()`.

    Returns:
        Sorted, de-duplicated tool-name allowlist.
    """
    skill_names = [s["function"]["name"] for s in _build_skill_schemas(tool_registry)]
    return sorted(set(skill_names + _BASE_TOOLS))


class AssistantAgent(MainAgent):
    """MainAgent restricted to knowledge tools with an assistant-first prompt."""

    def __init__(
        self,
        config: Any,
        tool_registry: Any,
        mode_manager: Any,
        working_dir: Any = None,
        env_context: Any = None,
    ) -> None:
        super().__init__(
            config,
            tool_registry,
            mode_manager,
            working_dir,
            allowed_tools=assistant_allowed_tools(tool_registry),
            env_context=env_context,
        )
        # allowed_tools makes MainAgent flag itself as a subagent; this is a
        # top-level deployment agent.
        self.is_subagent = False

    def build_system_prompt(self, thinking_visible: bool = False) -> str:
        """Assistant-first prompt: identity template + module SKILL block."""
        from atria.core.agents.prompts.loader import load_prompt

        base = load_prompt("system/assistant")
        try:
            from atria.core.modules.prompt import build_skill_block
            from atria.core.modules.registry import get_registry

            block = build_skill_block(get_registry(), include_subagent_delegation=False)
        except Exception as exc:  # modules must never break agent construction
            logger.warning("Failed to build module SKILL block for assistant prompt: %s", exc)
            block = ""
        full = base + ("\n\n" + block if block else "")
        self._system_stable = full
        self._system_dynamic = ""
        return full
