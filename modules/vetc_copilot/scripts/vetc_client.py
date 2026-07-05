"""Real VETC Mini App backend connector (VMA Authentication + VMA Payment).

Implements the documented partner-gateway contract:
- Backend token: OAuth2 Client Credentials Grant (``POST /auth/token``).
- Init payment: ``POST /mini-app/payments`` (Bearer + Idempotency/Trace headers).
- User token exchange: ``POST /mini-app/token`` (authorization_code / refresh).
- User info: ``GET /mini-app/user``.

HTTP is done through an injectable ``transport`` so the contract can be unit
tested against the documented sample responses without live credentials. In
production the default urllib transport calls the real gateway; credentials come
from :func:`vetc_config.load_vetc_config`.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

# transport(method, url, headers, body_bytes) -> (status_code, parsed_json_dict)
Transport = Callable[[str, str, dict, Optional[bytes]], "tuple[int, dict]"]


class VetcError(RuntimeError):
    """Raised when a VETC gateway call fails or returns a non-success payload."""


def _default_transport(
    method: str, url: str, headers: dict, body: Optional[bytes]
) -> "tuple[int, dict]":
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed gateway host
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, (json.loads(raw) if raw else {})
        except ValueError:
            return exc.code, {"error": raw.decode("utf-8", "replace")[:300]}


class VetcClient:
    """Client for the VETC partner-gateway. Caches the backend token until expiry."""

    def __init__(
        self, cfg, transport: Optional[Transport] = None, now: Callable[[], float] = time.time
    ) -> None:
        self._cfg = cfg
        self._t = transport or _default_transport
        self._now = now
        self._token: str = ""
        self._token_exp: float = 0.0

    def backend_token(self) -> str:
        """Return a cached machine-to-machine access token, fetching if needed."""
        if self._token and self._now() < self._token_exp - 30:
            return self._token
        body = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self._cfg.client_id,
                "client_secret": self._cfg.client_secret,
                "scope": "openid profile",
            }
        ).encode()
        status, data = self._t(
            "POST",
            f"{self._cfg.base_url}/auth/token",
            {"Content-Type": "application/x-www-form-urlencoded"},
            body,
        )
        if status != 200 or "access_token" not in data:
            raise VetcError(f"auth failed ({status}): {data.get('error_description') or data}")
        self._token = str(data["access_token"])
        self._token_exp = self._now() + float(data.get("expires_in", 3600))
        return self._token

    def init_payment(
        self,
        order_id: str,
        amount: int,
        description: str,
        metadata: dict,
        idempotency_key: Optional[str] = None,
        trace_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> dict:
        """Create a payment on the gateway; returns the ``data`` payment object.

        The returned object includes ``provider_payload`` (hmac + signature) that
        the Mini App front-end hands off to the VETC Main App to complete payment.
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.backend_token()}",
            "Idempotency-Key": idempotency_key or str(order_id),
            "X-Trace-ID": trace_id or str(order_id),
            "X-Request-ID": request_id or str(order_id),
        }
        body = json.dumps(
            {
                "terminal_id": self._cfg.terminal_id,
                "order_id": str(order_id),
                "amount": int(amount),
                "description": description,
                "metadata": metadata,
            }
        ).encode()
        status, data = self._t("POST", f"{self._cfg.base_url}/mini-app/payments", headers, body)
        if status not in (200, 201) or (data.get("code") not in ("00", None)):
            raise VetcError(f"init_payment failed ({status}): {data}")
        return data.get("data", data)

    def exchange_user_token(self, code: str, redirect_uri: str = "") -> dict:
        """Exchange an authorization code (from the Mini App FE) for user tokens."""
        body = urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "client_id": self._cfg.client_id,
                "client_secret": self._cfg.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            }
        ).encode()
        status, data = self._t(
            "POST",
            f"{self._cfg.base_url}/mini-app/token",
            {"Content-Type": "application/x-www-form-urlencoded"},
            body,
        )
        if status != 200 or "access_token" not in data:
            raise VetcError(f"token exchange failed ({status}): {data}")
        return data

    def get_user_info(self, user_access_token: str) -> dict:
        """Return the user profile (name/email/phone) for an exchanged user token."""
        status, data = self._t(
            "GET",
            f"{self._cfg.base_url}/mini-app/user",
            {
                "Authorization": f"Bearer {user_access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            None,
        )
        if status != 200 or data.get("code") != "00":
            raise VetcError(f"get_user_info failed ({status}): {data}")
        return data.get("data", {})
