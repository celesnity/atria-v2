"""History management for Minder.

Manages session state and undo/redo functionality.
"""

from minder.core.context_engineering.history.session_manager import SessionManager
from minder.core.context_engineering.history.topic_detector import TopicDetector
from minder.core.context_engineering.history.undo_manager import UndoManager

__all__ = [
    "SessionManager",
    "TopicDetector",
    "UndoManager",
]
