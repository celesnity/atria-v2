"""Runtime self-registration helpers for Minder service-modules.

On startup a module can call ``announce(module, cfg)`` to register itself with
the Minder host so the host knows the connector URL and can proxy tool calls.
On shutdown, ``deregister(module, cfg)`` removes the registration (best-effort).

All configuration is read from environment variables — no ``minder`` package is
imported, so this module is safe to run inside the module's own slim container.

Environment variables
---------------------
MINDER_URL
    Base URL of the Minder host (e.g. ``http://minder:8000``). Required.
MINDER_MODULE_CONNECTOR_URL
    Publicly reachable base URL of *this* module's connector (e.g.
    ``http://maintenance-copilot:8080``). Required.
MINDER_MODULE_REMOTE_ENTRY
    Optional. Full URL of the Module Federation ``remoteEntry.js``.  When set,
    ``api_base`` is derived by splitting on ``/dashboard/`` so Minder knows where
    the module's dashboard lives.
KEYCLOAK_TOKEN_URL
    Optional. Token endpoint for the client-credentials grant.
MINDER_MODULE_CLIENT_ID
    Client-ID for the client-credentials grant. Defaults to ``"minder-module"``.
MINDER_MODULE_CLIENT_SECRET
    Client-secret for the client-credentials grant. Required when
    ``KEYCLOAK_TOKEN_URL`` is set; token fetch is skipped if absent.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Optional

import httpx

logger = logging.getLogger("minder_python_sdk.announce")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class AnnounceConfig:
    """Resolved announce configuration (all fields already substituted)."""

    minder_url: str
    """Base URL of the Minder host, e.g. ``http://minder:8000``."""

    connector_url: str
    """Publicly reachable base URL of this module's connector."""

    remote_entry: Optional[str] = None
    """Full URL of the Module Federation ``remoteEntry.js`` (optional)."""

    api_base: Optional[str] = None
    """Derived from *remote_entry* by splitting on ``/dashboard/``. ``None`` when
    *remote_entry* is not set or does not contain ``/dashboard/``."""

    token_url: Optional[str] = None
    """Keycloak token endpoint (optional)."""

    client_id: str = "minder-module"
    """OAuth2 client-ID for the client-credentials grant."""

    client_secret: Optional[str] = None
    """OAuth2 client-secret. Token fetch is skipped when ``None``."""

    extra_headers: dict = field(default_factory=dict)
    """Extra HTTP headers forwarded with every request (e.g. injected at test time)."""


def resolve_announce_config() -> Optional[AnnounceConfig]:
    """Build an :class:`AnnounceConfig` from environment variables.

    Returns:
        A populated :class:`AnnounceConfig`, or ``None`` when the minimum
        required variables (``MINDER_URL`` and ``MINDER_MODULE_CONNECTOR_URL``)
        are missing.
    """
    minder_url = os.environ.get("MINDER_URL", "").rstrip("/")
    connector_url = os.environ.get("MINDER_MODULE_CONNECTOR_URL", "").rstrip("/")

    if not minder_url or not connector_url:
        logger.debug(
            "announce: MINDER_URL or MINDER_MODULE_CONNECTOR_URL not set — skipping registration"
        )
        return None

    remote_entry = os.environ.get("MINDER_MODULE_REMOTE_ENTRY") or None
    api_base: Optional[str] = None
    if remote_entry and "/dashboard/" in remote_entry:
        api_base = remote_entry.split("/dashboard/")[0]

    token_url = os.environ.get("KEYCLOAK_TOKEN_URL") or None
    client_id = os.environ.get("MINDER_MODULE_CLIENT_ID", "minder-module")
    client_secret = os.environ.get("MINDER_MODULE_CLIENT_SECRET") or None

    return AnnounceConfig(
        minder_url=minder_url,
        connector_url=connector_url,
        remote_entry=remote_entry,
        api_base=api_base,
        token_url=token_url,
        client_id=client_id,
        client_secret=client_secret,
    )


# ---------------------------------------------------------------------------
# Token acquisition
# ---------------------------------------------------------------------------


