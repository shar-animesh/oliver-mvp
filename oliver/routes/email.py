# Path: routes/email.py
# Description: Internal email-response route called by the Logic App.

import re
from datetime import datetime, timezone
from html import escape
from typing import cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from openai import APIError
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from utils.agents import (
    AgentContractError,
    AssessmentAgent,
    AssessmentRequest,
    CoachAgent,
    build_assessment_agent,
    canonical_assessment_context,
    render_coach_response,
)
from utils.attachments import AttachmentService, AttachmentValidationError, AzureBlobAttachmentStore, FileSystemAttachmentStore
from utils.email_content import current_message_text, html_to_text
from utils.herald import Herald
from utils.lifecycle import StageMaster
from utils.model_provider import get_model_client
from utils.models.api import (
    DeliveryInstructionResponse,
    DeliveryResultRequest,
    DeliveryStatusResponse,
    EmailResponseRequest,
    EmailResponseResult,
)
from utils.postgres import CanonicalAssessmentDb, EmailMessageDb, EmailThreadDb, OliverRunDb, OliverRunRelatedThreadDb, get_db
from utils.registrar import Registrar
from utils.scoring.models import CanonicalAssessment, DIStage
from utils.scoring.persistence import assessment_record
from utils.security import require_email_service
from utils.tools.tool_handlers import INTERNAL_EMAIL_DOMAIN, generate_embedding

settings = get_settings()

MAX_TOOL_ROUNDS = 8


def _canonical_message_id(value: str) -> str:
    """Normalize provider message IDs so transport formatting cannot defeat idempotency."""
    return value.strip().strip("<>").strip().lower()


