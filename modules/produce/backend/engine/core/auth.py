"""Self-contained authorization: role -> verbs, plus scope containment."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from engine.core.grant import PrGrant
from engine.core.scope import PrScope, contains

ROLES = ("worker", "lead", "supervisor", "configurator", "viewer")

# Cumulative operational verbs. Configurator is deliberately execution-less (P-03).
_WORKER = {"read", "claim", "execute", "submit_output", "raise_exception"}
_LEAD = _WORKER | {"assign", "resolve_exception", "override"}
_SUPERVISOR = _LEAD | {"approve_high_risk", "close_period"}

ROLE_VERBS: dict[str, set[str]] = {
    "worker": _WORKER,
    "lead": _LEAD,
    "supervisor": _SUPERVISOR,
    "configurator": {"read", "configure"},
    "viewer": {"read"},
}


@dataclass
class Principal:
    subject: str
    grants: list[tuple[str, str]] = field(default_factory=list)  # (role, scope_path)


def load_principal(session: Session, subject: str) -> Principal:
    rows = (
        session.query(PrGrant.role, PrScope.path)
        .join(PrScope, PrGrant.scope_id == PrScope.id)
        .filter(PrGrant.subject == subject)
        .all()
    )
    return Principal(subject=subject, grants=[(role, path) for role, path in rows])


def check(principal: Principal, verb: str, scope_path: str) -> bool:
    for role, grant_path in principal.grants:
        if verb in ROLE_VERBS.get(role, set()) and contains(grant_path, scope_path):
            return True
    return False


def require(principal: Principal, verb: str, scope_path: str) -> None:
    if not check(principal, verb, scope_path):
        raise PermissionError(f"{principal.subject} lacks '{verb}' on '{scope_path}'")
