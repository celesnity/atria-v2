"""Base/foundation layer for Atria.

This package provides foundational components:
- abstract/: Base classes defining shared behavior
- interfaces/: Protocol definitions for loose coupling
- exceptions/: Custom exception hierarchy
- factories/: Object construction patterns
"""

# Re-export commonly used base classes
from atria.core.base.abstract import BaseAgent

__all__ = [
    "BaseAgent",
]
