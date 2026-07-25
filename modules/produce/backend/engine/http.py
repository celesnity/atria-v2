"""Principal resolution: identity from Minder header, dev fallback standalone."""

from __future__ import annotations

import os

from fastapi import Request

from engine.core.auth import Principal, load_principal
from engine.db import db_session


def get_principal(request: Request) -> Principal:
    subject = request.headers.get("X-Minder-Principal") or os.environ.get(
        "PR_DEV_PRINCIPAL", "dev"
    )
    with db_session() as s:
        return load_principal(s, subject)
