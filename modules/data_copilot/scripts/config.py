"""Module-local model-provider config for the data_copilot module.

Maps three feature *roles* (``codegen``, ``verify``, ``report``) to
OpenAI-compatible endpoints. Resolution per field, highest priority first:

1. ``DC_<ROLE>_<FIELD>`` — explicit per-role override (e.g. point
   ``DC_CODEGEN_BASE_URL`` at a local vLLM for offline code generation).
2. The **core Atria** LLM env — ``ATRIA_MODEL`` and ``ATRIA_API_BASE_URL`` — so
   by default the copilot talks to the same model the rest of Atria uses,
   without any extra ``DC_*`` setup.
3. OpenAI-compatible fallbacks (``gpt-4o-mini`` at ``api.openai.com``).

The API key mirrors core Atria's own selection (:meth:`AppConfig.get_api_key`):
``OPENAI_API_KEY`` / ``OPENROUTER_API_KEY``, ordered by whether the endpoint is
OpenRouter. The module stays self-contained — it reads the same env vars core
reads rather than importing Atria's provider system.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Mapping, Optional

ROLES = ("codegen", "verify", "report")

_OPENAI_BASE_URL = "https://api.openai.com/v1"
_FALLBACK_MODEL = "gpt-4o-mini"


@dataclass(frozen=True)
class RoleConfig:
    """Endpoint + model for one feature role."""

    provider: str
    model: str
    base_url: str
    api_key: str


def _normalize_base_url(url: str) -> str:
    """Strip a trailing ``/chat/completions`` (the OpenAI SDK appends it itself).

    ``ATRIA_API_BASE_URL`` is often stored as the full completions URL; the
    OpenAI client wants just the ``/v1`` root. Mirrors core Atria's own handling.
    """
    url = (url or "").strip().rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    return url


def _resolve_api_key(src: Mapping[str, str], base_url: str, explicit: str) -> str:
    """Pick an API key the way core Atria does: explicit, else OPENAI/OPENROUTER.

    OpenRouter endpoints prefer ``OPENROUTER_API_KEY``; every other endpoint
    prefers ``OPENAI_API_KEY``. Both are accepted as fallbacks so either key
    works against any OpenAI-compatible endpoint. Returns ``""`` if none is set.
    """
    if explicit:
        return explicit
    if "openrouter.ai" in (base_url or "").lower():
        env_order = ("OPENROUTER_API_KEY", "OPENAI_API_KEY")
    else:
        env_order = ("OPENAI_API_KEY", "OPENROUTER_API_KEY")
    for var in env_order:
        key = src.get(var)
        if key:
            return key
    return ""


def load_config(env: Optional[Mapping[str, str]] = None) -> Dict[str, RoleConfig]:
    """Return the resolved config for all roles.

    For each role and field, a ``DC_<ROLE>_<FIELD>`` override wins; otherwise the
    value falls back to the shared core-Atria LLM env (``ATRIA_MODEL`` /
    ``ATRIA_API_BASE_URL``), then to the OpenAI-compatible defaults. The api_key
    is resolved like core Atria (``OPENAI_API_KEY`` / ``OPENROUTER_API_KEY``).

    Args:
        env: Optional environment mapping (defaults to ``os.environ``).

    Returns:
        Mapping of role name to its resolved :class:`RoleConfig`.
    """
    src = os.environ if env is None else env

    # Shared Atria LLM env — the copilot inherits this by default.
    atria_base = _normalize_base_url(src.get("ATRIA_API_BASE_URL", "")) or _OPENAI_BASE_URL
    atria_model = src.get("ATRIA_MODEL", "").strip() or _FALLBACK_MODEL

    resolved: Dict[str, RoleConfig] = {}
    for role in ROLES:
        prefix = f"DC_{role.upper()}_"
        base_url = src.get(f"{prefix}BASE_URL", "").strip() or atria_base
        model = src.get(f"{prefix}MODEL", "").strip() or atria_model
        provider = src.get(f"{prefix}PROVIDER", "").strip() or "openai"
        api_key = _resolve_api_key(src, base_url, src.get(f"{prefix}API_KEY", "").strip())
        resolved[role] = RoleConfig(
            provider=provider, model=model, base_url=base_url, api_key=api_key
        )
    return resolved
