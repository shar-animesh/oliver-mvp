# Path: app/security.py
# Description: Local-session and Microsoft Entra authorization for dashboard routes.

"""Local-session and Microsoft Entra authorization for dashboard routes."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, FrozenSet

import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from app.config import get_settings

settings = get_settings()


@dataclass(frozen=True)
class AdminPrincipal:
    """The authenticated person operating the admin dashboard."""

    username: str
    object_id: str
    roles: FrozenSet[str]


@lru_cache(maxsize=1)
def _entra_jwks_client() -> PyJWKClient:
    if not settings.ENTRA_TENANT_ID:
        raise RuntimeError("ENTRA_TENANT_ID is required when ADMIN_AUTH_MODE=entra")
    return PyJWKClient(
        f"https://login.microsoftonline.com/{settings.ENTRA_TENANT_ID}/discovery/v2.0/keys",
        cache_keys=True,
        cache_jwk_set=True,
        lifespan=3600,
    )


def _entra_principal(token: str) -> AdminPrincipal:
    if not settings.ENTRA_TENANT_ID or not settings.ENTRA_CLIENT_ID:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Entra authentication is not configured")
    try:
        signing_key = _entra_jwks_client().get_signing_key_from_jwt(token)
        claims: Dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.ENTRA_CLIENT_ID,
            issuer=f"https://login.microsoftonline.com/{settings.ENTRA_TENANT_ID}/v2.0",
            options={"require": ["exp", "iat", "iss", "aud", "oid", "scp"]},
        )
    except (PyJWTError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired Entra token") from error
    scopes = {scope for scope in str(claims["scp"]).split() if scope}
    if settings.ENTRA_REQUIRED_SCOPE not in scopes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Required Oliver API scope is missing")
    roles = frozenset(role for role in claims.get("roles", []) if isinstance(role, str))
    if not roles.intersection(settings.entra_admin_read_roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Oliver admin read role is required")
    object_id = str(claims["oid"])
    username = str(claims.get("preferred_username") or claims.get("name") or object_id)
    return AdminPrincipal(username=username, object_id=object_id, roles=roles)


def require_admin(request: Request) -> AdminPrincipal:
    """Require local signed-session auth or a role-bearing Entra access token."""
    if settings.ADMIN_AUTH_MODE == "entra":
        scheme, separator, token = request.headers.get("Authorization", "").partition(" ")
        if not separator or scheme.casefold() != "bearer" or not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Entra bearer token required")
        return _entra_principal(token)

    username = request.session.get("admin_username")
    if not isinstance(username, str) or not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin authentication required")
    return AdminPrincipal(username=username, object_id=f"local:{username}", roles=frozenset(settings.local_roles))
