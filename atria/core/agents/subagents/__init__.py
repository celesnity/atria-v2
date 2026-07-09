"""SubAgent infrastructure for task delegation."""

from .specs import SubAgentSpec, CompiledSubAgent
from .manager import SubAgentManager
from .task_tool import create_request_help_schema, REQUEST_HELP_TOOL_NAME
from .agents import ALL_SUBAGENTS

__all__ = [
    "SubAgentSpec",
    "CompiledSubAgent",
    "SubAgentManager",
    "create_request_help_schema",
    "REQUEST_HELP_TOOL_NAME",
    "ALL_SUBAGENTS",
]
