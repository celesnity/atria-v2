"""Session persistence and management."""

from atria.core.context_engineering.history.session_manager.pg_manager import PgSessionManager

# Alias so existing `from ... import SessionManager` imports still work
SessionManager = PgSessionManager

__all__ = ["SessionManager", "PgSessionManager"]
