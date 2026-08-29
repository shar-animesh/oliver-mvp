# Path: app/utils/models/api/email_threads.py
# Description: Read-only email-thread and canonical-assessment response contracts.

"""API response models for the read-only email-thread dashboard."""

from datetime import datetime
from typing import Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class EmailMessageResponse(BaseModel):
    """One inbound or outbound message in a conversation."""

    id: UUID
    direction: Literal["INBOUND", "OUTBOUND"]
    sender_email: Optional[str]
    recipient_emails: Optional[str]
    subject: Optional[str]
    content_html: Optional[str]
    received_at: datetime


class RelatedIdeaResponse(BaseModel):
    """One semantic match supplied to an Oliver response."""

    thread_id: UUID
    subject: Optional[str]
    participant_email: Optional[str]
    rank: int
    cosine_distance: float


class DimensionScoreResponse(BaseModel):
    """One traceable dimension in the canonical assessment."""

    agent: str
    dimension: str
    dimension_label: str
    state: str
    value: Optional[int]
    confidence: float
    weight: int
    summary: str
    evidence: List[str]
    gaps: List[str]
    scored_by: str


class CanonicalAssessmentResponse(BaseModel):
    """Portfolio score and independent transition-readiness result."""

    current_stage: str
    composite_score: Optional[int]
    transition_target: Optional[str]
    recommended_next_stage: Optional[str]
    gate_outcome: str
    lifecycle_state: str
    composite_confidence: Optional[float]
    lowest_confidence_dimension: str
    requires_human_review: bool
    response_depth: str
    rating: str
    score_rationale: str
    transition_rationale: str
    model_version: str
    weight_set_version: str
    transition_policy_version: str
    dimensions: List[DimensionScoreResponse]
    criteria: List[Dict[str, object]]
    created_at: datetime


class OliverRunResponse(BaseModel):
    """One stored Oliver decision for an inbound message."""

    id: UUID
    action: Literal["SEND_EMAIL", "NO_REPLY"]
    model_name: str
    subject: Optional[str]
    delivery_status: Optional[str]
    delivery_attempt_count: int
    delivery_last_error: Optional[str]
    delivered_at: Optional[datetime]
    assessment: Optional[CanonicalAssessmentResponse]
    related_ideas: List[RelatedIdeaResponse]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    created_at: datetime


class EmailThreadSummaryResponse(BaseModel):
    """Compact thread information displayed in the inbox list."""

    id: UUID
    initiative_id: Optional[UUID]
    initiative_title: Optional[str]
    conversation_id: str
    subject: Optional[str]
    participant_email: Optional[str]
    message_count: int
    run_count: int
    assessment_count: int
    canonical_score: Optional[int]
    di_stage: Optional[str]
    assessment_stage: Optional[str]
    initiative_current_stage: Optional[str]
    initiative_lifecycle_state: Optional[str]
    gate_outcome: Optional[str]
    rating: Optional[str]
    last_activity_at: datetime


class EmailThreadDetailResponse(BaseModel):
    """Complete communication history and Oliver decisions for a thread."""

    id: UUID
    initiative_id: Optional[UUID]
    initiative_title: Optional[str]
    initiative_current_stage: Optional[str]
    initiative_lifecycle_state: Optional[str]
    conversation_id: str
    subject: Optional[str]
    participant_email: Optional[str]
    embedding_model: Optional[str]
    embedding_dimensions: Optional[int]
    embedded_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    messages: List[EmailMessageResponse]
    runs: List[OliverRunResponse]
