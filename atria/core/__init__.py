"""Core functionality for Atria."""

import os
import warnings
from importlib import import_module
from typing import Dict, Tuple

# Suppress transformers warning about missing ML frameworks
# Atria uses LLM APIs directly and doesn't need local models
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
    "MainAgent": ("atria.core.agents", "MainAgent"),
    "ConfigManager": ("atria.core.runtime", "ConfigManager"),
    "SessionManager": ("atria.core.context_engineering.history", "SessionManager"),
    "ModeManager": ("atria.core.runtime", "ModeManager"),
    "OperationMode": ("atria.core.runtime", "OperationMode"),
    "UndoManager": ("atria.core.context_engineering.history", "UndoManager"),
    "ApprovalManager": ("atria.core.runtime.approval", "ApprovalManager"),
    "ApprovalChoice": ("atria.core.runtime.approval", "ApprovalChoice"),
    "ApprovalResult": ("atria.core.runtime.approval", "ApprovalResult"),
    "ErrorHandler": ("atria.core.runtime.monitoring", "ErrorHandler"),
    "ErrorAction": ("atria.core.runtime.monitoring", "ErrorAction"),
    "ToolRegistry": ("atria.core.context_engineering.tools", "ToolRegistry"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module 'atria.core' has no attribute '{name}'")
    module_path, attr_name = _EXPORTS[name]
    module = import_module(module_path)
    attr = getattr(module, attr_name)
    globals()[name] = attr
    return attr
