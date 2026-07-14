"""Core functionality for Minder."""

import os
import warnings
from importlib import import_module
from typing import Dict, Tuple

# Suppress transformers warning about missing ML frameworks
# Minder uses LLM APIs directly and doesn't need local models
os.environ["TRANSFORMERS_VERBOSITY"] = "error"  # Only show errors, not warnings
warnings.filterwarnings("ignore", message=".*None of PyTorch, TensorFlow.*found.*")
warnings.filterwarnings("ignore", message=".*Models won't be available.*")

__all__ = [
    "ConfigManager",
    "SessionManager",
    "MainAgent",
    "ModeManager",
    "OperationMode",
    "ApprovalManager",
    "ApprovalChoice",
    "ApprovalResult",
    "ErrorHandler",
    "ErrorAction",
    "UndoManager",
    "ToolRegistry",
]

_EXPORTS: Dict[str, Tuple[str, str]] = {
    "MainAgent": ("minder.core.agents", "MainAgent"),
    "ConfigManager": ("minder.core.runtime", "ConfigManager"),
    "SessionManager": ("minder.core.context_engineering.history", "SessionManager"),
    "ModeManager": ("minder.core.runtime", "ModeManager"),
    "OperationMode": ("minder.core.runtime", "OperationMode"),
    "UndoManager": ("minder.core.context_engineering.history", "UndoManager"),
    "ApprovalManager": ("minder.core.runtime.approval", "ApprovalManager"),
    "ApprovalChoice": ("minder.core.runtime.approval", "ApprovalChoice"),
    "ApprovalResult": ("minder.core.runtime.approval", "ApprovalResult"),
    "ErrorHandler": ("minder.core.runtime.monitoring", "ErrorHandler"),
    "ErrorAction": ("minder.core.runtime.monitoring", "ErrorAction"),
    "ToolRegistry": ("minder.core.context_engineering.tools", "ToolRegistry"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module 'minder.core' has no attribute '{name}'")
    module_path, attr_name = _EXPORTS[name]
    module = import_module(module_path)
    attr = getattr(module, attr_name)
    globals()[name] = attr
    return attr
