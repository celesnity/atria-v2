"""Factory helpers for assembling agent instances."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from minder.core.agents import MainAgent
from minder.core.base.interfaces import AgentInterface, ToolRegistryInterface
from minder.core.runtime import ModeManager
from minder.models.config import AppConfig

if TYPE_CHECKING:
    from minder.core.skills import SkillLoader
    from minder.core.runtime.config import ConfigManager

logger = logging.getLogger(__name__)


@dataclass
class AgentSuite:
    """Agent suite for runtime."""

    normal: AgentInterface
    assistant: AgentInterface | None = None
    skill_loader: "SkillLoader | None" = None


class AgentFactory:
    """Creates conversational agents bound to a shared mode manager and tools."""

    def __init__(
        self,
        config: AppConfig,
        tool_registry: ToolRegistryInterface,
        mode_manager: ModeManager,
        working_dir: Any = None,
        config_manager: "ConfigManager | None" = None,
        env_context: Any = None,
    ) -> None:
        self._config = config
        self._tool_registry = tool_registry
        self._mode_manager = mode_manager
        self._working_dir = working_dir
        self._config_manager = config_manager
        self._env_context = env_context
        self._skill_loader: "SkillLoader | None" = None

    def create_agents(self) -> AgentSuite:
        """Instantiate both normal and planning agents.

        Also initializes the skills system if skill directories exist.
        """
        # Initialize skills system
        self._initialize_skills()

        # Create main agent
        normal = MainAgent(
            self._config,
            self._tool_registry,
            self._mode_manager,
            self._working_dir,
            env_context=self._env_context,
        )

        from minder.core.agents.assistant_agent import AssistantAgent

        assistant = AssistantAgent(
            self._config,
            self._tool_registry,
            self._mode_manager,
            self._working_dir,
            env_context=self._env_context,
        )

        return AgentSuite(
            normal=normal,
            assistant=assistant,
            skill_loader=self._skill_loader,
        )

    def _initialize_skills(self) -> None:
        """Initialize the skills system from configured directories."""
        if not self._config_manager:
            return

        try:
            from minder.core.skills import SkillLoader

            skill_dirs = self._config_manager.get_skill_dirs()
            if skill_dirs:
                self._skill_loader = SkillLoader(skill_dirs)
                # Pre-discover skills for the index
                skills = self._skill_loader.discover_skills()
                if skills:
                    logger.info(
                        f"Discovered {len(skills)} skills from {len(skill_dirs)} directories"
                    )
                # Register with tool registry
                self._tool_registry.set_skill_loader(self._skill_loader)
        except ImportError:
            logger.debug("Skills module not available")
        except Exception as e:
            logger.warning(f"Failed to initialize skills system: {e}")

    def refresh_tools(self, suite: AgentSuite) -> None:
        """Refresh tool metadata for the agent."""
        if hasattr(suite.normal, "refresh_tools"):
            suite.normal.refresh_tools()
        if suite.assistant is not None and hasattr(suite.assistant, "refresh_tools"):
            suite.assistant.refresh_tools()
