"""Module-local model-provider config for the enterprise_knowledge module.

Maps two feature roles (index_embed, synthesis) to OpenAI-compatible endpoints.
Defaults target a hosted API (OpenAI); every field is overridable per role via
``EK_<ROLE>_<FIELD>``. The api_key default falls back to OPENAI_API_KEY, then
OPENROUTER_API_KEY, so the module runs against your existing keys unchanged.
This layer is self-contained and does not touch Atria's global provider system.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Mapping, Optional

ROLES = ("index_embed", "synthesis")


@dataclass(frozen=True)
class RoleConfig:
    """Endpoint + model for one feature role."""

    provider: str
    model: str
    base_url: str
    api_key: str


# Hosted defaults. Embeddings: OpenAI text-embedding-3-small (1536-dim).
# Synthesis: a multilingual chat model (override to any OpenRouter model).
_DEFAULTS: Dict[str, RoleConfig] = {
    "index_embed": RoleConfig("openai", "text-embedding-3-small",
                              "https://api.openai.com/v1", ""),
    "synthesis": RoleConfig("openai", "gpt-4o-mini",
                            "https://api.openai.com/v1", ""),
}


def _default_api_key(src: Mapping[str, str]) -> str:
    """Fallback API key: OPENAI_API_KEY, then OPENROUTER_API_KEY, else ''."""
    return src.get("OPENAI_API_KEY") or src.get("OPENROUTER_API_KEY") or ""


def load_config(env: Optional[Mapping[str, str]] = None) -> Dict[str, RoleConfig]:
    """Return the resolved config for all roles, applying env overrides.

    For each role, ``EK_<ROLE>_PROVIDER|MODEL|BASE_URL|API_KEY`` (role upper-
    cased) overrides the corresponding default field. When no explicit API key
    is set, it falls back to OPENAI_API_KEY / OPENROUTER_API_KEY.
    """
    src = os.environ if env is None else env
    fallback_key = _default_api_key(src)
    resolved: Dict[str, RoleConfig] = {}
    for role in ROLES:
        d = _DEFAULTS[role]
        prefix = f"EK_{role.upper()}_"
        resolved[role] = RoleConfig(
            provider=src.get(f"{prefix}PROVIDER", d.provider),
            model=src.get(f"{prefix}MODEL", d.model),
            base_url=src.get(f"{prefix}BASE_URL", d.base_url),
            api_key=src.get(f"{prefix}API_KEY", fallback_key),
        )
    return resolved
