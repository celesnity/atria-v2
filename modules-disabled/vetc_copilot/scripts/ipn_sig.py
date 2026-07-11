"""Shared HMAC-SHA256 signing for the VETC IPN callback.

The sandbox signs; the /ipn receiver verifies. Keeping both on these two
functions guarantees they never drift. To go live against the real VETC
gateway, replace ``ipn_verify`` with VETC's scheme — nothing else changes.
"""
from __future__ import annotations

import hashlib
import hmac


def _canonical(order_id: str, payment_id: str, status: str) -> bytes:
    return f"{order_id}|{payment_id}|{status}".encode("utf-8")


def ipn_sign(order_id: str, payment_id: str, status: str, secret: str) -> str:
    """Return the hex HMAC-SHA256 signature for an IPN payload."""
    return hmac.new(secret.encode("utf-8"), _canonical(order_id, payment_id, status),
                    hashlib.sha256).hexdigest()


def ipn_verify(order_id: str, payment_id: str, status: str, signature: str, secret: str) -> bool:
    """Constant-time check that ``signature`` matches the payload under ``secret``."""
    expected = ipn_sign(order_id, payment_id, status, secret)
    return hmac.compare_digest(expected, signature or "")
