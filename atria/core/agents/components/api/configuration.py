"""Helpers for resolving API endpoints and headers."""

from __future__ import annotations

from typing import Tuple, TYPE_CHECKING

from atria.models.config import AppConfig

if TYPE_CHECKING:
    from atria.core.agents.components.api.base_adapter import ProviderAdapter


# Models that require max_completion_tokens instead of max_tokens
_MAX_COMPLETION_TOKENS_PREFIXES = ("o1", "o3", "o4", "gpt-5")


def uses_max_completion_tokens(model: str) -> bool:
    """Check if a model requires max_completion_tokens instead of max_tokens.

    GPT-5 and O-series models (o1, o3, o4) use max_completion_tokens parameter
    instead of max_tokens for the OpenAI API.

    Args:
        model: The model ID string

    Returns:
        True if the model uses max_completion_tokens
    """
    return model.startswith(_MAX_COMPLETION_TOKENS_PREFIXES)


def build_max_tokens_param(model: str, max_tokens: int) -> dict[str, int]:
    """Build the appropriate max tokens parameter for a model.

    Args:
        model: The model ID string
        max_tokens: The max tokens value

    Returns:
        Dict with either {"max_completion_tokens": value} or {"max_tokens": value}
    """
    if uses_max_completion_tokens(model):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens}


_VALID_REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high")


def build_reasoning_param(model_id: str, effort: str | None) -> dict[str, str]:
    """Build the reasoning_effort parameter for reasoning-capable models.

    Only GPT-5-family and O-series models accept ``reasoning_effort``; other
    models get a 400 for the unknown parameter, so it is omitted for them.
    An unset or invalid *effort* yields no parameter (provider default).

    Note: on /v1/chat/completions, gpt-5.4 models reject function tools
    combined with any effort except "none" — for tool-calling agents, "none"
    is the only value that speeds things up without a 400.
    """
    if not effort:
        return {}
    effort = effort.strip().lower()
    if effort not in _VALID_REASONING_EFFORTS:
        return {}
    if uses_max_completion_tokens(model_id) or _is_reasoning_model(model_id):
        return {"reasoning_effort": effort}
    return {}


_NO_TEMPERATURE_PATTERNS = ("o1", "o3", "o4", "codex")


def _is_reasoning_model(model_id: str) -> bool:
    """Check if model ID matches known reasoning model patterns."""
    lower = model_id.lower()
    for pattern in _NO_TEMPERATURE_PATTERNS:
        if lower == pattern or lower.startswith(f"{pattern}-") or f"/{pattern}" in lower:
            return True
    if "codex" in lower:
        return True
    return False


def build_temperature_param(model_id: str, temperature: float) -> dict[str, float]:
    """Build temperature parameter if the model supports it.

    Checks model registry for supports_temperature field.
    Falls back to name-based detection for known reasoning models (o1, o3, o4, codex).

    Args:
        model_id: The model ID string
        temperature: The temperature value

    Returns:
        Dict with {"temperature": value} or empty dict for models that don't support it
    """
    # Reasoning models (o1/o3/o4/codex) and the GPT-5 family only accept the
    # default temperature (1); sending a custom value is a 400. Omit it for them.
    if _is_reasoning_model(model_id) or uses_max_completion_tokens(model_id):
        return {}

    from atria.config.models import get_model_registry

    registry = get_model_registry()
    result = registry.find_model_by_id(model_id)
    if result:
        _, _, model_info = result
        if not model_info.supports_temperature:
            return {}
    return {"temperature": temperature}


_DEFAULT_API_URL = "https://api.openai.com/v1/chat/completions"


def resolve_api_config(config: AppConfig) -> Tuple[str, dict[str, str]]:
    """Return the API URL and headers for the OpenAI-compatible endpoint."""
    api_key = config.get_api_key()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    api_url = config.api_base_url or _DEFAULT_API_URL
    return api_url, headers


def create_http_client(config: AppConfig) -> "ProviderAdapter":
    """Create an AgentHttpClient for the configured OpenAI-compatible endpoint."""
    from .http_client import AgentHttpClient

    api_url, headers = resolve_api_config(config)
    return AgentHttpClient(api_url, headers)
