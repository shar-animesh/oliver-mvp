"""HTTP contracts for governed Scout discovery and review."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from utils.agents.scout import ScoutDiscoveryRequest


class ScoutCandidateResponse(BaseModel):
    """One deduplicated candidate awaiting or completing human review."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_system: str
    source_reference: str
    title: str
    summary: str
    proposed_owner: Optional[str]
    confidence: float
    rationale: str
    status: str
    promoted_initiative_id: Optional[UUID]
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    discovered_at: datetime


class ScoutDiscoveryResponse(BaseModel):
    """Result of one approved-source discovery batch."""

    created_count: int
    candidates: list[ScoutCandidateResponse]


class ScoutDismissRequest(BaseModel):
    """Recorded reason for dismissing a candidate."""

    reason: str = Field(min_length=3, max_length=2000)


class ScoutPromotionResponse(BaseModel):
    """Idempotent promotion result."""

    candidate: ScoutCandidateResponse
    initiative_id: UUID


__all__ = [
    "ScoutCandidateResponse",
    "ScoutDiscoveryRequest",
    "ScoutDiscoveryResponse",
    "ScoutDismissRequest",
    "ScoutPromotionResponse",
]
