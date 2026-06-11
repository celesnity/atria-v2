"""API integration layer for Atria agents — OpenAI-compatible endpoint."""

from .base_adapter import ProviderAdapter
from .configuration import (
    build_max_tokens_param,
    build_temperature_param,
    create_http_client,
    resolve_api_config,
)
from .http_client import AgentHttpClient, HttpResult

# Register AgentHttpClient as a virtual subclass of ProviderAdapter.
# AgentHttpClient can't inherit directly because ProviderAdapter imports
# HttpResult from the same module (circular import).
ProviderAdapter.register(AgentHttpClient)

__all__ = [
    "AgentHttpClient",
    "HttpResult",
    "ProviderAdapter",
    "build_max_tokens_param",
    "build_temperature_param",
    "create_http_client",
    "resolve_api_config",
]
