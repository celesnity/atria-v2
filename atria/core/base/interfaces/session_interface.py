"""Async session manager interface."""

from __future__ import annotations

from typing import Optional, Protocol, Sequence

from atria.models.message import ChatMessage
from atria.models.session import Session, SessionMetadata


class SessionManagerInterface(Protocol):
    """Async protocol all session manager implementations must satisfy."""

    current_session: Optional[Session]
    turn_count: int

    async def create_session(
        self,
        working_directory: Optional[str] = None,
        channel: str = "cli",
        channel_user_id: str = "",
        **kwargs: object,
    ) -> Session: ...

    async def load_session(self, session_id: str, owner_id: Optional[str] = None) -> Session: ...

    async def save_session(
        self, session: Optional[Session] = None, force: bool = False
    ) -> None: ...

    async def add_message(self, message: ChatMessage, auto_save_interval: int = 5) -> None: ...

    async def list_sessions(
        self, owner_id: Optional[str] = None, include_archived: bool = False
    ) -> Sequence[SessionMetadata]: ...

    async def list_all_sessions(
        self,
        include_archived: bool = False,
        owner_id: Optional[str] = None,
        include_unowned: bool = True,
    ) -> Sequence[SessionMetadata]: ...

    async def delete_session(self, session_id: str) -> None: ...

    async def get_current_session(self) -> Optional[Session]: ...

    async def get_session_by_id(
        self, session_id: str, owner_id: Optional[str] = None
    ) -> Session: ...

    async def set_title(self, session_id: str, title: str) -> None: ...

    async def load_latest_session(self, working_directory: object = None) -> Optional[Session]: ...

    async def find_latest_session(
        self, working_directory: object = None
    ) -> Optional[SessionMetadata]: ...

    async def fork_session(self, message_index: Optional[int] = None) -> Optional[Session]: ...

    async def load_transcript(self, session_id: str) -> list[ChatMessage]: ...

    async def find_session_by_channel_user(
        self, channel: str, user_id: str, thread_id: Optional[str] = None
    ) -> Optional[SessionMetadata]: ...

    async def list_user_workspaces(self) -> list[str]: ...
