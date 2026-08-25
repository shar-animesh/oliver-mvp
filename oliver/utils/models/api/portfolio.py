"""HTTP responses for persisted portfolio intelligence."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from utils.agents.portfolio import PortfolioInsightReport


class PortfolioInsightResponse(BaseModel):
    """One versioned Portfolio Intelligence Agent output."""

    id: UUID
    input_fingerprint: str
    model_name: str
    generated_by: str
    created_at: datetime
    reused: bool
    report: PortfolioInsightReport
