# Path: routes/email.py
# Description: Internal email-response route called by the Logic App.

from datetime import datetime, timezone
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
from utils.email_content import html_to_text
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
        thread = db.scalar(select(EmailThreadDb).where(EmailThreadDb.conversation_id == request.conversation_id))
        if thread is None:
            thread = EmailThreadDb(
                conversation_id=request.conversation_id,
                subject=request.subject,
                participant_email=request.sender_email,
            )
            db.add(thread)
            db.flush()
        else:
            thread.subject = request.subject or thread.subject
            thread.participant_email = request.sender_email or thread.participant_email

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

        email_thread = "\n\n".join(
            (
                f'<email direction="{message.direction}" sender="{message.sender_email or "unknown"}" '
                f'received-at="{message.received_at.isoformat()}">\n'
                f"{message.content_html or ''}\n"
                "</email>"
            )
            for message in messages
        )

        inbound_idea_transcript: list[str] = []
        for message in messages:
            if message.direction != "INBOUND":
                continue
            inbound_idea_transcript.append(
                f"Sender: {message.sender_email or 'unknown'}\n"
                f"Subject: {message.subject or 'unknown'}\n"
                f"Received: {message.received_at.isoformat()}\n"
                f"Content:\n{html_to_text(message.content_html or '')}"
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
