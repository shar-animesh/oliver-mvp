# Path: app/routers/email_threads.py
# Description: Read-only administrative endpoints for Oliver email conversations.

"""Read-only admin endpoints for Oliver email communications."""

import re
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.security import require_admin
from app.utils.email_content import current_message_text, html_to_text
from app.utils.models.api import (
    CanonicalAssessmentResponse,
    DimensionScoreResponse,
    EmailMessageResponse,
    EmailThreadDetailResponse,
    EmailThreadSummaryResponse,
    OliverRunResponse,
    RelatedIdeaResponse,
)
from app.utils.postgres import CanonicalAssessmentDb, EmailMessageDb, EmailThreadDb, InitiativeDb, OliverRunDb, OliverRunRelatedThreadDb, get_db

router = APIRouter(
    prefix="/api/v1/email-threads",
    tags=["email threads"],
    dependencies=[Depends(require_admin)],
)


_REPLY_SUBJECT = re.compile(r"^(?:\s*\[[^\]]+\]\s*)*(?:re|reply)\s*:", re.IGNORECASE)
_FORWARD_SUBJECT = re.compile(r"^(?:\s*\[[^\]]+\]\s*)*(?:fw|fwd|forward)\s*:", re.IGNORECASE)
_FORWARDED_BODY = re.compile(r"(?:begin forwarded message|forwarded message|original message)", re.IGNORECASE)


def _message_kind(message: EmailMessageDb, *, is_followup_inbound: bool = False) -> str:
    """Classify a stored message using its direction, subject and body markers.

    The dashboard does not guess from a particular pilot or email address.  The
    Logic App currently persists the normalized subject/body, so this is a
    deterministic fallback until provider ``In-Reply-To``/forward headers are
    also persisted.  Outbound Oliver rows are always explicit responses.
    """
    if message.direction == "OUTBOUND":
        return "OLIVER_RESPONSE"
    subject = message.subject or ""
    if _FORWARD_SUBJECT.search(subject):
        return "FORWARDED"
    if _REPLY_SUBJECT.search(subject):
        return "REPLY"
    body_text = re.sub(r"<[^>]+>", " ", message.content_html or "")
    if _FORWARDED_BODY.search(body_text):
        return "FORWARDED"
    if is_followup_inbound:
        return "REPLY"
    return "NEW"


def _display_content(message: EmailMessageDb) -> str | None:
    """Hide quoted mail history while retaining the original body in storage.

    Outlook places the previous Oliver HTML response inside a participant's
    reply. Rendering the raw body made that quoted response look like a second
    Oliver decision in the dashboard. The ingestion record remains unchanged;
    this is only the reader-facing projection.
    """
    content = message.content_html
    if not content or message.direction != "INBOUND":
        return content
    full_text = html_to_text(content)
    authored_text = current_message_text(content)
    if not authored_text:
        return "<p><em>No new participant text; quoted message history is hidden.</em></p>"
    if authored_text == full_text:
        return content
    escaped = (
        authored_text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\n", "<br>")
    )
    return f"<div>{escaped}</div><p><em>Quoted message history hidden.</em></p>"


