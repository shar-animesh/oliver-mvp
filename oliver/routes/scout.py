"""Managed-source discovery and human-governed Scout review endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from openai import APIError
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from utils.agents import ScoutAgent, ScoutWorkflow
from utils.model_provider import get_model_client
from utils.models.api import (
    ScoutCandidateResponse,
    ScoutDiscoveryRequest,
    ScoutDiscoveryResponse,
    ScoutDismissRequest,
    ScoutPromotionResponse,
)
from utils.postgres import ScoutCandidateDb, get_db
from utils.security import AdminPrincipal, require_admin_identity, require_scout_reviewer, require_scout_service
from utils.security.entra import EntraPrincipal

settings = get_settings()
router = APIRouter(prefix="/scout", tags=["scout"])
scout_agent = ScoutAgent(
    client=get_model_client(),
    model=settings.OPENAI_MODEL,
    reasoning_effort=settings.OPENAI_REASONING_EFFORT,
    approved_sources=settings.scout_approved_source_systems,
    minimum_confidence=settings.SCOUT_MIN_CONFIDENCE,
)
scout_workflow = ScoutWorkflow()


@router.post("/discover", response_model=ScoutDiscoveryResponse)
def discover_candidates(
    request: ScoutDiscoveryRequest,
    service_principal: EntraPrincipal | None = Depends(require_scout_service),  # noqa: B008
    database: Session = Depends(get_db),  # noqa: B008
) -> ScoutDiscoveryResponse:
    """Classify a bounded batch from one approved managed source."""
    actor_id = service_principal.object_id if service_principal is not None else "local:scout-service"
    try:
        result = scout_agent.discover(database, request=request, actor_id=actor_id)
        database.commit()
    except ValueError as error:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except (APIError, RuntimeError, TypeError, KeyError) as error:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Scout discovery could not be completed") from error
    return ScoutDiscoveryResponse(
        created_count=result.created_count,
        candidates=[ScoutCandidateResponse.model_validate(candidate) for candidate in result.candidates],
    )


@router.get("/candidates", response_model=list[ScoutCandidateResponse])
def list_candidates(
    candidate_status: str | None = Query(default=None, alias="status"),  # noqa: B008
    _principal: AdminPrincipal = Depends(require_admin_identity),  # noqa: B008
    database: Session = Depends(get_db),  # noqa: B008
) -> list[ScoutCandidateResponse]:
    """List the Scout review queue without exposing original source payloads."""
    statement = select(ScoutCandidateDb).order_by(ScoutCandidateDb.discovered_at.desc())
    if candidate_status is not None:
        statement = statement.where(ScoutCandidateDb.status == candidate_status.upper())
    return [ScoutCandidateResponse.model_validate(candidate) for candidate in database.scalars(statement)]


@router.post("/candidates/{candidate_id}/promote", response_model=ScoutPromotionResponse)
def promote_candidate(
    candidate_id: UUID,
    principal: AdminPrincipal = Depends(require_scout_reviewer),  # noqa: B008
    database: Session = Depends(get_db),  # noqa: B008
) -> ScoutPromotionResponse:
    """Promote one reviewed candidate into a DI1 canonical initiative."""
    try:
        candidate, initiative = scout_workflow.promote(database, candidate_id=candidate_id, actor_id=principal.object_id)
        database.commit()
    except ValueError as error:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return ScoutPromotionResponse(candidate=ScoutCandidateResponse.model_validate(candidate), initiative_id=initiative.id)


@router.post("/candidates/{candidate_id}/dismiss", response_model=ScoutCandidateResponse)
def dismiss_candidate(
    candidate_id: UUID,
    request: ScoutDismissRequest,
    principal: AdminPrincipal = Depends(require_scout_reviewer),  # noqa: B008
    database: Session = Depends(get_db),  # noqa: B008
) -> ScoutCandidateResponse:
    """Dismiss one candidate with an immutable audit reason."""
    try:
        candidate = scout_workflow.dismiss(
            database,
            candidate_id=candidate_id,
            actor_id=principal.object_id,
            reason=request.reason,
        )
        database.commit()
    except ValueError as error:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return ScoutCandidateResponse.model_validate(candidate)
