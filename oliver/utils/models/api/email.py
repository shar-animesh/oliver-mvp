"""HTTP contracts for the Logic App email workflow."""

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

MAX_ATTACHMENT_BASE64_CHARACTERS = 34_000_000
MAX_ATTACHMENTS_PER_MESSAGE = 20
MAX_EMAIL_THREAD_CHARACTERS = 1_000_000


class EmailAttachmentInput(BaseModel):
    """One attachment supplied by the Logic App with its original provider identity."""

    attachment_id: str = Field(min_length=1, max_length=512)
    file_name: str = Field(min_length=1, max_length=512)
    content_type: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1, max_length=MAX_ATTACHMENT_BASE64_CHARACTERS)


class EmailResponseRequest(BaseModel):
    """Complete metadata and content for one inbound email."""

    message_id: str = Field(min_length=1, max_length=512)
    conversation_id: str = Field(min_length=1, max_length=512)
    subject: Optional[str] = Field(default=None, max_length=998)
    sender_email: Optional[str] = Field(default=None, max_length=320)
    sender_name: Optional[str] = Field(default=None, max_length=320)
    recipient_emails: Optional[str] = Field(default=None, max_length=10_000)
    received_at: datetime
    email_thread: str = Field(min_length=1, max_length=MAX_EMAIL_THREAD_CHARACTERS)
    attachments: List[EmailAttachmentInput] = Field(default_factory=list, max_length=MAX_ATTACHMENTS_PER_MESSAGE)

    @model_validator(mode="after")
    def bound_total_attachment_payload(self) -> "EmailResponseRequest":
        """Reject requests whose combined attachment payload exceeds the mail limit."""
        if sum(len(attachment.content_base64) for attachment in self.attachments) > MAX_ATTACHMENT_BASE64_CHARACTERS:
            raise ValueError("Combined attachment content exceeds the supported message limit")
        return self


class EmailResponseResult(BaseModel):
    """Persisted delivery instruction returned to the Logic App."""

    run_id: UUID
    action: Literal["SEND_EMAIL", "NO_REPLY"]
    subject: Optional[str] = None
    email_html: Optional[str] = None
    delivery_id: Optional[UUID] = None
    delivery_status: Optional[str] = None


class DeliveryResultRequest(BaseModel):
    """Idempotent delivery outcome reported by Logic App."""

    idempotency_key: str = Field(min_length=1, max_length=512)
    outcome: Literal["SENT", "FAILED"]
    occurred_at: datetime
    provider_message_id: Optional[str] = Field(default=None, max_length=512)
    error: Optional[str] = Field(default=None, max_length=2000)


class DeliveryStatusResponse(BaseModel):
    """Current durable delivery state."""

    delivery_id: UUID
    run_id: UUID
    status: str
    attempt_count: int
    provider_message_id: Optional[str]
    last_error: Optional[str]
    delivered_at: Optional[datetime]


class DeliveryInstructionResponse(DeliveryStatusResponse):
    """Due delivery instruction resolved from canonical outbound-message storage."""

    recipient_emails: Optional[str]
    subject: Optional[str]
    email_html: Optional[str]