def fetch_service_token(cfg: AnnounceConfig) -> Optional[str]:
    """Obtain an access token via the OAuth2 client-credentials grant.

    Args:
        cfg: Resolved :class:`AnnounceConfig`.

    Returns:
        A bearer token string, or ``None`` when *token_url* or *client_secret*
        is absent (i.e. Keycloak integration is not configured).
    """
    if not cfg.token_url or not cfg.client_secret:
        logger.debug("announce: token_url or client_secret not set — skipping token fetch")
        return None

    try:
        resp = httpx.post(
            cfg.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": cfg.client_id,
                "client_secret": cfg.client_secret,
            },
            timeout=10,
        )
        resp.raise_for_status()
        token: str = resp.json()["access_token"]
        logger.debug("announce: obtained service token (client_id=%s)", cfg.client_id)
        return token
    except Exception as exc:  # noqa: BLE001
        logger.warning("announce: failed to fetch service token: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Register / deregister
# ---------------------------------------------------------------------------


def _auth_headers(cfg: AnnounceConfig) -> dict:
    """Return Authorization + any extra headers for a request."""
    token = fetch_service_token(cfg)
    headers: dict = dict(cfg.extra_headers)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def announce(module: str, cfg: AnnounceConfig) -> None:
    """Register this module with the Minder host.

    POSTs to ``{minder_url}/api/modules/register`` with the module name,
    connector URL, and (when available) the remote-entry / api_base for the
    Module Federation dashboard.

    Args:
        module: The module's canonical name (e.g. ``"maintenance_copilot"``).
        cfg: Resolved :class:`AnnounceConfig`.

    Raises:
        httpx.HTTPStatusError: When the host returns a non-2xx response.
        httpx.RequestError: On network-level failures.
    """
    url = f"{cfg.minder_url}/api/modules/register"
    payload: dict = {
        "module": module,
        "connector_url": cfg.connector_url,
    }
    if cfg.remote_entry:
        payload["remote_entry"] = cfg.remote_entry
    if cfg.api_base:
        payload["api_base"] = cfg.api_base

    logger.info("announce: registering module %r at %s", module, url)
    resp = httpx.post(url, json=payload, headers=_auth_headers(cfg), timeout=10)
    resp.raise_for_status()
    logger.info("announce: module %r registered successfully", module)


def deregister(module: str, cfg: AnnounceConfig) -> None:
    """Deregister this module from the Minder host (best-effort).

    POSTs to ``{minder_url}/api/modules/deregister``.  All errors are swallowed
    so that shutdown is never blocked by a failing deregistration call.

    Args:
        module: The module's canonical name.
        cfg: Resolved :class:`AnnounceConfig`.
    """
    url = f"{cfg.minder_url}/api/modules/deregister"
    try:
        resp = httpx.post(
            url,
            json={"module": module},
            headers=_auth_headers(cfg),
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("announce: module %r deregistered", module)
    except Exception as exc:  # noqa: BLE001
        logger.debug("announce: deregister failed (best-effort, ignoring): %s", exc)


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

# Re-announce interval (seconds). Minder holds connector records in memory, so a
# one-shot startup announce is lost if Minder restarts while this module keeps
# running. Re-announcing on a timer means a restarted Minder re-learns this live
# module within one interval. 0 disables. register is idempotent, so a heartbeat
# that changes nothing is cheap.
HEARTBEAT_ENV = "MINDER_MODULE_HEARTBEAT_SEC"
DEFAULT_HEARTBEAT_SEC = 30.0


def start_heartbeat(
    module: str, cfg: AnnounceConfig, interval: Optional[float] = None
) -> Callable[[], None]:
    """Re-announce ``module`` every ``interval`` seconds on a daemon thread.

    Returns a stop function. Interval defaults to ``$MINDER_MODULE_HEARTBEAT_SEC``
    (or 30s); a value <= 0 disables the heartbeat and returns a no-op stop.
    """
    import threading

    if interval is None:
        try:
            interval = float(os.environ.get(HEARTBEAT_ENV, DEFAULT_HEARTBEAT_SEC))
        except ValueError:
            interval = DEFAULT_HEARTBEAT_SEC
    if interval <= 0:
        return lambda: None

    stop = threading.Event()

    def _loop() -> None:
        while not stop.wait(interval):
            try:
                announce(module, cfg)
            except Exception as exc:  # noqa: BLE001 — a flaky Minder must not crash the module
                logger.debug("heartbeat announce failed (ignoring): %s", exc)

    threading.Thread(target=_loop, name=f"minder-heartbeat-{module}", daemon=True).start()
    return stop.set
