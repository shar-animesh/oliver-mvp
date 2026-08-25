# Path: app/routers/commands.py
# Description: Authorized command gateway to the Oliver workflow API.

"""Authorized command gateway to Oliver's independently deployed workflow API."""

from typing import Dict, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.security import AdminPrincipal, require_admin

router = APIRouter(prefix="/api/v1/commands", tags=["commands"])
settings = get_settings()


class AssessmentTestRequest(BaseModel):
    """Non-persistent evidence submitted to Oliver's assessment laboratory."""

    subject: str = Field(min_length=3, max_length=200)
    evidence: str = Field(min_length=20, max_length=120_000)
    current_stage: Literal["DI1", "DI2", "DI3", "DI4", "DI5"] = "DI1"


def _oliver_headers(request: Request, principal: AdminPrincipal) -> Dict[str, str]:
    if settings.ADMIN_AUTH_MODE == "entra":
        return {"Authorization": request.headers.get("Authorization", "")}
    return {
        "X-Internal-Api-Key": settings.OLIVER_INTERNAL_API_KEY.get_secret_value(),
        "X-Oliver-Admin-Identity": principal.username,
    }


@router.post("/assessment-test")
async def run_assessment_test(
    payload: AssessmentTestRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_admin),  # noqa: B008
) -> Dict[str, object]:
    """Forward a role-checked sandbox assessment; no canonical records are mutated."""
    if not principal.roles.intersection({"Oliver.Assessment.Test", "Oliver.Platform.Admin"}):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Assessment test authority is required")
    try:
        async with httpx.AsyncClient(timeout=settings.OLIVER_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.OLIVER_API_URL.rstrip('/')}/api/v1/assessment/test",
                headers=_oliver_headers(request, principal),
                json=payload.model_dump(),
            )
    except httpx.TimeoutException as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(f"Oliver did not complete the assessment within {settings.OLIVER_REQUEST_TIMEOUT_SECONDS} seconds"),
        ) from error
    except httpx.ConnectError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The admin API could not connect to the configured Oliver workflow endpoint",
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The request to Oliver failed: {type(error).__name__}",
        ) from error
    if response.is_error:
        detail = "Oliver could not complete the assessment test"
        try:
            detail = str(response.json().get("detail") or detail)
        except (ValueError, AttributeError):
            pass
        raise HTTPException(status_code=response.status_code, detail=detail)
    try:
        result = response.json()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Oliver returned a non-JSON assessment result",
        ) from error
    if not isinstance(result, dict):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Oliver returned an invalid assessment result")
    return result
