# Path: app/utils/models/api/initiatives.py
# Description: Canonical initiative, evidence, lifecycle, and audit response contracts.

"""Public read contracts for canonical initiatives and lifecycle history."""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


class InitiativeAssessmentSummary(BaseModel):
    """One historical canonical assessment without duplicating dimension detail."""

    run_id: UUID
    thread_id: Optional[UUID]
    evidence_version_id: Optional[UUID]
    current_stage: str
    composite_score: Optional[int]
    transition_target: Optional[str]
    recommended_next_stage: Optional[str]
    gate_outcome: str
    rating: str
    requires_human_review: bool
    transition_policy_version: str
    created_at: datetime


class LifecycleTransitionResponse(BaseModel):
    """One lifecycle proposal or decision."""

    id: UUID
    assessment_run_id: Optional[UUID]
    transition_type: str
    from_stage: str
    to_stage: Optional[str]
    status: str
    requires_human_review: bool
    expected_initiative_version: int
    policy_version: str
    reason: str
    proposed_by: str
    decided_by: Optional[str]
    created_at: datetime
    decided_at: Optional[datetime]


class AuditEventResponse(BaseModel):
    """One immutable audit event."""

    id: UUID
    event_type: str
    actor_type: str
    actor_id: str
    subject_type: str
    subject_id: str
    correlation_id: Optional[str]
    payload: Dict[str, object]
    occurred_at: datetime


class EvidenceVersionResponse(BaseModel):
    """One immutable evidence-set version."""

    id: UUID
    version: int
    source_fingerprint: str
    trigger_message_id: Optional[UUID]
    created_at: datetime


class InitiativeThreadResponse(BaseModel):
    """Email conversation attached to an initiative."""

    id: UUID
    subject: Optional[str]
    participant_email: Optional[str]
    updated_at: datetime


class InitiativeSummaryResponse(BaseModel):
    """Portfolio row backed by authoritative initiative state."""

    id: UUID
    primary_thread_id: Optional[UUID]
    title: str
    owner_email: Optional[str]
    current_stage: str
    stage_name: str
    lifecycle_state: str
    is_on_hold: bool
    hold_reason: Optional[str]
    version: int
    days_in_stage: int
    evidence_version_count: int
    pending_review_count: int
    latest_score: Optional[int]
    latest_gate_outcome: Optional[str]
    latest_rating: Optional[str]
    latest_assessment_at: Optional[datetime]
    stage_entered_at: datetime
    updated_at: datetime


class InitiativeDetailResponse(InitiativeSummaryResponse):
    """Complete lifecycle history for one canonical initiative."""

    created_at: datetime
    threads: List[InitiativeThreadResponse]
    assessments: List[InitiativeAssessmentSummary]
    evidence_versions: List[EvidenceVersionResponse]
    transitions: List[LifecycleTransitionResponse]
    audit_events: List[AuditEventResponse]
