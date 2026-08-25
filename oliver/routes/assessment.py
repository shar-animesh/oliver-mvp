"""Non-persistent Assessment Agent laboratory for authorized operators."""

from fastapi import APIRouter, Depends, HTTPException, status
from openai import APIError, APITimeoutError

from config import get_settings
from utils.agents import (
    AgentContractError,
    AssessmentAgent,
    AssessmentRequest,
    CoachAgent,
    build_assessment_agent,
    canonical_assessment_context,
    render_coach_response,
)
from utils.model_provider import get_model_client
from utils.models.api.assessment import AssessmentTestRequest, AssessmentTestResult
from utils.security import AdminPrincipal, require_insight_operator

settings = get_settings()
client = get_model_client()
assessment_agent: AssessmentAgent = build_assessment_agent(
    client=client,
    mode=settings.ASSESSMENT_EVALUATOR_MODE,
    model=settings.OPENAI_MODEL,
    reasoning_effort=settings.ASSESSMENT_REASONING_EFFORT,
    max_evidence_chars=settings.ASSESSMENT_MAX_EVIDENCE_CHARS,
    request_timeout_seconds=settings.OPENAI_REQUEST_TIMEOUT_SECONDS,
    response_retries=settings.ASSESSMENT_RESPONSE_RETRIES,
)
coach_agent = CoachAgent(
    client=client,
    model=settings.OPENAI_MODEL,
    reasoning_effort=settings.OPENAI_REASONING_EFFORT,
    embedding_model=settings.OPENAI_EMBEDDING_MODEL,
    embedding_dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
    max_tool_rounds=8,
)

router = APIRouter(prefix="/assessment", tags=["assessment"])


@router.post("/test", response_model=AssessmentTestResult)
def test_assessment(
    request: AssessmentTestRequest,
    _principal: AdminPrincipal = Depends(require_insight_operator),  # noqa: B008
) -> AssessmentTestResult:
    """Evaluate evidence and draft its complete reply without persistence or delivery."""
    try:
        assessment = assessment_agent.assess(
            AssessmentRequest(
                subject=f"Assessment requested: {request.subject}",
                latest_message_html=f"Please assess this initiative.\n\n{request.evidence}",
                inbound_messages_html=(request.evidence,),
                has_previous_assessment=False,
                current_stage=request.current_stage,
            )
        )
    except APITimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"The Assessment Agent did not respond within {settings.OPENAI_REQUEST_TIMEOUT_SECONDS} seconds",
        ) from error
    except APIError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="The Assessment Agent provider call failed") from error
    except (RuntimeError, TypeError, KeyError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The Assessment Agent could not produce a valid structured assessment",
        ) from error
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The supplied evidence could not be assessed",
        )

    email_thread = f'<email direction="INBOUND" sender="assessment-lab-user">\nSubject: {request.subject}\n\n{request.evidence}\n</email>'
    try:
        coach_result = coach_agent.respond(
            database=None,
            current_thread=None,
            email_thread=email_thread,
            canonical_context=canonical_assessment_context(assessment),
        )
    except APITimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"The Coach Agent did not respond within {settings.OPENAI_REQUEST_TIMEOUT_SECONDS} seconds",
        ) from error
    except APIError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="The Coach Agent provider call failed") from error
    except (RuntimeError, TypeError, KeyError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The Coach Agent could not produce a valid structured response",
        ) from error

    try:
        email_html = render_coach_response(coach_result.response, assessment)
    except AgentContractError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The Coach response did not satisfy the assessment email contract",
        ) from error
    return AssessmentTestResult(
        **assessment.model_dump(),
        response_action=coach_result.response.action,
        response_kind=coach_result.response.reply_kind,
        email_subject=coach_result.response.subject,
        email_html=email_html,
    )
