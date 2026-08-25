"""Local-development and Entra role authorization for lifecycle commands."""

import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from config import get_settings

from .entra import require_entra_roles

settings = get_settings()


@dataclass(frozen=True)
class AdminPrincipal:
    """An authorized lifecycle user without any code-level personal allowlist."""

    identity: str
    object_id: str
    roles: frozenset[str]


def require_admin_identity(request: Request) -> AdminPrincipal:
    """Require local test authorization or an Entra admin application role."""
    if settings.ADMIN_AUTH_MODE == "entra":
        principal = require_entra_roles(
            request,
            settings.entra_admin_read_roles
            | settings.entra_lifecycle_approver_roles
            | settings.entra_insight_operator_roles
            | settings.entra_scout_reviewer_roles,
        )
        return AdminPrincipal(
            identity=principal.display_identity,
            object_id=principal.object_id,
            roles=principal.roles,
        )

    supplied_key = request.headers.get("X-Internal-Api-Key", "")
    configured_key = settings.ADMIN_GATEWAY_API_KEY.get_secret_value() or settings.INTERNAL_API_KEY.get_secret_value()
    if not supplied_key or not configured_key or not secrets.compare_digest(supplied_key.encode("utf-8"), configured_key.encode("utf-8")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal API key")
    normalized = request.headers.get("X-Oliver-Admin-Identity", "").strip().casefold()
    if normalized not in settings.admin_identities:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin identity is not authorized")
    return AdminPrincipal(identity=normalized, object_id=f"local:{normalized}", roles=frozenset())


def require_lifecycle_approver(
    principal: AdminPrincipal = Depends(require_admin_identity),  # noqa: B008
) -> AdminPrincipal:
    """Require explicit lifecycle-decision authority."""
    if settings.ADMIN_AUTH_MODE == "entra":
        authorized = bool(principal.roles.intersection(settings.entra_lifecycle_approver_roles))
    else:
        authorized = principal.identity in settings.lifecycle_approver_identities
    if not authorized:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lifecycle approval authority is required")
    return principal


def require_insight_operator(
    principal: AdminPrincipal = Depends(require_admin_identity),  # noqa: B008
) -> AdminPrincipal:
    """Require authority to run model-backed portfolio or sandbox analysis."""
    if settings.ADMIN_AUTH_MODE == "entra":
        authorized = bool(principal.roles.intersection(settings.entra_insight_operator_roles))
    else:
        authorized = principal.identity in settings.admin_identities
    if not authorized:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Assessment test authority is required")
    return principal


def require_scout_reviewer(
    principal: AdminPrincipal = Depends(require_admin_identity),  # noqa: B008
) -> AdminPrincipal:
    """Require authority to promote or dismiss discovered Scout candidates."""
    if settings.ADMIN_AUTH_MODE == "entra":
        authorized = bool(principal.roles.intersection(settings.entra_scout_reviewer_roles))
    else:
        authorized = principal.identity in settings.admin_identities
    if not authorized:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Scout review authority is required")
    return principal
