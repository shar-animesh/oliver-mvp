"""HTTP contracts for governed lifecycle commands."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class LifecycleReasonRequest(BaseModel):
    """Required rationale for a hold or resume command."""

    reason: str = Field(min_length=3, max_length=2000)


class LifecycleDecisionRequest(BaseModel):
    """Explicit human decision on one pending lifecycle proposal."""

    decision: Literal["APPROVE", "REJECT"]
    reason: str = Field(min_length=3, max_length=2000)


class LifecycleTransitionResult(BaseModel):
    """Persisted lifecycle command outcome."""

    id: UUID
    initiative_id: UUID
    transition_type: str
    from_stage: str
    to_stage: Optional[str]
    status: str
    reason: str
    decided_by: Optional[str]
    decided_at: Optional[datetime]


class CadenceResponse(BaseModel):
    """Current deterministic Pacer result for an initiative."""

    initiative_id: UUID
    stage: str
    days_in_stage: int
    sla_days: Optional[int]
    days_to_next_gate: Optional[int]
    stall_flag: bool
    on_hold: bool
