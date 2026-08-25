"""Sentinel metric ingestion and Realizer value reconciliation endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from utils.lifecycle import LifecycleConflictError
from utils.models.api import (
    MetricDefinitionRequest,
    MetricDefinitionResponse,
    MetricObservationRequest,
    MetricObservationResponse,
    ValueRealizationResponse,
)
from utils.operations import Realizer, Sentinel, threshold_breached
from utils.postgres import get_db
from utils.security import AdminPrincipal, require_admin_identity, require_lifecycle_approver, require_metrics_service
from utils.security.entra import EntraPrincipal

router = APIRouter(prefix="/operations", tags=["operations"])
sentinel = Sentinel()
realizer = Realizer()


@router.post("/initiatives/{initiative_id}/metrics", response_model=MetricDefinitionResponse)
def define_metric(
    initiative_id: UUID,
    request: MetricDefinitionRequest,
    principal: AdminPrincipal = Depends(require_lifecycle_approver),  # noqa: B008
    database: Session = Depends(get_db),  # noqa: B008
) -> MetricDefinitionResponse:
    """Create an idempotent governed metric definition for DI3-DI5."""
    try:
        metric = sentinel.define_metric(
            database,
            initiative_id=initiative_id,
            name=request.name,
            metric_type=request.metric_type,
            unit=request.unit,
            direction=request.direction,
            threshold=request.threshold,
            baseline=request.baseline,
            source_system=request.source_system,
            actor_id=principal.object_id,
        )
        database.commit()
    except ValueError as error:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return MetricDefinitionResponse.model_validate(metric)


@router.post("/metrics/{metric_id}/observations", response_model=MetricObservationResponse)
def record_observation(
    metric_id: UUID,
    request: MetricObservationRequest,
    service_principal: EntraPrincipal | None = Depends(require_metrics_service),  # noqa: B008
    database: Session = Depends(get_db),  # noqa: B008
) -> MetricObservationResponse:
    """Store one source measurement and emit a deterministic alert on breach."""
    actor_id = service_principal.object_id if service_principal is not None else "local:metrics-service"
    try:
        observation, alert = sentinel.record_observation(
            database,
            metric_id=metric_id,
            idempotency_key=request.idempotency_key,
            value=request.value,
            source_system=request.source_system,
            source_reference=request.source_reference,
            observed_at=request.observed_at,
            metadata=request.metadata,
            actor_id=actor_id,
        )
        database.commit()
    except LifecycleConflictError as error:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except ValueError as error:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    breached = threshold_breached(
        value=observation.value,
        threshold=observation.metric.threshold,
        direction=observation.metric.direction,
    )
    return MetricObservationResponse(
        id=observation.id,
        metric_id=observation.metric_id,
        value=observation.value,
        observed_at=observation.observed_at,
        breached=breached,
        alert_id=alert.id if alert is not None else None,
    )


@router.get("/initiatives/{initiative_id}/realized-value", response_model=list[ValueRealizationResponse])
def realized_value(
    initiative_id: UUID,
    _principal: AdminPrincipal = Depends(require_admin_identity),  # noqa: B008
    database: Session = Depends(get_db),  # noqa: B008
) -> list[ValueRealizationResponse]:
    """Return exact latest actual-versus-target value metrics."""
    return [ValueRealizationResponse(**result.__dict__) for result in realizer.summarize(database, initiative_id=initiative_id)]
