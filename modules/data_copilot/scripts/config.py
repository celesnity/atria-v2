"""Module-local model-provider config for the data_copilot module.

Maps three feature *roles* to OpenAI-compatible endpoints. Every field is read
from ``DC_<ROLE>_<FIELD>`` environment variables with OpenAI defaults, and the
api_key falls back to ``OPENAI_API_KEY`` when a role-specific key is unset. This
layer is deliberately self-contained: it does not touch Atria's global provider
system.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Mapping, Optional

ROLES = ("codegen", "verify", "report")


@dataclass(frozen=True)
class RoleConfig:
    """Endpoint + model for one feature role."""

    provider: str
    model: str
    base_url: str
    api_key: str


# OpenAI-compatible defaults. Code generation needs a capable model; every field
# is overridable per role via env (e.g. point DC_CODEGEN_BASE_URL at local vLLM).
_DEFAULTS: Dict[str, RoleConfig] = {
    "codegen": RoleConfig("openai", "gpt-4o-mini", "https://api.openai.com/v1", ""),
    "verify": RoleConfig("openai", "gpt-4o-mini", "https://api.openai.com/v1", ""),
    "report": RoleConfig("openai", "gpt-4o-mini", "https://api.openai.com/v1", ""),
}


def load_config(env: Optional[Mapping[str, str]] = None) -> Dict[str, RoleConfig]:
    """Return the resolved config for all roles, applying env overrides.

    For each role, ``DC_<ROLE>_PROVIDER|MODEL|BASE_URL|API_KEY`` (role upper-
    cased) overrides the corresponding default field. A role's api_key defaults
    to ``OPENAI_API_KEY`` when neither an override nor a default is set.

    Args:
        env: Optional environment mapping (defaults to ``os.environ``).

    Returns:
        Mapping of role name to its resolved :class:`RoleConfig`.
    """
    src = os.environ if env is None else env
    fallback_key = src.get("OPENAI_API_KEY", "")
    resolved: Dict[str, RoleConfig] = {}
    for role in ROLES:
        d = _DEFAULTS[role]
        prefix = f"DC_{role.upper()}_"
        resolved[role] = RoleConfig(
            provider=src.get(f"{prefix}PROVIDER", d.provider),
            model=src.get(f"{prefix}MODEL", d.model),
            base_url=src.get(f"{prefix}BASE_URL", d.base_url),
            api_key=src.get(f"{prefix}API_KEY", d.api_key or fallback_key),
        )
    return resolved
