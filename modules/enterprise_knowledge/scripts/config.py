"""Module-local model-provider config for the enterprise_knowledge module.

Maps feature roles (index_embed, synthesis, kg_extract) to OpenAI-compatible
endpoints. Defaults target a hosted API (OpenAI); every field is overridable
per role via ``EK_<ROLE>_<FIELD>``. When a role has no explicit
``EK_<ROLE>_API_KEY``, the key is chosen to match the endpoint host — an
OpenRouter base_url gets OPENROUTER_API_KEY, an OpenAI base_url gets
OPENAI_API_KEY — so a ``.env`` that carries both keys routes each provider
correctly. This layer is self-contained and does not touch Atria's global
provider system.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Mapping, Optional

ROLES = ("index_embed", "synthesis", "kg_extract")


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
    # Entity/relation extraction for the knowledge graph. Any chat model works;
    # override per deployment via EK_KG_EXTRACT_* (mirrors EK_SYNTHESIS_*).
    "kg_extract": RoleConfig("openai", "gpt-4o-mini",
                             "https://api.openai.com/v1", ""),
}


def _fallback_api_key(base_url: str, src: Mapping[str, str]) -> str:
    """Pick the fallback API key that matches the endpoint host.

    With both OPENAI_API_KEY and OPENROUTER_API_KEY set (a common ``.env``),
    route by host so an OpenRouter base_url uses the OpenRouter key and an OpenAI
    base_url uses the OpenAI key. Falls back to whichever key is present, else ''.
    """
    openai_key = src.get("OPENAI_API_KEY") or ""
    openrouter_key = src.get("OPENROUTER_API_KEY") or ""
    if "openrouter.ai" in base_url:
        return openrouter_key or openai_key
    return openai_key or openrouter_key


def load_config(env: Optional[Mapping[str, str]] = None) -> Dict[str, RoleConfig]:
    """Return the resolved config for all roles, applying env overrides.

    For each role, ``EK_<ROLE>_PROVIDER|MODEL|BASE_URL|API_KEY`` (role upper-
    cased) overrides the corresponding default field. When no explicit API key
    is set, it falls back to the key matching the resolved base_url's host
    (see :func:`_fallback_api_key`).
    """
    src = os.environ if env is None else env
    resolved: Dict[str, RoleConfig] = {}
    for role in ROLES:
        d = _DEFAULTS[role]
        prefix = f"EK_{role.upper()}_"
        base_url = src.get(f"{prefix}BASE_URL", d.base_url)
        resolved[role] = RoleConfig(
            provider=src.get(f"{prefix}PROVIDER", d.provider),
            model=src.get(f"{prefix}MODEL", d.model),
            base_url=base_url,
            api_key=src.get(f"{prefix}API_KEY", _fallback_api_key(base_url, src)),
        )
    return resolved
