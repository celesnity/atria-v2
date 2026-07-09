"""Subagent specifications."""

from .ask_user import ASK_USER_SUBAGENT
from .planner import PLANNER_SUBAGENT
from .module_worker import MODULE_WORKER_SUBAGENT
from .web_generator import WEB_GENERATOR_SUBAGENT

ALL_SUBAGENTS = [
    ASK_USER_SUBAGENT,
    PLANNER_SUBAGENT,
    MODULE_WORKER_SUBAGENT,
    WEB_GENERATOR_SUBAGENT,
]
