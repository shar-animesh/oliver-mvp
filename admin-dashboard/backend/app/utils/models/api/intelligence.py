# Path: app/utils/models/api/intelligence.py
# Description: Portfolio intelligence and Scout queue response contracts.

"""Read contracts for portfolio intelligence and Scout review queues."""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PortfolioInsightAdminResponse(BaseModel):
    """Latest persisted aggregate insight report."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    input_fingerprint: str
    report: Dict[str, object]
    model_name: str
    generated_by: str
    created_at: datetime


class ScoutCandidateAdminResponse(BaseModel):
    """Scout candidate visible to authorized reviewers."""

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
    discovered_at: datetime


class IntelligenceOverviewResponse(BaseModel):
    """Read-only intelligence surface for the admin workspace."""

    latest_portfolio_insight: Optional[PortfolioInsightAdminResponse]
    scout_candidates: List[ScoutCandidateAdminResponse]
