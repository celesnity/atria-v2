"""Brain model config from VA_BRAIN_* env, falling back to OPENAI_API_KEY."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class RoleConfig:
    """Endpoint + model for the Brain role."""

    provider: str
    model: str
    base_url: str
    api_key: str


def load_brain_config(env: Optional[Mapping[str, str]] = None) -> RoleConfig:
    """Resolve the Brain config, applying ``VA_BRAIN_*`` overrides.

    ``VA_BRAIN_API_KEY`` wins; otherwise ``OPENAI_API_KEY``; otherwise empty
    (which makes the client report ``available == False``).
    """
    src = os.environ if env is None else env
    return RoleConfig(
        provider=src.get("VA_BRAIN_PROVIDER", "openai"),
        model=src.get("VA_BRAIN_MODEL", "gpt-4o-mini"),
        base_url=src.get("VA_BRAIN_BASE_URL", "https://api.openai.com/v1"),
        api_key=src.get("VA_BRAIN_API_KEY", src.get("OPENAI_API_KEY", "")),
    )
