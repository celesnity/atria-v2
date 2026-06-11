"""Runtime subsystem for Atria.

This package manages runtime/operational concerns:
- config.py: Configuration management
- mode_manager.py: Operation modes (PLAN, EXECUTE, etc.)
- approval/: User approval workflows
- monitoring/: Error handling and task tracking
- services/: High-level service orchestration
"""

from atria.core.runtime.config import ConfigManager
from atria.core.runtime.mode_manager import ModeManager, OperationMode

__all__ = [
    "ConfigManager",
    "ModeManager",
    "OperationMode",
]
