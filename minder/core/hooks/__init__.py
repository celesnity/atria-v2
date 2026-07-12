"""Hooks system for Minder CLI.

Provides lifecycle hooks that fire shell commands at key events
(tool execution, session start/end, compaction, etc.). Users configure
hooks in settings.json with regex matchers to filter which events
trigger which commands.
"""

from minder.core.hooks.models import HookEvent, HookCommand, HookMatcher, HookConfig
from minder.core.hooks.executor import HookResult, HookCommandExecutor
from minder.core.hooks.manager import HookOutcome, HookManager
from minder.core.hooks.loader import load_hooks_config

__all__ = [
    "HookEvent",
    "HookCommand",
    "HookMatcher",
    "HookConfig",
    "HookResult",
    "HookCommandExecutor",
    "HookOutcome",
    "HookManager",
    "load_hooks_config",
]
