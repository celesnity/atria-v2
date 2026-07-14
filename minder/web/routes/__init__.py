"""API routes for web UI."""

from minder.web.routes.chat import router as chat_router
from minder.web.routes.sessions import router as sessions_router
from minder.web.routes.config import router as config_router
from minder.web.routes.tools import router as tools_router
from minder.web.routes.commands import router as commands_router
from minder.web.routes.mcp import router as mcp_router
from minder.web.routes.auth import router as auth_router
from minder.web.routes.projects import router as projects_router
from minder.web.routes.artifacts import router as artifacts_router
from minder.web.routes.fs import router as fs_router
from minder.web.routes.personas import router as personas_router
from minder.web.routes.transcribe import router as transcribe_router
from minder.web.routes.modules import router as modules_router
from minder.web.routes.blocks import router as blocks_router
from minder.web.routes.blocks_remote import router as blocks_remote_router
from minder.web.routes.artifacts_remote import router as artifacts_remote_router
from minder.web.routes.module_dashboard import router as module_dashboard_router
from minder.web.routes.module_connector import router as module_connector_router
from minder.web.routes.connect import router as connect_router
from minder.web.routes.me import router as me_router
from minder.web.routes.admin_tenants import router as admin_tenants_router
from minder.web.routes.admin_tenant_users import (
    router as admin_tenant_users_router,
    invites_router as admin_tenant_invites_router,
)

__all__ = [
    "connect_router",
    "chat_router",
    "sessions_router",
    "config_router",
    "tools_router",
    "commands_router",
    "mcp_router",
    "auth_router",
    "projects_router",
    "artifacts_router",
    "fs_router",
    "personas_router",
    "transcribe_router",
    "modules_router",
    "blocks_router",
    "blocks_remote_router",
    "artifacts_remote_router",
    "module_dashboard_router",
    "module_connector_router",
    "me_router",
    "admin_tenants_router",
    "admin_tenant_users_router",
    "admin_tenant_invites_router",
]
