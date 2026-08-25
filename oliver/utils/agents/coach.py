"""Model-backed Idea Coach Agent and its host-side output contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from openai import OpenAI
from sqlalchemy.orm import Session

from utils.model_provider import parse_structured_output, structured_text_config
from utils.models import AssessmentReport, OliverResponse
from utils.postgres import EmailThreadDb
from utils.prompts import build_system_prompt
from utils.scoring.models import CanonicalAssessment
from utils.templates import render_assessment_email, render_oliver_email
from utils.tools.tool_handlers import handle_tool_call
from utils.tools.tool_schema import TOOL_SCHEMAS


class AgentContractError(RuntimeError):
    """The Coach returned a valid schema shape that the host cannot authorize."""


@dataclass(frozen=True)
class CoachAgentResult:
    """Validated Coach output plus operational provenance from one run."""

    response: OliverResponse
    prompt_tokens: int
    completion_tokens: int
    related_threads: tuple[tuple[EmailThreadDb, float], ...]


class CoachAgent:
    """Use the configured provider to resolve and communicate one email request."""

    def __init__(
        self,
        *,
        client: OpenAI,
        model: str,
        reasoning_effort: str,
        embedding_model: str,
        embedding_dimensions: int,
        max_tool_rounds: int,
    ) -> None:
        self._client = client
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._max_tool_rounds = max_tool_rounds

    def respond(
        self,
        *,
        database: Session | None,
        current_thread: EmailThreadDb | None,
        email_thread: str,
        canonical_context: str | None,
    ) -> CoachAgentResult:
        """Return a Coach response, with tools only when persistent thread context exists."""
        input_items: list[Any] = [
            {
                "role": "user",
                "content": "Resolve the latest inbound message in the supplied email thread.",
            }
        ]
        related_threads: dict[UUID, tuple[EmailThreadDb, float]] = {}
        prompt_tokens = 0
        completion_tokens = 0

        for _tool_round in range(self._max_tool_rounds):
            request_options: dict[str, Any] = {
                "model": self._model,
                "instructions": build_system_prompt(email_thread=email_thread, canonical_assessment=canonical_context),
                "input": input_items,
                "text": structured_text_config(OliverResponse),
                "reasoning": {"effort": self._reasoning_effort},
                "include": ["web_search_call.action.sources"],
                "store": False,
            }
            if database is not None and current_thread is not None:
                request_options["tools"] = TOOL_SCHEMAS
            model_response = self._client.responses.create(
                **request_options,
            )
            if model_response.usage is not None:
                prompt_tokens += model_response.usage.input_tokens
                completion_tokens += model_response.usage.output_tokens
            input_items.extend(model_response.output)

            function_calls = [item for item in model_response.output if item.type == "function_call"]
            if not function_calls:
                response = parse_structured_output(model_response, OliverResponse)
                return CoachAgentResult(
                    response=response,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    related_threads=tuple(sorted(related_threads.values(), key=lambda match: match[1])),
                )

            if database is None or current_thread is None:
                raise AgentContractError("Coach requested a tool in a tool-free preview")

            for function_call in function_calls:
                tool_output, matches = handle_tool_call(
                    client=self._client,
                    db=database,
                    current_thread=current_thread,
                    tool_name=function_call.name,
                    tool_arguments=function_call.arguments,
                    embedding_model=self._embedding_model,
                    embedding_dimensions=self._embedding_dimensions,
                )
                for related_thread, cosine_distance in matches:
                    previous_match = related_threads.get(related_thread.id)
                    if previous_match is None or cosine_distance < previous_match[1]:
                        related_threads[related_thread.id] = (related_thread, cosine_distance)
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": function_call.call_id,
                        "output": tool_output,
                    }
                )

        raise RuntimeError("Oliver exceeded the maximum number of tool-call rounds")


def render_coach_response(response: OliverResponse, assessment: CanonicalAssessment | None) -> str | None:
    """Render an authorized Coach response without coercing missing content."""
    if response.action == "NO_REPLY":
        return None
    if response.subject is None:
        raise AgentContractError("SEND_EMAIL response has no subject")
    if response.reply_kind == "assessment":
        if response.report is None or assessment is None:
            raise AgentContractError("Assessment reply requires a canonical assessment and report")
        _validate_assessment_report(response.report, assessment)
        return render_assessment_email(subject=response.subject, report=response.report, assessment=assessment)
    if response.content_html is None:
        raise AgentContractError("Message reply has no HTML content")
    return render_oliver_email(subject=response.subject, content_html=response.content_html)


def _validate_assessment_report(report: AssessmentReport, assessment: CanonicalAssessment) -> None:
    """Reject prose that is not grounded in the active transition policy contract."""
    approved_ids = {criterion.criterion_id for criterion in assessment.criteria}
    referenced_ids: set[str] = set()
    for item in report.coaching_recommendations:
        referenced_ids.update(item.criterion_ids)
    if report.approach_guidance is not None:
        referenced_ids.update(report.approach_guidance.criterion_ids)
    for item in report.opportunities:
        referenced_ids.update(item.criterion_ids)
    if report.path_forward is not None:
        referenced_ids.update(report.path_forward.criterion_ids)
    for item in report.next_steps:
        referenced_ids.update(item.criterion_ids)
    unknown_ids = referenced_ids - approved_ids
    if unknown_ids:
        raise AgentContractError(f"Assessment report references unapproved criteria: {sorted(unknown_ids)}")

    if assessment.response_depth.value == "BRIEF":
        if len(report.working_well) > 2 or len(report.coaching_recommendations) > 3:
            raise AgentContractError("A brief assessment exceeds the allowed evidence-focused item count")
        if report.approach_guidance is not None or report.opportunities or report.path_forward is not None:
            raise AgentContractError("A brief assessment contains sections reserved for deeper evidence")
        if len(report.next_steps) > 3:
            raise AgentContractError("A brief assessment contains too many next steps")
