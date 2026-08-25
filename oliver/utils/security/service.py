"""Managed-identity authorization for Oliver service endpoints."""

import secrets

from fastapi import HTTPException, Request, status

from config import get_settings

from .entra import EntraPrincipal, require_entra_roles

settings = get_settings()


def _require_local_key(request: Request) -> None:
    supplied = request.headers.get("X-Internal-Api-Key", "")
    if not secrets.compare_digest(supplied, settings.INTERNAL_API_KEY.get_secret_value()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal API key")


def require_email_service(request: Request) -> EntraPrincipal | None:
    """Authorize Logic App by local key or its production managed-identity role."""
    if settings.SERVICE_AUTH_MODE == "entra":
        return require_entra_roles(request, settings.entra_email_service_roles)
    _require_local_key(request)
    return None


def require_scheduler_service(request: Request) -> EntraPrincipal | None:
    """Authorize scheduled lifecycle evaluation independently of email processing."""
    if settings.SERVICE_AUTH_MODE == "entra":
        return require_entra_roles(request, settings.entra_scheduler_service_roles)
    _require_local_key(request)
    return None


def require_scout_service(request: Request) -> EntraPrincipal | None:
    """Authorize an approved Scout connector workload."""
    if settings.SERVICE_AUTH_MODE == "entra":
        return require_entra_roles(request, settings.entra_scout_service_roles)
    _require_local_key(request)
    return None


def require_metrics_service(request: Request) -> EntraPrincipal | None:
    """Authorize an operational measurement connector workload."""
    if settings.SERVICE_AUTH_MODE == "entra":
        return require_entra_roles(request, settings.entra_metrics_service_roles)
    _require_local_key(request)
    return None
