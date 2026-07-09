"""FastAPI providers that construct application services.

Each provider assembles a service from the shared sessionmaker and runtime
state, so routes depend on the service (an abstraction) rather than reaching
into the database connection or the global state singleton themselves.
"""

from __future__ import annotations

from atria.core.services.artifact_service import ArtifactService
from atria.core.services.conversation_service import ConversationService
from atria.core.services.module_chat_service import ModuleChatService
from atria.core.services.project_service import ProjectService
from atria.db.connection import get_sessionmaker
from atria.web.state import get_state


async def get_project_service() -> ProjectService:
    sm = await get_sessionmaker()
    return ProjectService(sm, get_state().session_manager)


async def get_conversation_service() -> ConversationService:
    sm = await get_sessionmaker()
    return ConversationService(sm)


async def get_artifact_service() -> ArtifactService:
    sm = await get_sessionmaker()
    return ArtifactService(sm)


async def get_module_chat_service() -> ModuleChatService:
    sm = await get_sessionmaker()
    return ModuleChatService(sm, get_state().session_manager)
