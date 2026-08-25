"""Governed lifecycle commands owned by the Oliver workflow service."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import get_settings
from utils.lifecycle import LifecycleConflictError, LifecycleDecisionError, StageMaster
from utils.models.api import CadenceResponse, LifecycleDecisionRequest, LifecycleReasonRequest, LifecycleTransitionResult
from utils.pacer import Pacer
from utils.postgres import LifecycleTransitionDb, get_db
from utils.security import AdminPrincipal, require_lifecycle_approver, require_scheduler_service

router = APIRouter(prefix="/lifecycle", tags=["lifecycle"])
stage_master = StageMaster()
pacer = Pacer(stage_sla_days=get_settings().lifecycle_stage_sla_days)


def _result(transition: LifecycleTransitionDb) -> LifecycleTransitionResult:
    return LifecycleTransitionResult(
        id=transition.id,
        initiative_id=transition.initiative_id,
        transition_type=transition.transition_type,
        from_stage=transition.from_stage,
        to_stage=transition.to_stage,
        status=transition.status,
        reason=transition.reason,
        decided_by=transition.decided_by,
        decided_at=transition.decided_at,
    )


def _execute(database: Session, operation) -> LifecycleTransitionResult:
    try:
        transition = operation()
        database.commit()
        return _result(transition)
    except LifecycleDecisionError as error:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except LifecycleConflictError as error:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/initiatives/{initiative_id}/hold", response_model=LifecycleTransitionResult)
def hold_initiative(
    initiative_id: UUID,
    request: LifecycleReasonRequest,
    principal: AdminPrincipal = Depends(require_lifecycle_approver),  # noqa: B008
    database: Session = Depends(get_db),  # noqa: B008
) -> LifecycleTransitionResult:
    """Place an initiative on hold under recorded human authority."""
    return _execute(
        database,
        lambda: stage_master.hold(database, initiative_id=initiative_id, reason=request.reason, actor_id=principal.object_id),
    )


@router.post("/initiatives/{initiative_id}/resume", response_model=LifecycleTransitionResult)
def resume_initiative(
    initiative_id: UUID,
    request: LifecycleReasonRequest,
    principal: AdminPrincipal = Depends(require_lifecycle_approver),  # noqa: B008
    database: Session = Depends(get_db),  # noqa: B008
) -> LifecycleTransitionResult:
    """Resume an initiative while leaving older decisions for reassessment."""
    return _execute(
        database,
        lambda: stage_master.resume(database, initiative_id=initiative_id, reason=request.reason, actor_id=principal.object_id),
    )


@router.post("/transitions/{transition_id}/decision", response_model=LifecycleTransitionResult)
def decide_transition(
    transition_id: UUID,
    request: LifecycleDecisionRequest,
    principal: AdminPrincipal = Depends(require_lifecycle_approver),  # noqa: B008
    database: Session = Depends(get_db),  # noqa: B008
) -> LifecycleTransitionResult:
    """Approve or reject a pending DI5, No-Go, or policy-review proposal."""
    return _execute(
        database,
        lambda: stage_master.decide_transition(
            database,
            transition_id=transition_id,
            approve=request.decision == "APPROVE",
            reason=request.reason,
            actor_id=principal.object_id,
        ),
    )


@router.post(
    "/pacer/evaluate",
    response_model=list[CadenceResponse],
    dependencies=[Depends(require_scheduler_service)],
)
def evaluate_cadence(database: Session = Depends(get_db)) -> list[CadenceResponse]:  # noqa: B008
    """Run the deterministic scheduled cadence check."""
    snapshots = pacer.evaluate_all(database)
    database.commit()
    return [CadenceResponse(**snapshot.__dict__) for snapshot in snapshots]
