"""Brain model config.

Resolves the Brain endpoint from env with sensible, provider-aware defaults so
the module "just works" against either OpenAI or OpenRouter:

- ``VA_BRAIN_*`` always override (PROVIDER / MODEL / BASE_URL / API_KEY).
- API key precedence: ``VA_BRAIN_API_KEY`` -> ``OPENROUTER_API_KEY`` -> ``OPENAI_API_KEY``.
- OpenRouter is auto-detected when ``VA_BRAIN_PROVIDER=openrouter``, an
  ``OPENROUTER_API_KEY`` is present, or the resolved key looks like an
  OpenRouter key (``sk-or-`` prefix — common even when stored in
  ``OPENAI_API_KEY``). In that case the base URL and model default to
  OpenRouter's endpoint and a free model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
# Low-cost, reliable, good at tool-calling. Free models (e.g. gpt-oss-120b:free)
# are heavily rate-limited upstream, which breaks the agent's multi-call loop.
# Override with VA_BRAIN_MODEL to use a different model.
_OPENROUTER_MODEL = "openai/gpt-4o-mini"
_OPENAI_BASE = "https://api.openai.com/v1"
_OPENAI_MODEL = "gpt-4o-mini"


@dataclass(frozen=True)
class RoleConfig:
    """Endpoint + model for the Brain role."""

    provider: str
    model: str
    base_url: str
    api_key: str


def load_brain_config(env: Optional[Mapping[str, str]] = None) -> RoleConfig:
    """Resolve the Brain config from env, applying ``VA_BRAIN_*`` overrides.

    The operative values live in ``.env`` (``VA_BRAIN_PROVIDER`` /
    ``VA_BRAIN_MODEL`` / ``VA_BRAIN_BASE_URL``, passed to the container via
    docker-compose); the constants here are only the fallback when those are
    unset or empty. ``api_key`` is empty when no key is configured, which makes
    the client report ``available == False``.
    """
    src = os.environ if env is None else env
    api_key = (
        src.get("VA_BRAIN_API_KEY")
        or src.get("OPENROUTER_API_KEY")
        or src.get("OPENAI_API_KEY", "")
    )
    is_openrouter = (
        src.get("VA_BRAIN_PROVIDER", "").lower() == "openrouter"
        or bool(src.get("OPENROUTER_API_KEY"))
        or api_key.startswith("sk-or-")
    )
    default_base = _OPENROUTER_BASE if is_openrouter else _OPENAI_BASE
    default_model = _OPENROUTER_MODEL if is_openrouter else _OPENAI_MODEL
    default_provider = "openrouter" if is_openrouter else "openai"
    # ``or default`` (not get(k, default)) so an empty env value falls back too.
    return RoleConfig(
        provider=src.get("VA_BRAIN_PROVIDER") or default_provider,
        model=src.get("VA_BRAIN_MODEL") or default_model,
        base_url=src.get("VA_BRAIN_BASE_URL") or default_base,
        api_key=api_key or "",
    )
