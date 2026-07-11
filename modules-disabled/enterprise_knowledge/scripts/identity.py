"""Load synthetic users and resolve a user_id to an access identity.

Users come from ``access/users.csv`` (materialized from the dataset). The
``department`` column is a canonical department_id (COMP/HR/FIN/PROD/ENG/OPS/
LEGAL/EXEC) so it compares exactly against document departments in the ACL layer.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


class UnknownUserError(ValueError):
    """Raised when a user_id is not present in the users table."""


@dataclass(frozen=True)
class User:
    """A resolved access identity."""

    user_id: str
    full_name: str
    role: str          # Employee | Manager | Director | Executive
    department: str    # canonical department_id
    status: str


def default_users_path() -> str:
    """Return EK_USERS_CSV if set, else ``<module>/access/users.csv``."""
    override = os.environ.get("EK_USERS_CSV")
    if override:
        return override
    return str(Path(__file__).resolve().parent.parent / "access" / "users.csv")


def load_users(path: str | None = None) -> Dict[str, User]:
    """Load the users table into a ``{user_id: User}`` map."""
    target = path or default_users_path()
    users: Dict[str, User] = {}
    with open(target, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            user = User(
                user_id=row["user_id"].strip(),
                full_name=row.get("full_name", "").strip(),
                role=row["role"].strip(),
                department=row["department"].strip(),
                status=row.get("status", "Active").strip(),
            )
            users[user.user_id] = user
    return users


def resolve(users: Dict[str, User], user_id: str) -> User:
    """Return the :class:`User` for ``user_id`` or raise :class:`UnknownUserError`."""
    try:
        return users[user_id]
    except KeyError as exc:
        raise UnknownUserError(f"unknown user_id: {user_id!r}") from exc