def _normalized_header(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


_REPLY_SUBJECT = re.compile(r"^(?:(?:re|reply)\s*:\s*)+", re.IGNORECASE)
_FORWARD_SUBJECT = re.compile(r"^(?:(?:fw|fwd|forward)\s*:\s*)+", re.IGNORECASE)


def _normalized_subject(value: str | None) -> str:
    """Compare subjects independently of the prefixes added by mail clients."""
    subject = (value or "").strip()
    previous = None
    while subject and subject != previous:
        previous = subject
        subject = _REPLY_SUBJECT.sub("", subject).strip()
        subject = _FORWARD_SUBJECT.sub("", subject).strip()
    return _normalized_header(subject)


def _looks_like_reply(request: EmailResponseRequest) -> bool:
    """Identify a reply even when the connector supplies a new conversation ID."""
    if _REPLY_SUBJECT.search(request.subject or ""):
        return True
    body = html_to_text(request.email_thread)
    authored = current_message_text(request.email_thread)
    if authored and _normalized_header(authored) != _normalized_header(body):
        return True
    return bool(re.search(r"(?:original message|forwarded message|on .+ wrote:|^from:\s)", body, re.IGNORECASE | re.MULTILINE))


def _find_existing_reply_thread(database: Session, request: EmailResponseRequest) -> EmailThreadDb | None:
    """Resolve a reply to its existing thread when Graph's conversation ID changes.

    Microsoft connectors normally preserve ``conversationId``. Some flows instead
    provide an item-scoped ID for replies. A normalized subject/participant match
    is used only for messages that contain reply/quoted-history markers and only
    against threads that already have an Oliver outbound response.
    """
    if not _looks_like_reply(request):
        return None
    candidates = database.scalars(select(EmailThreadDb).where(EmailThreadDb.participant_email.ilike(request.sender_email or ""))).all()
    for candidate in sorted(candidates, key=lambda item: (item.updated_at, item.id), reverse=True):
        if _normalized_subject(candidate.subject) != _normalized_subject(request.subject):
            continue
        has_oliver_response = any(message.direction == "OUTBOUND" for message in candidate.messages)
        if has_oliver_response:
            return candidate
    return None


def _participant_display_name(sender_email: str | None, sender_name: str | None = None) -> str | None:
    """Return a safe participant name for conversational context.

    Microsoft Graph can provide a display name, but older Logic App payloads
    only contain an address.  In that case derive a readable fallback from the
    local part without ever inventing a name from the email body.
    """
    supplied = " ".join((sender_name or "").split()).strip()
    if supplied:
        return supplied[:320]
    local_part = (sender_email or "").split("@", 1)[0]
    parts = [part for part in re.split(r"[._\-]+", local_part) if part]
    if not parts or all(part.casefold() in {"info", "support", "admin", "noreply", "no", "reply"} for part in parts):
        return None
    return " ".join(part[:1].upper() + part[1:] for part in parts)[:320]


def _is_replayed_message(
    existing: EmailMessageDb,
    *,
    message_id: str,
    sender_email: str | None,
    subject: str | None,
    content_html: str,
    received_at: datetime,
) -> bool:
    """Recognize a provider replay even when it supplied a different item ID.

    Outlook/Logic App retries normally preserve ``internetMessageId``.  Some
    connectors fall back to a per-item ID, though, which previously created a
    second Oliver run for the same message. A normalized
    sender/subject/authored-body match is a safe secondary key for that case.
    A genuinely new email should have its own stable provider ID; suppressing
    an ID-less replay is preferable to creating a second assessment and
    outbound reply.
    """
    if _canonical_message_id(existing.internet_message_id) == _canonical_message_id(message_id):
        return True
    if existing.direction != "INBOUND":
        return False
    if _normalized_header(existing.sender_email) != _normalized_header(sender_email):
        return False
    if _normalized_subject(existing.subject) != _normalized_subject(subject):
        return False
    # Outlook replies frequently include a quoted copy of Oliver's previous
    # HTML response. Compare only the sender-authored portion so connector
    # retries remain idempotent even when quote markup or tracking wrappers
    # change between attempts.
    if _normalized_header(current_message_text(existing.content_html or "")) != _normalized_header(current_message_text(content_html)):
        return False
    return True


client = get_model_client()
assessment_agent: AssessmentAgent = build_assessment_agent(
    client=client,
    mode=settings.ASSESSMENT_EVALUATOR_MODE,
    model=settings.OPENAI_MODEL,
    reasoning_effort=settings.ASSESSMENT_REASONING_EFFORT,
    max_evidence_chars=settings.ASSESSMENT_MAX_EVIDENCE_CHARS,
    request_timeout_seconds=settings.OPENAI_REQUEST_TIMEOUT_SECONDS,
    response_retries=settings.ASSESSMENT_RESPONSE_RETRIES,
)
registrar = Registrar()
stage_master = StageMaster()
herald = Herald()
if settings.ATTACHMENT_STORE == "azure_blob":
    if not settings.AZURE_STORAGE_ACCOUNT_URL:
        raise RuntimeError("AZURE_STORAGE_ACCOUNT_URL is required when ATTACHMENT_STORE=azure_blob")
    attachment_store = AzureBlobAttachmentStore(
        account_url=settings.AZURE_STORAGE_ACCOUNT_URL,
        container=settings.AZURE_STORAGE_CONTAINER,
    )
else:
    attachment_store = FileSystemAttachmentStore(settings.ATTACHMENT_STORAGE_DIR)
attachment_service = AttachmentService(
    store=attachment_store,
    max_bytes=settings.MAX_ATTACHMENT_BYTES,
    max_uncompressed_bytes=settings.MAX_ATTACHMENT_UNCOMPRESSED_BYTES,
    max_extracted_chars=settings.MAX_EXTRACTED_ATTACHMENT_CHARS,
)
coach_agent = CoachAgent(
    client=client,
    model=settings.OPENAI_MODEL,
    reasoning_effort=settings.OPENAI_REASONING_EFFORT,
    embedding_model=settings.OPENAI_EMBEDDING_MODEL,
    embedding_dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
    max_tool_rounds=MAX_TOOL_ROUNDS,
)

router = APIRouter(
    prefix="/email",
    tags=["Email"],
    dependencies=[Depends(require_email_service)],
)


@router.post("/respond", response_model=EmailResponseResult)
def respond_to_email(
    request: EmailResponseRequest,
    db: Session = Depends(get_db),  # noqa: B008
) -> EmailResponseResult:
    """Persist the inbound email and return Oliver's delivery instruction."""
    inbound_message = db.scalar(select(EmailMessageDb).where(EmailMessageDb.internet_message_id == request.message_id))
    if inbound_message is not None:
        existing_run = db.scalar(
            select(OliverRunDb).where(OliverRunDb.inbound_message_id == inbound_message.id).order_by(OliverRunDb.created_at.desc())
        )
        if existing_run is not None:
            existing_delivery = herald.for_run(db, existing_run.id)
            return EmailResponseResult(
                run_id=existing_run.id,
                action=existing_run.action,
                subject=existing_run.subject,
                email_html=existing_run.rendered_email_html,
                delivery_id=existing_delivery.id if existing_delivery is not None else None,
                delivery_status=existing_delivery.status if existing_delivery is not None else None,
            )
        thread = inbound_message.thread
    else:
        inbound_message = None
        thread = db.scalar(select(EmailThreadDb).where(EmailThreadDb.conversation_id == request.conversation_id))
        if thread is None:
            thread = _find_existing_reply_thread(db, request)
        if thread is None:
            thread = EmailThreadDb(
                conversation_id=request.conversation_id,
                subject=request.subject,
                participant_email=request.sender_email,
            )
            db.add(thread)
            db.flush()
        else:
            # A few Microsoft connectors expose a per-item ID instead of the
            # stable Internet Message-ID.  Check the existing messages in this
            # conversation before inserting so a replay cannot produce another
            # run (or another outbound email) for the same payload.
            existing_messages = list(
                db.scalars(select(EmailMessageDb).where(EmailMessageDb.thread_id == thread.id, EmailMessageDb.direction == "INBOUND"))
            )
            inbound_message = next(
                (
                    message
                    for message in existing_messages
                    if _is_replayed_message(
                        message,
                        message_id=request.message_id,
                        sender_email=request.sender_email,
                        subject=request.subject,
                        content_html=request.email_thread,
                        received_at=request.received_at,
                    )
                ),
                None,
            )
            if inbound_message is not None:
                existing_run = db.scalar(
                    select(OliverRunDb).where(OliverRunDb.inbound_message_id == inbound_message.id).order_by(OliverRunDb.created_at.desc())
                )
                if existing_run is not None:
                    existing_delivery = herald.for_run(db, existing_run.id)
                    return EmailResponseResult(
                        run_id=existing_run.id,
                        action=existing_run.action,
                        subject=existing_run.subject,
                        email_html=existing_run.rendered_email_html,
                        delivery_id=existing_delivery.id if existing_delivery is not None else None,
                        delivery_status=existing_delivery.status if existing_delivery is not None else None,
                    )
            thread.subject = request.subject or thread.subject
            thread.participant_email = request.sender_email or thread.participant_email

        if inbound_message is None:
            inbound_message = EmailMessageDb(
                thread_id=thread.id,
                internet_message_id=request.message_id,
                direction="INBOUND",
                sender_email=request.sender_email,
                recipient_emails=request.recipient_emails,
                subject=request.subject,
                content_html=request.email_thread,
                received_at=request.received_at,
            )
            db.add(inbound_message)
            db.commit()
            db.refresh(inbound_message)

    try:
        attachments = [attachment_service.ingest(db, inbound_message, attachment) for attachment in request.attachments]
    except AttachmentValidationError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    try:
        messages = list(db.scalars(select(EmailMessageDb).where(EmailMessageDb.thread_id == thread.id).order_by(EmailMessageDb.received_at.asc())))
        initiative = registrar.find_initiative(db, thread)
        previous_assessment_exists = (
            db.scalar(
                (
                    select(CanonicalAssessmentDb.run_id).where(CanonicalAssessmentDb.initiative_id == initiative.id)
                    if initiative is not None
                    else select(CanonicalAssessmentDb.run_id)
                    .join(OliverRunDb, OliverRunDb.id == CanonicalAssessmentDb.run_id)
                    .where(OliverRunDb.thread_id == thread.id)
                ).limit(1)
            )
            is not None
        )
        try:
            canonical_assessment = assessment_agent.assess(
                AssessmentRequest(
                    subject=request.subject,
                    latest_message_html=request.email_thread,
                    inbound_messages_html=tuple(message.content_html or "" for message in messages if message.direction == "INBOUND"),
                    attachment_texts=tuple(
                        attachment.blob.extracted_text
                        for attachment in attachments
                        if attachment.blob.extraction_status == "SUCCEEDED" and attachment.blob.extracted_text
                    ),
                    has_previous_assessment=previous_assessment_exists,
                    current_stage=DIStage(initiative.current_stage) if initiative is not None else DIStage.DI1,
                )
            )
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Oliver's scoring configuration is invalid.",
            ) from error
        canonical_prompt_context = canonical_assessment_context(canonical_assessment)

        def message_context(message: EmailMessageDb) -> str:
            participant_name = _participant_display_name(
                message.sender_email,
                request.sender_name if message.id == inbound_message.id else None,
            )
            content = message.content_html or ""
            if message.direction == "INBOUND":
                full_text = html_to_text(content)
                authored_text = current_message_text(content)
                if authored_text and _normalized_header(authored_text) != _normalized_header(full_text):
                    # Keep quoted Oliver HTML out of the Coach context. The
                    # original message is retained for audit and exposed in
                    # the admin UI as a collapsed/hidden quote.
                    content = f"<p>{escape(authored_text)}</p>"
                elif not authored_text and full_text:
                    content = "<p>(No new participant text; quoted history omitted.)</p>"
            return (
                f'<email direction="{message.direction}" sender="{escape(message.sender_email or "unknown", quote=True)}" '
                f'participant-name="{escape(participant_name or "", quote=True)}" '
                f'received-at="{message.received_at.isoformat()}">\n'
                f"{content}\n"
                "</email>"
            )

        email_thread = "\n\n".join(message_context(message) for message in messages)

        inbound_idea_transcript: list[str] = []
        for message in messages:
            if message.direction != "INBOUND":
                continue
            authored_text = current_message_text(message.content_html or "")
            inbound_idea_transcript.append(
                f"Sender: {message.sender_email or 'unknown'}\n"
                f"Subject: {message.subject or 'unknown'}\n"
                f"Received: {message.received_at.isoformat()}\n"
                f"Content:\n{authored_text}"
            )

        thread.semantic_text = "\n\n".join(inbound_idea_transcript)
        participant_email = (thread.participant_email or "").lower()
        if participant_email.endswith(f"@{INTERNAL_EMAIL_DOMAIN}"):
            thread.embedding = generate_embedding(
                client,
                thread.semantic_text,
                model=settings.OPENAI_EMBEDDING_MODEL,
                dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
            )
            thread.embedding_model = settings.OPENAI_EMBEDDING_MODEL
            thread.embedding_dimensions = settings.OPENAI_EMBEDDING_DIMENSIONS
            thread.embedded_at = datetime.now(timezone.utc)
        else:
            thread.embedding = None
            thread.embedding_model = None
            thread.embedding_dimensions = None
            thread.embedded_at = None
        db.commit()

        coach_result = coach_agent.respond(
            database=db,
            current_thread=thread,
            email_thread=email_thread,
            canonical_context=canonical_prompt_context,
        )
        oliver_response = coach_result.response
        rendered_email_html = render_coach_response(oliver_response, canonical_assessment)
    except (APIError, AgentContractError, RuntimeError, TypeError, ValueError, KeyError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The model provider could not complete the request.",
        ) from error

    is_assessment_reply = oliver_response.action == "SEND_EMAIL" and oliver_response.reply_kind == "assessment" and canonical_assessment is not None

    evidence_version = None
    if is_assessment_reply:
        initiative = registrar.ensure_initiative(db, thread)
        evidence_version = registrar.capture_message_evidence(
            db,
            initiative=initiative,
            inbound_messages=[message for message in messages if message.direction == "INBOUND"],
            attachments=attachments,
            trigger_message=inbound_message,
        )

    run_id = uuid4()
    run = OliverRunDb(
        id=run_id,
        thread_id=thread.id,
        inbound_message_id=inbound_message.id,
        action=oliver_response.action,
        model_name=settings.OPENAI_MODEL,
        subject=oliver_response.subject,
        generated_content_html=oliver_response.content_html,
        rendered_email_html=rendered_email_html,
        prompt_tokens=coach_result.prompt_tokens,
        completion_tokens=coach_result.completion_tokens,
    )
    db.add(run)
    # Persist the canonical assessment only when Oliver issued a stage-gate assessment,
    # so conversational replies, information requests, and NO_REPLY decisions are never
    # recorded as scored initiatives.
    if is_assessment_reply:
        persisted_assessment = cast(CanonicalAssessment, canonical_assessment)
        db.add(
            assessment_record(
                run_id,
                persisted_assessment,
                initiative_id=initiative.id,
                evidence_version_id=evidence_version.id,
            )
        )
        db.flush()
        stage_master.process_assessment(
            db,
            initiative=initiative,
            assessment=persisted_assessment,
            assessment_run_id=run_id,
        )
    for rank, (related_thread, cosine_distance) in enumerate(coach_result.related_threads, start=1):
        db.add(
            OliverRunRelatedThreadDb(
                run_id=run_id,
                related_thread_id=related_thread.id,
                rank=rank,
                cosine_distance=cosine_distance,
            )
        )
    delivery = None
    if oliver_response.action == "SEND_EMAIL":
        outbound_message = EmailMessageDb(
            id=uuid4(),
            thread_id=thread.id,
            internet_message_id=f"oliver-run:{run_id}",
            direction="OUTBOUND",
            sender_email="Oliver",
            recipient_emails=request.sender_email,
            subject=oliver_response.subject,
            content_html=rendered_email_html,
            received_at=datetime.now(timezone.utc),
        )
        db.add(outbound_message)
        delivery = herald.enqueue(db, run=run, outbound_message=outbound_message)
    db.commit()

    return EmailResponseResult(
        run_id=run.id,
        action=run.action,
        subject=run.subject,
        email_html=run.rendered_email_html,
        delivery_id=delivery.id if delivery is not None else None,
        delivery_status=delivery.status if delivery is not None else None,
    )


