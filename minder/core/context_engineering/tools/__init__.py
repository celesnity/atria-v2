"""Tool subsystem for Minder core.

This package contains:
- implementations/: Low-level tool implementations (BashTool, EditTool, etc.)
- handlers/: High-level handlers that wrap implementations and add orchestration logic
- registry.py: ToolRegistry that dispatches tool calls to handlers
- context.py: ToolExecutionContext for passing dependencies to handlers
"""

from .context import ToolExecutionContext
from .registry import ToolRegistry

# Re-export implementations for convenience
from .implementations import (
    BaseTool,
    BashTool,
    Diff,
    DiffPreview,
    FileOperations,
    VLMTool,
)

# Re-export handlers for convenience
from .handlers import (
    ProcessToolHandler,
    TodoHandler,
    TodoItem,
)

__all__ = [
    # Core
    "ToolExecutionContext",
    "ToolRegistry",
    # Implementations
    "BaseTool",
    "BashTool",
    "Diff",
    "DiffPreview",
    "FileOperations",
    "VLMTool",
    # Handlers
    "ProcessToolHandler",
    "TodoHandler",
    "TodoItem",
]
