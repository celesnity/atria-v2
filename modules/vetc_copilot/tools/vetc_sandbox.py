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


def _complete_payment(state: SandboxState, pid: str, poster) -> bool:
    pay = state.payments.get(pid)
    if not pay:
        return False
    pay["status"] = "SUCCESS"
    for t in pay.get("transactions", []):
        t["status"] = "SUCCESS"
    ipn_url = pay.get("ipn_url")
    if ipn_url:
        sig = ipn_sign(pay["order_id"], pid, "SUCCESS", state.hmac_secret)
        poster(ipn_url, {"order_id": pay["order_id"], "payment_id": pid,
                         "status": "SUCCESS", "signature": sig})
    return True


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
    if route == ("POST", "/partner-gateway/v1/mini-app/payments"):
        if _bearer(headers) not in state.backend_tokens:
            return 401, {"code": "UNAUTHORIZED", "message": "Access token không hợp lệ"}
        try:
            req = json.loads(body or b"{}")
        except ValueError:
            return 400, {"code": "BAD_REQUEST", "message": "Bad request"}
        if not req.get("order_id") or not req.get("amount") or not req.get("terminal_id"):
            return 422, {"code": "INVALID_REQUEST", "message": "Dữ liệu không hợp lệ"}
        pid = state.next_id("pay_")
        meta = req.get("metadata", {}) or {}
        hmac_str = f"INIT_TRANS|{pid}|{req['terminal_id']}|null|{req['amount']}.00"
        pay = {
            "id": pid, "merchant_id": req["terminal_id"], "terminal_id": req["terminal_id"],
            "order_id": str(req["order_id"]), "amount": req["amount"], "status": "CREATED",
            "description": req.get("description", ""), "metadata": meta,
            "ipn_url": meta.get("ipn_url"),
            "provider_payload": {"hmac": hmac_str,
                                 "signature": ipn_sign(pid, req["terminal_id"], "INIT", state.hmac_secret),
                                 "mc_order_id": pid, "mid": req["terminal_id"]},
            "transactions": [{"id": state.next_id("txn_"), "type": "PAYMENT",
                              "amount": req["amount"], "status": "CREATED"}],
        }
        state.payments[pid] = pay
        # Simulate the user approving in the VETC app after a short delay.
        if state.autocomplete_seconds >= 0:
            import threading

            threading.Timer(state.autocomplete_seconds, _complete_payment, args=(state, pid, poster)).start()
        return 201, {"code": "00", "message": "Success", "data": pay}
    if method == "GET" and path.startswith("/partner-gateway/v1/mini-app/payments/"):
        pid = path.rsplit("/", 1)[-1]
        pay = state.payments.get(pid)
        if not pay:
            return 404, {"code": "NOT_FOUND", "message": "payment not found"}
        return 200, {"code": "00", "data": {"id": pid, "order_id": pay["order_id"],
                     "amount": pay["amount"], "status": pay["status"]}}
    if method == "POST" and path.endswith("/complete") and "/payments/" in path:
        pid = path.rsplit("/", 2)[-2]
        if not _complete_payment(state, pid, poster):
            return 404, {"code": "NOT_FOUND", "message": "payment not found"}
        return 200, {"code": "00", "message": "completed"}
    return 404, {"code": "NOT_FOUND", "message": f"no route {method} {path}"}
