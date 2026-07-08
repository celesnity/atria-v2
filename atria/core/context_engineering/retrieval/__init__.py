"""Information retrieval for Atria.

Provides token monitoring for context compaction. (Codebase indexing and
regex/grep context retrieval were unused and moved to _local/dead-code.)
"""

from atria.core.context_engineering.retrieval.token_monitor import ContextTokenMonitor

__all__ = ["ContextTokenMonitor"]