def _canonical_messages(thread: EmailThreadDb) -> List[EmailMessageDb]:
    """Return one visible outbound message per inbound message.

    Historical connector retries can leave several Oliver outbound rows for the
    same inbound message even though only one delivery reached Outlook. Keep
    the full run audit separately, but avoid presenting retry artifacts as
    multiple conversation replies in the admin UI.
    """
    inbound_messages: List[EmailMessageDb] = []
    unmatched_outbound: List[EmailMessageDb] = []
    outbound_by_inbound: dict[UUID, EmailMessageDb] = {}
    runs_by_id = {run.id: run for run in thread.runs}

    for message in thread.messages:
        if message.direction != "OUTBOUND" or not message.internet_message_id.startswith("oliver-run:"):
            if message.direction == "INBOUND":
                inbound_messages.append(message)
            else:
                unmatched_outbound.append(message)
            continue
        try:
            run_id = UUID(message.internet_message_id.removeprefix("oliver-run:"))
        except ValueError:
            unmatched_outbound.append(message)
            continue
        run = runs_by_id.get(run_id)
        if run is None:
            unmatched_outbound.append(message)
            continue
        previous = outbound_by_inbound.get(run.inbound_message_id)
        if previous is None or (message.received_at, message.id) > (previous.received_at, previous.id):
            outbound_by_inbound[run.inbound_message_id] = message

    visible = [*inbound_messages, *outbound_by_inbound.values(), *unmatched_outbound]
    return sorted(visible, key=lambda message: (message.received_at, message.id))


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
            func.row_number()
            .over(partition_by=OliverRunDb.thread_id, order_by=(OliverRunDb.created_at.desc(), OliverRunDb.id.desc()))
            .label("row_number"),
        )
        .join(OliverRunDb, OliverRunDb.id == CanonicalAssessmentDb.run_id)
        .subquery()
    )
    rows = database.execute(
        select(
            EmailThreadDb,
            InitiativeDb.id,
            InitiativeDb.title,
            InitiativeDb.current_stage,
            InitiativeDb.lifecycle_state,
            func.coalesce(message_counts.c.message_count, 0),
            func.coalesce(run_counts.c.run_count, 0),
            func.coalesce(assessment_counts.c.assessment_count, 0),
            latest_assessments.c.composite_score,
            latest_assessments.c.current_stage,
            latest_assessments.c.gate_outcome,
            latest_assessments.c.rating,
            func.coalesce(message_counts.c.last_activity_at, EmailThreadDb.updated_at),
        )
        .outerjoin(message_counts, message_counts.c.thread_id == EmailThreadDb.id)
        .outerjoin(InitiativeDb, InitiativeDb.id == EmailThreadDb.initiative_id)
        .outerjoin(run_counts, run_counts.c.thread_id == EmailThreadDb.id)
        .outerjoin(assessment_counts, assessment_counts.c.thread_id == EmailThreadDb.id)
        .outerjoin(
            latest_assessments,
            (latest_assessments.c.thread_id == EmailThreadDb.id) & (latest_assessments.c.row_number == 1),
        )
        .order_by(message_counts.c.last_activity_at.desc().nullslast(), EmailThreadDb.updated_at.desc(), EmailThreadDb.id.desc())
    ).all()
    return [
        EmailThreadSummaryResponse(
            id=thread.id,
            initiative_id=thread.initiative_id,
            initiative_title=initiative_title,
            conversation_id=thread.conversation_id,
            subject=thread.subject,
            participant_email=thread.participant_email,
            message_count=message_count,
            run_count=run_count,
            assessment_count=assessment_count,
            canonical_score=canonical_score,
            di_stage=initiative_stage or assessment_stage,
            assessment_stage=assessment_stage,
            initiative_current_stage=initiative_stage,
            initiative_lifecycle_state=initiative_lifecycle_state,
            gate_outcome=gate_outcome,
            rating=rating,
            last_activity_at=last_activity_at,
        )
        for (
            thread,
            initiative_id,
            initiative_title,
            initiative_stage,
            initiative_lifecycle_state,
            message_count,
            run_count,
            assessment_count,
            canonical_score,
            assessment_stage,
            gate_outcome,
            rating,
            last_activity_at,
        ) in rows
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
            selectinload(EmailThreadDb.initiative),
            selectinload(EmailThreadDb.runs).selectinload(OliverRunDb.assessment),
            selectinload(EmailThreadDb.runs).selectinload(OliverRunDb.delivery),
            selectinload(EmailThreadDb.runs).selectinload(OliverRunDb.related_threads).selectinload(OliverRunRelatedThreadDb.related_thread),
        )
    )
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email thread not found")

    # Older runs may have persisted the initiative on the canonical assessment
    # but not on the thread row.  Recover that linkage from run provenance so
    # the conversation still opens the correct pilot in the admin UI.
    initiative = thread.initiative
    if initiative is None:
        for run in sorted(thread.runs, key=lambda item: (item.created_at, item.id), reverse=True):
            assessment = run.assessment
            if assessment is not None and assessment.initiative_id is not None:
                initiative = database.get(InitiativeDb, assessment.initiative_id)
                if initiative is not None:
                    break

    visible_messages = _canonical_messages(thread)
    inbound_seen = 0

    def serialize_message(message: EmailMessageDb) -> EmailMessageResponse:
        nonlocal inbound_seen
        is_followup_inbound = message.direction == "INBOUND" and inbound_seen > 0
        if message.direction == "INBOUND":
            inbound_seen += 1
        return EmailMessageResponse(
            id=message.id,
            direction=message.direction,
            sender_email=message.sender_email,
            recipient_emails=message.recipient_emails,
            subject=message.subject,
            content_html=_display_content(message),
            received_at=message.received_at,
            message_kind=_message_kind(message, is_followup_inbound=is_followup_inbound),
        )

    return EmailThreadDetailResponse(
        id=thread.id,
        initiative_id=initiative.id if initiative is not None else thread.initiative_id,
        initiative_title=initiative.title if initiative is not None else None,
        initiative_current_stage=initiative.current_stage if initiative is not None else None,
        initiative_lifecycle_state=initiative.lifecycle_state if initiative is not None else None,
        conversation_id=thread.conversation_id,
        subject=thread.subject,
        participant_email=thread.participant_email,
        embedding_model=thread.embedding_model,
        embedding_dimensions=thread.embedding_dimensions,
        embedded_at=thread.embedded_at,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=[serialize_message(message) for message in visible_messages],
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
