"""User authentication models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class User(BaseModel):
    """Represents an authenticated user account."""

    id: int
    username: str  # maps to display_name in DB
    email: str
    password_hash: Optional[str] = None
    created_at: datetime = datetime.utcnow()
    role: str = "user"
