# Path: app/utils/postgres/schemas.py
# Description: Read-only SQLAlchemy mappings for tables owned by Oliver.

"""Read-only mapping of the tables owned and migrated by Oliver."""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class DatabaseBase(DeclarativeBase):
    """Local mapping base; the admin service never creates these tables."""


class EmailThreadDb(DatabaseBase):
    """Read-only email conversation mapping."""

    __tablename__ = "email_threads"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    initiative_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("initiatives.id"), nullable=True)
    conversation_id: Mapped[str] = mapped_column(String(512), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(998), nullable=True)
    participant_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    semantic_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    embedding_dimensions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    embedded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    messages: Mapped[List["EmailMessageDb"]] = relationship(
        back_populates="thread",
        order_by="EmailMessageDb.received_at",
    )
    runs: Mapped[List["OliverRunDb"]] = relationship(back_populates="thread", order_by="OliverRunDb.created_at")
    related_run_matches: Mapped[List["OliverRunRelatedThreadDb"]] = relationship(
        back_populates="related_thread",
        foreign_keys="OliverRunRelatedThreadDb.related_thread_id",
    )
    initiative: Mapped[Optional["InitiativeDb"]] = relationship(back_populates="threads")


class InitiativeDb(DatabaseBase):
    """Read-only canonical initiative aggregate."""

    __tablename__ = "initiatives"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    current_stage: Mapped[str] = mapped_column(String(8), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False)
    is_on_hold: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hold_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    threads: Mapped[List[EmailThreadDb]] = relationship(back_populates="initiative")


class EmailMessageDb(DatabaseBase):
    """Read-only inbound or outbound message mapping."""

    __tablename__ = "email_messages"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    thread_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("email_threads.id"), nullable=False)
    internet_message_id: Mapped[str] = mapped_column(String(512), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    sender_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    recipient_emails: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(998), nullable=True)
    content_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    thread: Mapped[EmailThreadDb] = relationship(back_populates="messages")


class OliverRunDb(DatabaseBase):
    """Read-only Oliver decision mapping."""

    __tablename__ = "oliver_runs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    thread_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("email_threads.id"), nullable=False)
    inbound_message_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("email_messages.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(998), nullable=True)
    generated_content_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rendered_email_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    thread: Mapped[EmailThreadDb] = relationship(back_populates="runs")
    related_threads: Mapped[List["OliverRunRelatedThreadDb"]] = relationship(
        back_populates="run",
        order_by="OliverRunRelatedThreadDb.rank",
    )
    assessment: Mapped[Optional["CanonicalAssessmentDb"]] = relationship(back_populates="run", uselist=False)
    delivery: Mapped[Optional["DeliveryOutboxDb"]] = relationship(back_populates="run", uselist=False)


class CanonicalAssessmentDb(DatabaseBase):
    """Read-only canonical score and DI-stage mapping."""

    __tablename__ = "canonical_assessments"

    run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("oliver_runs.id"), primary_key=True)
    initiative_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("initiatives.id"), nullable=True)
    evidence_version_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
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
    dimensions: Mapped[List[Dict[str, object]]] = mapped_column(JSONB, nullable=False)
    criteria: Mapped[List[Dict[str, object]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped[OliverRunDb] = relationship(back_populates="assessment")


class EvidenceVersionDb(DatabaseBase):
    """Read-only evidence snapshot metadata."""

    __tablename__ = "evidence_versions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    initiative_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("initiatives.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger_message_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LifecycleTransitionDb(DatabaseBase):
    """Read-only lifecycle proposal and decision record."""

    __tablename__ = "lifecycle_transitions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    initiative_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("initiatives.id"), nullable=False)
    assessment_run_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    transition_type: Mapped[str] = mapped_column(String(16), nullable=False)
    from_stage: Mapped[str] = mapped_column(String(8), nullable=False)
    to_stage: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expected_initiative_version: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_by: Mapped[str] = mapped_column(String(320), nullable=False)
    decided_by: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEventDb(DatabaseBase):
    """Read-only event from Oliver's append-only audit ledger."""

    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    initiative_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(320), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    payload: Mapped[Dict[str, object]] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DeliveryOutboxDb(DatabaseBase):
    """Read-only durable delivery state."""

    __tablename__ = "delivery_outbox"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("oliver_runs.id"), nullable=False)
    outbound_message_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped[OliverRunDb] = relationship(back_populates="delivery")


class PortfolioInsightReportDb(DatabaseBase):
    """Read-only persisted Portfolio Intelligence output."""

    __tablename__ = "portfolio_insight_reports"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    input_snapshot: Mapped[Dict[str, object]] = mapped_column(JSONB, nullable=False)
    report: Mapped[Dict[str, object]] = mapped_column(JSONB, nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    generated_by: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ScoutCandidateDb(DatabaseBase):
    """Read-only governed Scout review item."""

    __tablename__ = "scout_candidates"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(128), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_owner: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    promoted_initiative_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OliverRunRelatedThreadDb(DatabaseBase):
    """Read-only related-conversation match for one Oliver decision."""

    __tablename__ = "oliver_run_related_threads"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("oliver_runs.id"), nullable=False)
    related_thread_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("email_threads.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    cosine_distance: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped[OliverRunDb] = relationship(back_populates="related_threads")
    related_thread: Mapped[EmailThreadDb] = relationship(
        back_populates="related_run_matches",
        foreign_keys=[related_thread_id],
    )
