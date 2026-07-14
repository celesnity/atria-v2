"""Business logic for conversation lookups shared by the filesystem routes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from minder.core.services.errors import ServiceError
from minder.db.repositories.conversation_repo import ConversationRepository


class ConversationService:
    """Use cases that resolve conversation-scoped data."""

    def __init__(self, sessionmaker: Any) -> None:
        self._conversations = ConversationRepository(sessionmaker)

    async def working_dir(self, conversation_id: int) -> Path:
        """Return the conversation's working directory, verifying it exists."""
        conv = await self._conversations.get_by_id(conversation_id)
        if not conv:
            raise ServiceError.not_found("Conversation not found")
        wd = conv["working_directory"]
        if not wd or not os.path.isdir(wd):
            raise ServiceError.not_found("Working directory missing")
        return Path(wd)
