"""Role-governed Portfolio Intelligence Agent endpoint."""

from fastapi import APIRouter, Depends, HTTPException, status
from openai import APIError
from sqlalchemy.orm import Session

from config import get_settings
from utils.agents import PortfolioIntelligenceAgent
from utils.model_provider import get_model_client
from utils.models.api import PortfolioInsightResponse
from utils.postgres import get_db
from utils.security import AdminPrincipal, require_insight_operator

settings = get_settings()
router = APIRouter(prefix="/portfolio", tags=["portfolio"])
portfolio_agent = PortfolioIntelligenceAgent(
    client=get_model_client(),
    model=settings.OPENAI_MODEL,
    reasoning_effort=settings.OPENAI_REASONING_EFFORT,
)


@router.post("/insights", response_model=PortfolioInsightResponse)
def generate_portfolio_insight(
    principal: AdminPrincipal = Depends(require_insight_operator),  # noqa: B008
    database: Session = Depends(get_db),  # noqa: B008
) -> PortfolioInsightResponse:
    """Generate or reuse an insight report for the exact current aggregate snapshot."""
    try:
        result = portfolio_agent.generate(database, actor_id=principal.object_id)
        database.commit()
    except ValueError as error:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except (APIError, RuntimeError, TypeError, KeyError) as error:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Portfolio analysis could not be completed") from error
    return PortfolioInsightResponse(
        id=result.record.id,
        input_fingerprint=result.record.input_fingerprint,
        model_name=result.record.model_name,
        generated_by=result.record.generated_by,
        created_at=result.record.created_at,
        reused=result.reused,
        report=result.report,
    )
