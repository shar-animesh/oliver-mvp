# Path: app/routers/intelligence.py
# Description: Authenticated portfolio-intelligence and Scout queue endpoints.

"""Authenticated read-only intelligence and Scout queue endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.security import require_admin
from app.utils.models.api import IntelligenceOverviewResponse, PortfolioInsightAdminResponse, ScoutCandidateAdminResponse
from app.utils.postgres import PortfolioInsightReportDb, ScoutCandidateDb, get_db

router = APIRouter(
    prefix="/api/v1/intelligence",
    tags=["intelligence"],
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=IntelligenceOverviewResponse)
def get_intelligence_overview(database: Session = Depends(get_db)) -> IntelligenceOverviewResponse:  # noqa: B008
    """Return the latest portfolio interpretation and open Scout candidates."""
    latest = database.scalar(select(PortfolioInsightReportDb).order_by(PortfolioInsightReportDb.created_at.desc()).limit(1))
    candidates = list(
        database.scalars(
            select(ScoutCandidateDb)
            .where(ScoutCandidateDb.status.in_(("DISCOVERED", "REVIEWED")))
            .order_by(ScoutCandidateDb.discovered_at.desc())
            .limit(100)
        )
    )
    return IntelligenceOverviewResponse(
        latest_portfolio_insight=PortfolioInsightAdminResponse.model_validate(latest) if latest is not None else None,
        scout_candidates=[ScoutCandidateAdminResponse.model_validate(candidate) for candidate in candidates],
    )
