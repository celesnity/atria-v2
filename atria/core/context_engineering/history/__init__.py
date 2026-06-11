"""History management for Atria.

Manages session state and undo/redo functionality.
"""

from atria.core.context_engineering.history.session_manager import SessionManager
from atria.core.context_engineering.history.topic_detector import TopicDetector
from atria.core.context_engineering.history.undo_manager import UndoManager

__all__ = [
    "SessionManager",
    "TopicDetector",
    "UndoManager",
]
