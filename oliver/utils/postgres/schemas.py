"""SQLAlchemy schema for Oliver email conversations and model runs."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from utils.postgres.base import DatabaseBase


class InitiativeDb(DatabaseBase):
    """Canonical business initiative independent of any single email thread."""

    __tablename__ = "initiatives"
    __table_args__ = (
        CheckConstraint("current_stage IN ('DI1', 'DI2', 'DI3', 'DI4', 'DI5')", name="ck_initiative_current_stage"),
        CheckConstraint(
            "related_idea_sharing_scope IN ('PRIVATE', 'INTERNAL')",
            name="ck_initiative_related_idea_sharing_scope",
        ),
        CheckConstraint("version > 0", name="ck_initiative_version_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    current_stage: Mapped[str] = mapped_column(String(8), nullable=False, default="DI1", server_default="DI1")
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="Assessed", server_default="Assessed")
    related_idea_sharing_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="PRIVATE", server_default="PRIVATE")
    is_on_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    hold_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    stage_entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    threads: Mapped[List["EmailThreadDb"]] = relationship(back_populates="initiative")
    evidence_items: Mapped[List["EvidenceItemDb"]] = relationship(back_populates="initiative", cascade="all, delete-orphan")
    evidence_versions: Mapped[List["EvidenceVersionDb"]] = relationship(back_populates="initiative", cascade="all, delete-orphan")
    lifecycle_transitions: Mapped[List["LifecycleTransitionDb"]] = relationship(
        back_populates="initiative",
        cascade="all, delete-orphan",
        order_by="LifecycleTransitionDb.created_at",
    )


class EmailThreadDb(DatabaseBase):
    """One Microsoft 365 email conversation handled by Oliver."""

    __tablename__ = "email_threads"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    initiative_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("initiatives.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(998), nullable=True)
    participant_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    semantic_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding: Mapped[Optional[List[float]]] = mapped_column(ARRAY(Float), nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    embedding_dimensions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    embedded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    messages: Mapped[List["EmailMessageDb"]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="EmailMessageDb.received_at",
    )
    runs: Mapped[List["OliverRunDb"]] = relationship(back_populates="thread", cascade="all, delete-orphan")
    related_run_matches: Mapped[List["OliverRunRelatedThreadDb"]] = relationship(
        back_populates="related_thread",
        foreign_keys="OliverRunRelatedThreadDb.related_thread_id",
    )
    initiative: Mapped[Optional[InitiativeDb]] = relationship(back_populates="threads")


class EmailMessageDb(DatabaseBase):
    """An inbound or outbound email recorded exactly once."""

    __tablename__ = "email_messages"
    __table_args__ = (
        UniqueConstraint("internet_message_id", name="uq_email_messages_internet_message_id"),
        Index("ix_email_messages_thread_received", "thread_id", "received_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    thread_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("email_threads.id", ondelete="CASCADE"), nullable=False)
    internet_message_id: Mapped[str] = mapped_column(String(512), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    sender_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    recipient_emails: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(998), nullable=True)
    content_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    thread: Mapped[EmailThreadDb] = relationship(back_populates="messages")
    attachments: Mapped[List["EmailAttachmentDb"]] = relationship(back_populates="message", cascade="all, delete-orphan")


class AttachmentBlobDb(DatabaseBase):
    """Content-addressed attachment payload and its derived extraction."""

    __tablename__ = "attachment_blobs"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_attachment_blob_size_nonnegative"),
        CheckConstraint(
            "extraction_status IN ('PENDING', 'SUCCEEDED', 'FAILED', 'UNSUPPORTED')",
            name="ck_attachment_blob_extraction_status",
        ),
    )

    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", server_default="PENDING")
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extraction_metadata: Mapped[Optional[dict[str, object]]] = mapped_column(JSONB, nullable=True)
    extraction_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    attachments: Mapped[List["EmailAttachmentDb"]] = relationship(back_populates="blob")


class EmailAttachmentDb(DatabaseBase):
    """One provider attachment reference linked to a content-addressed blob."""

    __tablename__ = "email_attachments"
    __table_args__ = (
        UniqueConstraint("message_id", "provider_attachment_id", name="uq_email_attachment_provider_id"),
        Index("ix_email_attachments_message", "message_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    message_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("email_messages.id", ondelete="CASCADE"), nullable=False)
    provider_attachment_id: Mapped[str] = mapped_column(String(512), nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    blob_hash: Mapped[str] = mapped_column(String(64), ForeignKey("attachment_blobs.content_hash"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    message: Mapped[EmailMessageDb] = relationship(back_populates="attachments")
    blob: Mapped[AttachmentBlobDb] = relationship(back_populates="attachments")


class EvidenceItemDb(DatabaseBase):
    """Immutable reference to one source that may support an assessment."""

    __tablename__ = "evidence_items"
    __table_args__ = (
        CheckConstraint("source_type IN ('MESSAGE', 'ATTACHMENT', 'ADMIN', 'SCOUT')", name="ck_evidence_item_source_type"),
        CheckConstraint(
            "(source_type = 'MESSAGE' AND message_id IS NOT NULL AND attachment_id IS NULL) OR "
            "(source_type = 'ATTACHMENT' AND attachment_id IS NOT NULL AND message_id IS NULL) OR "
            "(source_type IN ('ADMIN', 'SCOUT') AND message_id IS NULL AND attachment_id IS NULL)",
            name="ck_evidence_item_source_reference",
        ),
        UniqueConstraint("initiative_id", "message_id", name="uq_evidence_item_initiative_message"),
        UniqueConstraint("initiative_id", "attachment_id", name="uq_evidence_item_initiative_attachment"),
        UniqueConstraint("id", "initiative_id", name="uq_evidence_items_id_initiative"),
        Index("ix_evidence_items_initiative_created", "initiative_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    initiative_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("initiatives.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    message_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("email_messages.id", ondelete="CASCADE"), nullable=True)
    attachment_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("email_attachments.id", ondelete="CASCADE"), nullable=True)
    external_source_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    initiative: Mapped[InitiativeDb] = relationship(back_populates="evidence_items")


class EvidenceVersionDb(DatabaseBase):
    """Immutable snapshot of the evidence set used at one lifecycle moment."""

    __tablename__ = "evidence_versions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_evidence_version_positive"),
        UniqueConstraint("initiative_id", "version", name="uq_evidence_version_number"),
        UniqueConstraint("initiative_id", "source_fingerprint", name="uq_evidence_version_fingerprint"),
        UniqueConstraint("id", "initiative_id", name="uq_evidence_versions_id_initiative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    initiative_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("initiatives.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger_message_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("email_messages.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    initiative: Mapped[InitiativeDb] = relationship(back_populates="evidence_versions")
    items: Mapped[List["EvidenceVersionItemDb"]] = relationship(back_populates="evidence_version", cascade="all, delete-orphan")


class EvidenceVersionItemDb(DatabaseBase):
    """Membership of one immutable evidence snapshot."""

    __tablename__ = "evidence_version_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["evidence_version_id", "initiative_id"],
            ["evidence_versions.id", "evidence_versions.initiative_id"],
            name="fk_evidence_version_items_version_initiative",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["evidence_item_id", "initiative_id"],
            ["evidence_items.id", "evidence_items.initiative_id"],
            name="fk_evidence_version_items_item_initiative",
            ondelete="CASCADE",
        ),
    )

    evidence_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    evidence_item_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    initiative_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    evidence_version: Mapped[EvidenceVersionDb] = relationship(back_populates="items")


class OliverRunDb(DatabaseBase):
    """One Oliver decision made for an inbound message."""

    __tablename__ = "oliver_runs"
    __table_args__ = (Index("ix_oliver_runs_thread_created", "thread_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    thread_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("email_threads.id", ondelete="CASCADE"), nullable=False)
    inbound_message_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("email_messages.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(998), nullable=True)
    generated_content_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rendered_email_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    thread: Mapped[EmailThreadDb] = relationship(back_populates="runs")
    related_threads: Mapped[List["OliverRunRelatedThreadDb"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="OliverRunRelatedThreadDb.rank",
    )
    assessment: Mapped[Optional["CanonicalAssessmentDb"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        uselist=False,
    )
    delivery: Mapped[Optional["DeliveryOutboxDb"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        uselist=False,
    )


class CanonicalAssessmentDb(DatabaseBase):
    """Versioned, authoritative score and DI-stage result for one Oliver run."""

    __tablename__ = "canonical_assessments"
    __table_args__ = (
        CheckConstraint(
            "composite_score IS NULL OR composite_score BETWEEN 0 AND 100",
            name="ck_assessment_score_range",
        ),
        CheckConstraint(
            "composite_confidence IS NULL OR composite_confidence BETWEEN 0 AND 1",
            name="ck_assessment_confidence_range",
        ),
        CheckConstraint(
            "current_stage IN ('DI1', 'DI2', 'DI3', 'DI4', 'DI5')",
            name="ck_assessment_current_stage",
        ),
        CheckConstraint(
            "transition_target IS NULL OR transition_target IN ('DI1', 'DI2', 'DI3', 'DI4', 'DI5')",
            name="ck_assessment_transition_target",
        ),
        CheckConstraint(
            "recommended_next_stage IS NULL OR recommended_next_stage IN ('DI1', 'DI2', 'DI3', 'DI4', 'DI5')",
            name="ck_assessment_recommended_stage",
        ),
        CheckConstraint(
            "gate_outcome IN ('ADVANCE', 'CONDITIONAL_ADVANCE', 'HOLD_FOR_EVIDENCE', 'DO_NOT_ADVANCE', 'CONTINUE_MONITORING')",
            name="ck_assessment_gate_outcome",
        ),
        CheckConstraint(
            "response_depth IN ('BRIEF', 'STANDARD', 'DETAILED')",
            name="ck_assessment_response_depth",
        ),
    )

    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("oliver_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    initiative_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("initiatives.id", ondelete="SET NULL"), nullable=True, index=True
    )
    evidence_version_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("evidence_versions.id", ondelete="SET NULL"), nullable=True
    )
    current_stage: Mapped[str] = mapped_column(String(8), nullable=False)
    composite_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    transition_target: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    recommended_next_stage: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    gate_outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False)
    composite_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lowest_confidence_dimension: Mapped[str] = mapped_column(String(64), nullable=False)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_depth: Mapped[str] = mapped_column(String(16), nullable=False)
    rating: Mapped[str] = mapped_column(String(32), nullable=False)
    score_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    transition_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    weight_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    transition_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    dimensions: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    criteria: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run: Mapped[OliverRunDb] = relationship(back_populates="assessment")


class LifecycleTransitionDb(DatabaseBase):
    """One proposed or applied change to authoritative initiative state."""

    __tablename__ = "lifecycle_transitions"
    __table_args__ = (
        CheckConstraint(
            "transition_type IN ('ADVANCE', 'NO_GO', 'RETIRE', 'OVERRIDE', 'ROLLBACK', 'HOLD', 'RESUME')",
            name="ck_lifecycle_transition_type",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPLIED', 'APPROVED', 'REJECTED', 'CANCELLED')",
            name="ck_lifecycle_transition_status",
        ),
        CheckConstraint("from_stage IN ('DI1', 'DI2', 'DI3', 'DI4', 'DI5')", name="ck_lifecycle_transition_from_stage"),
        CheckConstraint(
            "to_stage IS NULL OR to_stage IN ('DI1', 'DI2', 'DI3', 'DI4', 'DI5')",
            name="ck_lifecycle_transition_to_stage",
        ),
        CheckConstraint("expected_initiative_version > 0", name="ck_lifecycle_transition_version_positive"),
        UniqueConstraint("assessment_run_id", "transition_type", name="uq_lifecycle_transition_assessment_type"),
        Index("ix_lifecycle_transitions_initiative_created", "initiative_id", "created_at"),
        Index("ix_lifecycle_transitions_pending", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    initiative_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("initiatives.id", ondelete="CASCADE"), nullable=False)
    assessment_run_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("canonical_assessments.run_id", ondelete="SET NULL"), nullable=True
    )
    transition_type: Mapped[str] = mapped_column(String(16), nullable=False)
    from_stage: Mapped[str] = mapped_column(String(8), nullable=False)
    to_stage: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expected_initiative_version: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_by: Mapped[str] = mapped_column(String(320), nullable=False, default="StageMaster")
    decided_by: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    initiative: Mapped[InitiativeDb] = relationship(back_populates="lifecycle_transitions")


class AuditEventDb(DatabaseBase):
    """Append-only record of material domain and integration events."""

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('SYSTEM', 'USER', 'MANAGED_IDENTITY')",
            name="ck_audit_event_actor_type",
        ),
        Index("ix_audit_events_initiative_occurred", "initiative_id", "occurred_at"),
        Index("ix_audit_events_correlation", "correlation_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    # Deliberately not a foreign key: an audit record must survive deletion of its source aggregate.
    initiative_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(320), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DeliveryOutboxDb(DatabaseBase):
    """Durable delivery instruction referencing the canonical outbound message."""

    __tablename__ = "delivery_outbox"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'SENT', 'FAILED', 'UNKNOWN')", name="ck_delivery_outbox_status"),
        CheckConstraint("attempt_count >= 0", name="ck_delivery_outbox_attempt_count_nonnegative"),
        UniqueConstraint("run_id", name="uq_delivery_outbox_run"),
        UniqueConstraint("outbound_message_id", name="uq_delivery_outbox_message"),
        Index("ix_delivery_outbox_status_next_attempt", "status", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("oliver_runs.id", ondelete="CASCADE"), nullable=False)
    outbound_message_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("email_messages.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING", server_default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    run: Mapped[OliverRunDb] = relationship(back_populates="delivery")
    outbound_message: Mapped[EmailMessageDb] = relationship()
    attempts: Mapped[List["DeliveryAttemptDb"]] = relationship(
        back_populates="delivery", cascade="all, delete-orphan", order_by="DeliveryAttemptDb.created_at"
    )


class DeliveryAttemptDb(DatabaseBase):
    """Idempotent delivery result reported by Logic App."""

    __tablename__ = "delivery_attempts"
    __table_args__ = (
        CheckConstraint("outcome IN ('SENT', 'FAILED')", name="ck_delivery_attempt_outcome"),
        UniqueConstraint("idempotency_key", name="uq_delivery_attempt_idempotency_key"),
        Index("ix_delivery_attempts_delivery_created", "delivery_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    delivery_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("delivery_outbox.id", ondelete="CASCADE"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    delivery: Mapped[DeliveryOutboxDb] = relationship(back_populates="attempts")


class PortfolioInsightReportDb(DatabaseBase):
    """Versioned agent interpretation of a verified aggregate snapshot."""

    __tablename__ = "portfolio_insight_reports"
    __table_args__ = (UniqueConstraint("input_fingerprint", name="uq_portfolio_insight_input_fingerprint"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    report: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    generated_by: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ScoutCandidateDb(DatabaseBase):
    """Governed candidate detected from an explicitly approved source."""

    __tablename__ = "scout_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DISCOVERED', 'REVIEWED', 'PROMOTED', 'DISMISSED')",
            name="ck_scout_candidate_status",
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_scout_candidate_confidence"),
        UniqueConstraint("source_system", "source_reference", "content_hash", name="uq_scout_candidate_source_content"),
        Index("ix_scout_candidates_status_discovered", "status", "discovered_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    source_system: Mapped[str] = mapped_column(String(128), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_owner: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DISCOVERED", server_default="DISCOVERED")
    promoted_initiative_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("initiatives.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MetricDefinitionDb(DatabaseBase):
    """One governed operational or realized-value measure for an initiative."""

    __tablename__ = "metric_definitions"
    __table_args__ = (
        CheckConstraint("metric_type IN ('SLO', 'VALUE')", name="ck_metric_definition_type"),
        CheckConstraint("direction IN ('AT_LEAST', 'AT_MOST')", name="ck_metric_definition_direction"),
        UniqueConstraint("initiative_id", "name", name="uq_metric_definition_initiative_name"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    initiative_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("initiatives.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(16), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    baseline: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_system: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    observations: Mapped[List["MetricObservationDb"]] = relationship(
        back_populates="metric", cascade="all, delete-orphan", order_by="MetricObservationDb.observed_at"
    )


class MetricObservationDb(DatabaseBase):
    """One idempotent measurement from an approved source system."""

    __tablename__ = "metric_observations"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_metric_observation_idempotency_key"),
        Index("ix_metric_observations_metric_observed", "metric_id", "observed_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    metric_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("metric_definitions.id", ondelete="CASCADE"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    source_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    measurement_metadata: Mapped[Optional[dict[str, object]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    metric: Mapped[MetricDefinitionDb] = relationship(back_populates="observations")
    alert: Mapped[Optional["OperationalAlertDb"]] = relationship(back_populates="observation", cascade="all, delete-orphan", uselist=False)


class OperationalAlertDb(DatabaseBase):
    """Sentinel alert emitted once for a breaching observation."""

    __tablename__ = "operational_alerts"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')", name="ck_operational_alert_status"),
        UniqueConstraint("observation_id", name="uq_operational_alert_observation"),
        Index("ix_operational_alerts_initiative_status", "initiative_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    initiative_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("initiatives.id", ondelete="CASCADE"), nullable=False)
    observation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("metric_observations.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN", server_default="OPEN")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    observation: Mapped[MetricObservationDb] = relationship(back_populates="alert")


class OliverRunRelatedThreadDb(DatabaseBase):
    """One related conversation supplied to a specific Oliver run."""

    __tablename__ = "oliver_run_related_threads"
    __table_args__ = (
        UniqueConstraint("run_id", "related_thread_id", name="uq_oliver_run_related_thread"),
        Index("ix_oliver_run_related_threads_run_rank", "run_id", "rank"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("oliver_runs.id", ondelete="CASCADE"), nullable=False)
    related_thread_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("email_threads.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    cosine_distance: Mapped[float] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run: Mapped[OliverRunDb] = relationship(back_populates="related_threads")
    related_thread: Mapped[EmailThreadDb] = relationship(
        back_populates="related_run_matches",
        foreign_keys=[related_thread_id],
    )
