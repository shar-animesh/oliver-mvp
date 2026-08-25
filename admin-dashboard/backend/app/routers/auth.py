# Path: app/routers/auth.py
# Description: Local-development sign-in and production Entra session endpoints.

"""Local admin sign-in surface, replaceable by Entra in production."""

import base64
import hashlib
import hmac
from typing import List

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.security import require_admin

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
settings = get_settings()


class LoginRequest(BaseModel):
    """Local-only interactive credentials."""

    username: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class AdminSessionResponse(BaseModel):
    """Authenticated dashboard identity."""

    username: str
    roles: List[str]


def _decode_base64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, expected_text = encoded_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        if iterations < 600_000:
            return False
        salt = _decode_base64url(salt_text)
        expected = _decode_base64url(expected_text)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


@router.post("/login", response_model=AdminSessionResponse)
def login(credentials: LoginRequest, request: Request) -> AdminSessionResponse:
    """Create a signed local session for an allowlisted admin."""
    if settings.ADMIN_AUTH_MODE != "local":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local authentication is disabled")
    username = credentials.username.strip().casefold()
    encoded_hash = settings.local_user_hashes.get(username)
    if encoded_hash is None or not _verify_password(credentials.password, encoded_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    request.session.clear()
    request.session["admin_username"] = username
    return AdminSessionResponse(username=username, roles=sorted(settings.local_roles))


@router.get("/me", response_model=AdminSessionResponse)
def current_session(request: Request) -> AdminSessionResponse:
    """Return the active signed-in admin."""
    principal = require_admin(request)
    return AdminSessionResponse(username=principal.username, roles=sorted(principal.roles))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> None:
    """Remove the active dashboard session."""
    request.session.clear()
