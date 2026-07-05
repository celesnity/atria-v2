#!/usr/bin/env python
"""Local, spec-faithful VETC partner-gateway simulator (VMA Auth + Payment).

Pure ``handle(...)`` dispatcher + a thin threaded http.server wrapper. Lets the
module's real vetc_client run end-to-end (OAuth2, init-payment, IPN push, user
login) without VETC credentials. NOT for production.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ipn_sig import ipn_sign  # type: ignore[import-not-found]


@dataclass
class SandboxState:
    """In-memory sandbox stores."""

    client_id: str
    client_secret: str
    hmac_secret: str
    users: dict
    autocomplete_seconds: int = 2
    backend_tokens: set = field(default_factory=set)
    user_tokens: dict = field(default_factory=dict)   # token -> user_id
    auth_codes: dict = field(default_factory=dict)     # code -> user_id
    payments: dict = field(default_factory=dict)       # id -> payment dict
    _seq: int = 0

    def next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}{self._seq:06d}"


def new_state(env: dict) -> SandboxState:
    """Build sandbox state from ``SANDBOX_*`` env."""
    return SandboxState(
        client_id=env.get("SANDBOX_CLIENT_ID", "sandbox-client"),
        client_secret=env.get("SANDBOX_CLIENT_SECRET", "sandbox-secret"),
        hmac_secret=env.get("SANDBOX_HMAC_SECRET", "sandbox-hmac-secret"),
        users=json.loads(env.get("SANDBOX_USERS", "{}") or "{}"),
        autocomplete_seconds=int(env.get("SANDBOX_AUTOCOMPLETE_SECONDS", "2")),
    )


def _form(body: bytes) -> dict:
    return {k: v[0] for k, v in urllib.parse.parse_qs(body.decode("utf-8")).items()}


def _bearer(headers: dict) -> str:
    auth = headers.get("Authorization") or headers.get("authorization") or ""
    return auth[7:] if auth.startswith("Bearer ") else ""


def handle(method: str, path: str, headers: dict, body: bytes, state: SandboxState, poster) -> "tuple[int, dict]":
    """Route one request. ``poster(url, dict)`` sends an IPN (injectable)."""
    route = (method, path)
    if route == ("POST", "/partner-gateway/v1/auth/token"):
        f = _form(body)
        if f.get("client_id") != state.client_id or f.get("client_secret") != state.client_secret:
            return 401, {"error": "invalid_client", "error_description": "Invalid client credentials"}
        tok = state.next_id("bk_")
        state.backend_tokens.add(tok)
        return 200, {"access_token": tok, "token_type": "Bearer", "expires_in": 3600,
                     "scope": "openid profile"}
    if route == ("POST", "/sandbox/authcode"):
        uid = (json.loads(body or b"{}")).get("user_id", "")
        code = state.next_id("ac_")
        state.auth_codes[code] = uid
        return 200, {"auth_code": code, "user_id": uid}
    if route == ("POST", "/partner-gateway/v1/mini-app/token"):
        f = _form(body)
        if f.get("grant_type") == "authorization_code":
            uid = state.auth_codes.get(f.get("code", ""))
            if uid is None:
                return 422, {"error": "INVALID_AUTH_CODE", "error_description": "Auth Code không đúng"}
        else:  # refresh_token
            uid = state.user_tokens.get(f.get("refresh_token", ""))
            if uid is None:
                return 401, {"error": "invalid_grant", "error_description": "Invalid refresh token"}
        at, rt = state.next_id("ut_"), state.next_id("rt_")
        state.user_tokens[at] = uid
        state.user_tokens[rt] = uid
        return 200, {"access_token": at, "refresh_token": rt, "id_token": state.next_id("id_"),
                     "token_type": "Bearer", "expires_in": 300, "scope": "openid profile email"}
    if route == ("GET", "/partner-gateway/v1/mini-app/user"):
        uid = state.user_tokens.get(_bearer(headers))
        if not uid:
            return 401, {"code": "UNAUTHORIZED", "message": "Access token không hợp lệ"}
        profile = state.users.get(uid, {"name": uid})
        return 200, {"code": "00", "message": "Thành công", "data": profile}
    return 404, {"code": "NOT_FOUND", "message": f"no route {method} {path}"}
