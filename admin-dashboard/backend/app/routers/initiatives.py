# Path: app/routers/initiatives.py
# Description: Authenticated read-only initiative and lifecycle endpoints.

"""Authenticated, read-only portfolio and lifecycle endpoints."""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from app.security import require_admin
from app.utils.models.api import (
    AuditEventResponse,
    EvidenceVersionResponse,
    InitiativeAssessmentSummary,
    InitiativeDetailResponse,
    InitiativeSummaryResponse,
    InitiativeThreadResponse,
    LifecycleTransitionResponse,
)
from app.utils.postgres import (
    AuditEventDb,
    CanonicalAssessmentDb,
    EmailThreadDb,
    EvidenceVersionDb,
    InitiativeDb,
    LifecycleTransitionDb,
    get_db,
)

router = APIRouter(
    prefix="/api/v1/initiatives",
    tags=["initiatives"],
    dependencies=[Depends(require_admin)],
)

_STAGE_NAMES = {
    "DI1": "Concept",
    "DI2": "Pilot",
    "DI3": "Test",
    "DI4": "Implement",
    "DI5": "Scale",
}


def _summary_rows(database: Session, initiative_id: Optional[UUID] = None) -> List[Row]:
    evidence_counts = (
        select(EvidenceVersionDb.initiative_id, func.count(EvidenceVersionDb.id).label("evidence_version_count"))
        .group_by(EvidenceVersionDb.initiative_id)
        .subquery()
    )
    review_counts = (
        select(LifecycleTransitionDb.initiative_id, func.count(LifecycleTransitionDb.id).label("pending_review_count"))
        .where(LifecycleTransitionDb.status == "PENDING")
        .group_by(LifecycleTransitionDb.initiative_id)
        .subquery()
    )
    latest_assessment = (
        select(
            CanonicalAssessmentDb.initiative_id,
            CanonicalAssessmentDb.composite_score,
            CanonicalAssessmentDb.gate_outcome,
            CanonicalAssessmentDb.rating,
            CanonicalAssessmentDb.created_at,
            func.row_number()
            .over(
                partition_by=CanonicalAssessmentDb.initiative_id,
                order_by=CanonicalAssessmentDb.created_at.desc(),
            )
            .label("row_number"),
        )
        .where(CanonicalAssessmentDb.initiative_id.is_not(None))
        .subquery()
    )
    statement = (
        select(
            InitiativeDb,
            func.coalesce(evidence_counts.c.evidence_version_count, 0),
            func.coalesce(review_counts.c.pending_review_count, 0),
            latest_assessment.c.composite_score,
            latest_assessment.c.gate_outcome,
            latest_assessment.c.rating,
            latest_assessment.c.created_at,
        )
        .outerjoin(evidence_counts, evidence_counts.c.initiative_id == InitiativeDb.id)
        .outerjoin(review_counts, review_counts.c.initiative_id == InitiativeDb.id)
        .outerjoin(
            latest_assessment,
            (latest_assessment.c.initiative_id == InitiativeDb.id) & (latest_assessment.c.row_number == 1),
        )
        .order_by(InitiativeDb.updated_at.desc())
    )
    if initiative_id is not None:
        statement = statement.where(InitiativeDb.id == initiative_id)
    return database.execute(statement).all()


def _to_summary(row: Row) -> InitiativeSummaryResponse:
    initiative, evidence_count, review_count, score, gate, rating, assessed_at = row
    days_in_stage = max(0, (datetime.now(timezone.utc) - initiative.stage_entered_at).days)
    return InitiativeSummaryResponse(
        id=initiative.id,
        title=initiative.title,
        owner_email=initiative.owner_email,
        current_stage=initiative.current_stage,
        stage_name=_STAGE_NAMES.get(initiative.current_stage, initiative.current_stage),
        lifecycle_state=initiative.lifecycle_state,
        is_on_hold=initiative.is_on_hold,
        hold_reason=initiative.hold_reason,
        version=initiative.version,
        days_in_stage=days_in_stage,
        evidence_version_count=evidence_count,
        pending_review_count=review_count,
        latest_score=score,
        latest_gate_outcome=gate,
        latest_rating=rating,
        latest_assessment_at=assessed_at,
        stage_entered_at=initiative.stage_entered_at,
        updated_at=initiative.updated_at,
    )


@router.get("", response_model=List[InitiativeSummaryResponse])
def list_initiatives(database: Session = Depends(get_db)) -> List[InitiativeSummaryResponse]:  # noqa: B008
    """List authoritative initiatives, including review and evidence status."""
    return [_to_summary(row) for row in _summary_rows(database)]


@router.get("/{initiative_id}", response_model=InitiativeDetailResponse)
def get_initiative(
    initiative_id: UUID,
    database: Session = Depends(get_db),  # noqa: B008
) -> InitiativeDetailResponse:
    """Return one initiative's assessment, evidence, transition, and audit history."""
    rows = _summary_rows(database, initiative_id)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Initiative not found")
    summary = _to_summary(rows[0])
    initiative = rows[0][0]
    threads = list(database.scalars(select(EmailThreadDb).where(EmailThreadDb.initiative_id == initiative_id)))
    assessments = list(
        database.scalars(
            select(CanonicalAssessmentDb)
            .where(CanonicalAssessmentDb.initiative_id == initiative_id)
            .order_by(CanonicalAssessmentDb.created_at.desc())
        )
    )
    evidence_versions = list(
        database.scalars(select(EvidenceVersionDb).where(EvidenceVersionDb.initiative_id == initiative_id).order_by(EvidenceVersionDb.version.desc()))
    )
    transitions = list(
        database.scalars(
            select(LifecycleTransitionDb)
            .where(LifecycleTransitionDb.initiative_id == initiative_id)
            .order_by(LifecycleTransitionDb.created_at.desc())
        )
    )
    events = list(
        database.scalars(select(AuditEventDb).where(AuditEventDb.initiative_id == initiative_id).order_by(AuditEventDb.occurred_at.desc()).limit(500))
    )
    return InitiativeDetailResponse(
        **summary.model_dump(),
        created_at=initiative.created_at,
        threads=[InitiativeThreadResponse.model_validate(thread, from_attributes=True) for thread in threads],
        assessments=[
            InitiativeAssessmentSummary(
                run_id=assessment.run_id,
                evidence_version_id=assessment.evidence_version_id,
                current_stage=assessment.current_stage,
                composite_score=assessment.composite_score,
                transition_target=assessment.transition_target,
                recommended_next_stage=assessment.recommended_next_stage,
                gate_outcome=assessment.gate_outcome,
                rating=assessment.rating,
                requires_human_review=assessment.requires_human_review,
                transition_policy_version=assessment.transition_policy_version,
                created_at=assessment.created_at,
            )
            for assessment in assessments
        ],
        evidence_versions=[EvidenceVersionResponse.model_validate(version, from_attributes=True) for version in evidence_versions],
        transitions=[LifecycleTransitionResponse.model_validate(transition, from_attributes=True) for transition in transitions],
        audit_events=[AuditEventResponse.model_validate(event, from_attributes=True) for event in events],
    )