@router.get("/deliveries/pending", response_model=list[DeliveryInstructionResponse])
def pending_deliveries(
    limit: int = Query(default=20, ge=1, le=100),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[DeliveryInstructionResponse]:
    """Return due delivery instructions for a polling Logic App."""
    deliveries = herald.pending(
        db,
        limit=limit,
        visibility_timeout_seconds=settings.DELIVERY_VISIBILITY_TIMEOUT_SECONDS,
    )
    response = [
        DeliveryInstructionResponse(
            delivery_id=delivery.id,
            run_id=delivery.run_id,
            status=delivery.status,
            attempt_count=delivery.attempt_count,
            provider_message_id=delivery.provider_message_id,
            last_error=delivery.last_error,
            delivered_at=delivery.delivered_at,
            recipient_emails=delivery.outbound_message.recipient_emails,
            subject=delivery.outbound_message.subject,
            email_html=delivery.outbound_message.content_html,
        )
        for delivery in deliveries
    ]
    db.commit()
    return response


@router.post("/deliveries/{delivery_id}/result", response_model=DeliveryStatusResponse)
def record_delivery_result(
    delivery_id: UUID,
    request: DeliveryResultRequest,
    db: Session = Depends(get_db),  # noqa: B008
) -> DeliveryStatusResponse:
    """Accept an idempotent sent/failed result from Logic App."""
    try:
        delivery = herald.record_result(
            db,
            delivery_id=delivery_id,
            idempotency_key=request.idempotency_key,
            outcome=request.outcome,
            occurred_at=request.occurred_at,
            provider_message_id=request.provider_message_id,
            error=request.error,
        )
        db.commit()
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return DeliveryStatusResponse(
        delivery_id=delivery.id,
        run_id=delivery.run_id,
        status=delivery.status,
        attempt_count=delivery.attempt_count,
        provider_message_id=delivery.provider_message_id,
        last_error=delivery.last_error,
        delivered_at=delivery.delivered_at,
    )
