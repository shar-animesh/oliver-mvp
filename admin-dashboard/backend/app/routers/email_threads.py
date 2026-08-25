# Path: app/routers/email_threads.py
# Description: Read-only administrative endpoints for Oliver email conversations.

"""Read-only admin endpoints for Oliver email communications."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.security import require_admin
from app.utils.models.api import (
    CanonicalAssessmentResponse,
    DimensionScoreResponse,
    EmailMessageResponse,
    EmailThreadDetailResponse,
    EmailThreadSummaryResponse,
    OliverRunResponse,
    RelatedIdeaResponse,
)
from app.utils.postgres import CanonicalAssessmentDb, EmailMessageDb, EmailThreadDb, OliverRunDb, OliverRunRelatedThreadDb, get_db

router = APIRouter(
    prefix="/api/v1/email-threads",
    tags=["email threads"],
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=List[EmailThreadSummaryResponse])
def list_email_threads(database: Session = Depends(get_db)) -> List[EmailThreadSummaryResponse]:  # noqa: B008
    """List email threads by latest activity."""
    message_counts = (
        select(
            EmailMessageDb.thread_id.label("thread_id"),
            func.count(EmailMessageDb.id).label("message_count"),
            func.max(EmailMessageDb.received_at).label("last_activity_at"),
        )
        .group_by(EmailMessageDb.thread_id)
        .subquery()
    )
    run_counts = (
        select(
            OliverRunDb.thread_id.label("thread_id"),
            func.count(OliverRunDb.id).label("run_count"),
        )
        .group_by(OliverRunDb.thread_id)
        .subquery()
    )
    assessment_counts = (
        select(OliverRunDb.thread_id.label("thread_id"), func.count(CanonicalAssessmentDb.run_id).label("assessment_count"))
        .join(CanonicalAssessmentDb, CanonicalAssessmentDb.run_id == OliverRunDb.id)
        .group_by(OliverRunDb.thread_id)
        .subquery()
    )
    latest_assessments = (
        select(
            OliverRunDb.thread_id.label("thread_id"),
            CanonicalAssessmentDb.composite_score,
            CanonicalAssessmentDb.current_stage,
            CanonicalAssessmentDb.gate_outcome,
            CanonicalAssessmentDb.rating,
            func.row_number().over(partition_by=OliverRunDb.thread_id, order_by=OliverRunDb.created_at.desc()).label("row_number"),
        )
        .join(OliverRunDb, OliverRunDb.id == CanonicalAssessmentDb.run_id)
        .subquery()
    )
    rows = database.execute(
        select(
            EmailThreadDb,
            message_counts.c.message_count,
            func.coalesce(run_counts.c.run_count, 0),
            func.coalesce(assessment_counts.c.assessment_count, 0),
            latest_assessments.c.composite_score,
            latest_assessments.c.current_stage,
            latest_assessments.c.gate_outcome,
            latest_assessments.c.rating,
            message_counts.c.last_activity_at,
        )
        .join(message_counts, message_counts.c.thread_id == EmailThreadDb.id)
        .outerjoin(run_counts, run_counts.c.thread_id == EmailThreadDb.id)
        .outerjoin(assessment_counts, assessment_counts.c.thread_id == EmailThreadDb.id)
        .outerjoin(
            latest_assessments,
            (latest_assessments.c.thread_id == EmailThreadDb.id) & (latest_assessments.c.row_number == 1),
        )
        .order_by(message_counts.c.last_activity_at.desc())
    ).all()
    return [
        EmailThreadSummaryResponse(
            id=thread.id,
            conversation_id=thread.conversation_id,
            subject=thread.subject,
            participant_email=thread.participant_email,
            message_count=message_count,
            run_count=run_count,
            assessment_count=assessment_count,
            canonical_score=canonical_score,
            di_stage=di_stage,
            gate_outcome=gate_outcome,
            rating=rating,
            last_activity_at=last_activity_at,
        )
        for thread, message_count, run_count, assessment_count, canonical_score, di_stage, gate_outcome, rating, last_activity_at in rows
    ]


@router.get("/{thread_id}", response_model=EmailThreadDetailResponse)
def get_email_thread(
    thread_id: UUID,
    database: Session = Depends(get_db),  # noqa: B008
) -> EmailThreadDetailResponse:
    """Return one complete email conversation and its Oliver decisions."""
    thread = database.scalar(
        select(EmailThreadDb)
        .where(EmailThreadDb.id == thread_id)
        .options(
            selectinload(EmailThreadDb.messages),
            selectinload(EmailThreadDb.runs).selectinload(OliverRunDb.assessment),
            selectinload(EmailThreadDb.runs).selectinload(OliverRunDb.delivery),
            selectinload(EmailThreadDb.runs).selectinload(OliverRunDb.related_threads).selectinload(OliverRunRelatedThreadDb.related_thread),
        )
    )
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email thread not found")

    return EmailThreadDetailResponse(
        id=thread.id,
        conversation_id=thread.conversation_id,
        subject=thread.subject,
        participant_email=thread.participant_email,
        embedding_model=thread.embedding_model,
        embedding_dimensions=thread.embedding_dimensions,
        embedded_at=thread.embedded_at,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=[
            EmailMessageResponse(
                id=message.id,
                direction=message.direction,
                sender_email=message.sender_email,
                recipient_emails=message.recipient_emails,
                subject=message.subject,
                content_html=message.content_html,
                received_at=message.received_at,
            )
            for message in thread.messages
        ],
        runs=[
            OliverRunResponse(
                id=run.id,
                action=run.action,
                model_name=run.model_name,
                subject=run.subject,
                delivery_status=run.delivery.status if run.delivery is not None else None,
                delivery_attempt_count=run.delivery.attempt_count if run.delivery is not None else 0,
                delivery_last_error=run.delivery.last_error if run.delivery is not None else None,
                delivered_at=run.delivery.delivered_at if run.delivery is not None else None,
                assessment=(
                    CanonicalAssessmentResponse(
                        current_stage=run.assessment.current_stage,
                        composite_score=run.assessment.composite_score,
                        transition_target=run.assessment.transition_target,
                        recommended_next_stage=run.assessment.recommended_next_stage,
                        gate_outcome=run.assessment.gate_outcome,
                        lifecycle_state=run.assessment.lifecycle_state,
                        composite_confidence=run.assessment.composite_confidence,
                        lowest_confidence_dimension=run.assessment.lowest_confidence_dimension,
                        requires_human_review=run.assessment.requires_human_review,
                        response_depth=run.assessment.response_depth,
                        rating=run.assessment.rating,
                        score_rationale=run.assessment.score_rationale,
                        transition_rationale=run.assessment.transition_rationale,
                        model_version=run.assessment.model_version,
                        weight_set_version=run.assessment.weight_set_version,
                        transition_policy_version=run.assessment.transition_policy_version,
                        dimensions=[DimensionScoreResponse.model_validate(dimension) for dimension in run.assessment.dimensions],
                        criteria=run.assessment.criteria,
                        created_at=run.assessment.created_at,
                    )
                    if run.assessment is not None
                    else None
                ),
                related_ideas=[
                    RelatedIdeaResponse(
                        thread_id=match.related_thread.id,
                        subject=match.related_thread.subject,
                        participant_email=match.related_thread.participant_email,
                        rank=match.rank,
                        cosine_distance=match.cosine_distance,
                    )
                    for match in run.related_threads
                ],
                prompt_tokens=run.prompt_tokens,
                completion_tokens=run.completion_tokens,
                created_at=run.created_at,
            )
            for run in thread.runs
        ],
    )
