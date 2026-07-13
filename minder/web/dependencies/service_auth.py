"""Service-principal auth: a Keycloak service-account token bearing the
``module-push`` realm role. Distinct from human-user login
(``require_authenticated_user``) — used to gate the module reverse-push ingress.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from minder.web.state import get_state

MODULE_PUSH_ROLE = "module-push"
MODULE_REGISTER_ROLE = "module-register"


async def _validate_and_roles(request: Request) -> tuple[dict, list[str]]:
    state = get_state()
    services = getattr(state, "keycloak", None)
    if services is None or getattr(services, "validator", None) is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "service auth not configured")
    auth = request.headers.get("Authorization", "")
    token = auth.split(" ", 1)[1].strip() if auth.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        claims = services.validator.validate(token)
    except Exception as exc:  # noqa: BLE001 — any validation failure is a 401
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc
    roles = list((claims.get("realm_access") or {}).get("roles") or [])
    return claims, roles


def _principal(claims: dict, roles: list[str]) -> dict:
    return {"client_id": claims.get("azp") or claims.get("clientId"), "roles": roles}


async def require_service_principal(request: Request) -> dict:
    """Validate a Keycloak service token and require the ``module-push`` role.

    Returns ``{"client_id", "roles"}`` on success. Raises 401 on a missing or
    invalid token, 403 when the ``module-push`` realm role is absent, and 503
    when Keycloak is not configured.
    """
    claims, roles = await _validate_and_roles(request)
    if MODULE_PUSH_ROLE not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"missing {MODULE_PUSH_ROLE} role")
    return _principal(claims, roles)


async def require_module_register(request: Request) -> dict:
    """Validate a Keycloak service token and require the ``module-register`` role.

    Returns ``{"client_id", "roles"}`` on success. Raises 401 on a missing or
    invalid token, 403 when the ``module-register`` realm role is absent, and 503
    when Keycloak is not configured.
    """
    claims, roles = await _validate_and_roles(request)
    if MODULE_REGISTER_ROLE not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"missing {MODULE_REGISTER_ROLE} role")
    return _principal(claims, roles)
