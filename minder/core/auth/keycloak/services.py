# minder/core/auth/keycloak/services.py
from __future__ import annotations

from dataclasses import dataclass

from minder.core.auth.keycloak.admin_client import KeycloakAdminClient
from minder.core.auth.keycloak.config import AuthMode, KeycloakConfig
from minder.core.auth.keycloak.jwt import JwksCache, TokenValidator


@dataclass(frozen=True)
class KeycloakServices:
    config: KeycloakConfig
    validator: TokenValidator
    admin: KeycloakAdminClient

    @classmethod
    def from_env(cls) -> "KeycloakServices | None":
        cfg = KeycloakConfig.from_env()
        if cfg.auth_mode is not AuthMode.KEYCLOAK:
            return None
        cache = JwksCache(cfg)
        validator = TokenValidator(cfg, cache)
        admin = KeycloakAdminClient(cfg)
        return cls(config=cfg, validator=validator, admin=admin)
