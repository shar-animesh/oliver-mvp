"""Microsoft Entra access-token validation shared by user and service roles."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from config import get_settings

settings = get_settings()


@dataclass(frozen=True)
class EntraPrincipal:
    """Verified Entra workload or user identity."""

    object_id: str
    display_identity: str
    roles: frozenset[str]


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    if not settings.ENTRA_TENANT_ID:
        raise RuntimeError("ENTRA_TENANT_ID is not configured")
    return PyJWKClient(
        f"https://login.microsoftonline.com/{settings.ENTRA_TENANT_ID}/discovery/v2.0/keys",
        cache_keys=True,
        cache_jwk_set=True,
        lifespan=3600,
    )


def require_entra_roles(request: Request, required_roles: set[str]) -> EntraPrincipal:
    """Validate an Entra bearer token and require at least one application role."""
    if not settings.ENTRA_TENANT_ID or not settings.ENTRA_API_CLIENT_ID:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Entra authentication is not configured")
    scheme, separator, token = request.headers.get("Authorization", "").partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Entra bearer token required")
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.ENTRA_API_CLIENT_ID,
            issuer=f"https://login.microsoftonline.com/{settings.ENTRA_TENANT_ID}/v2.0",
            options={"require": ["exp", "iat", "iss", "aud", "oid"]},
        )
    except (PyJWTError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired Entra token") from error
    roles = frozenset(role for role in claims.get("roles", []) if isinstance(role, str))
    if not roles.intersection(required_roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Required Oliver application role is missing")
    object_id = str(claims["oid"])
    identity = str(claims.get("preferred_username") or claims.get("name") or claims.get("azp") or object_id)
    return EntraPrincipal(object_id=object_id, display_identity=identity, roles=roles)
