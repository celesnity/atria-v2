"""Authentication API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Response, Request, status
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel

from atria.web.state import get_state

SECRET_KEY = "change-me"
TOKEN_COOKIE = "atria_session"
TOKEN_TTL_SECONDS = 60 * 60 * 24

serializer = URLSafeTimedSerializer(SECRET_KEY)


class AuthResponse(BaseModel):
    username: str
    email: Optional[str] = None
    role: str
    workspace_path: Optional[str] = None
    project_id: Optional[int] = None


class LoginRequest(BaseModel):
    email: str


router = APIRouter(prefix="/api/auth", tags=["auth"])


def create_token(user_id: str) -> str:
    return serializer.dumps({"sub": user_id, "ts": datetime.utcnow().isoformat()})


def verify_token(token: str) -> str:
    try:
        data = serializer.loads(token, max_age=TOKEN_TTL_SECONDS)
        return data["sub"]
    except BadSignature as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, response: Response) -> AuthResponse:
    email = payload.email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    state = get_state()
    user_store = state.user_store

    user = await user_store.get_by_email(email)
    if not user:
        username = email.split("@")[0]
        base = username
        counter = 1
        while await user_store.get_by_username(username):
            username = f"{base}{counter}"
            counter += 1
        user = await user_store.create_user(username, password_hash="", email=email)

    # Bootstrap (or refresh) the user's workspace directory + project row.
    # Idempotent: safe to call every login.
    from atria.web.dependencies.workspace import ensure_user_workspace

    workspace = await ensure_user_workspace(user.id)

    token = create_token(str(user.id))
    response.set_cookie(
        TOKEN_COOKIE, token, httponly=True, samesite="lax", max_age=TOKEN_TTL_SECONDS
    )
    return AuthResponse(
        username=user.username,
        email=user.email,
        role=user.role,
        workspace_path=str(workspace.workspace_path),
        project_id=workspace.project_id,
    )


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(TOKEN_COOKIE)
    return {"status": "success"}


@router.get("/me", response_model=AuthResponse)
async def get_me(request: Request) -> AuthResponse:
    token = request.cookies.get(TOKEN_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id_str = verify_token(token)
    state = get_state()
    user = await state.user_store.get_by_id(int(user_id_str))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    from atria.web.dependencies.workspace import ensure_user_workspace

    workspace = await ensure_user_workspace(user.id)
    return AuthResponse(
        username=user.username,
        email=user.email,
        role=user.role,
        workspace_path=str(workspace.workspace_path),
        project_id=workspace.project_id,
    )
