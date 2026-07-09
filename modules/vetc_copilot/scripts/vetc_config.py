"""Real VETC partner-gateway config (VMA Auth + Payment).

Values come from ``VETC_*`` env (set in ``.env``, passed to the container via
docker-compose). Without ``VETC_CLIENT_ID`` / ``VETC_CLIENT_SECRET`` the module
is ``configured == False`` and callers fall back to the mock payment path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

_UAT = "https://uat-apigw-kds.vetc.com.vn/partner-gateway/v1"
_PROD = "https://apigw-kds.vetc.com.vn/partner-gateway/v1"


@dataclass(frozen=True)
class VetcConfig:
    """Partner-gateway base URL + issued credentials."""

    base_url: str
    client_id: str
    client_secret: str
    terminal_id: str
    mini_app_id: str

    @property
    def configured(self) -> bool:
        """True when VETC-issued credentials are present (real calls possible)."""
        return bool(self.client_id and self.client_secret)


def load_vetc_config(env: Optional[Mapping[str, str]] = None) -> VetcConfig:
    """Resolve the VETC gateway config from ``VETC_*`` env.

    ``VETC_ENV`` selects uat (default) vs prod; ``VETC_BASE_URL`` overrides the
    base URL outright. Credentials are ``VETC_CLIENT_ID`` / ``VETC_CLIENT_SECRET``;
    ``VETC_TERMINAL_ID`` and ``VETC_MINI_APP_ID`` are the issued merchant/app ids.
    """
    src = os.environ if env is None else env
    envname = (src.get("VETC_ENV", "uat") or "uat").lower()
    base = src.get("VETC_BASE_URL") or (_PROD if envname == "prod" else _UAT)
    return VetcConfig(
        base_url=base.rstrip("/"),
        client_id=src.get("VETC_CLIENT_ID", "") or "",
        client_secret=src.get("VETC_CLIENT_SECRET", "") or "",
        terminal_id=src.get("VETC_TERMINAL_ID", "com.vetc.charging") or "com.vetc.charging",
        mini_app_id=src.get("VETC_MINI_APP_ID", "") or "",
    )
