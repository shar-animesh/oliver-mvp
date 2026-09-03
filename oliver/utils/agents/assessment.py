"""Evidence interpretation boundary for Oliver's canonical assessment policy."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal, Protocol

from openai import OpenAI
from pydantic import BaseModel, Field, model_validator

from utils.email_content import current_message_text
from utils.evidence_contracts import bound_finding_items, bound_finding_text
from utils.model_provider import (
    StructuredOutputError,
    call_with_bounded_provider_retry,
    parse_structured_output,
    structured_text_config,
)
from utils.prompts import assessment_agent_prompt
from utils.scoring import CanonicalAssessment, DimensionScore, DIStage, assess_email, consolidate_dimensions
from utils.scoring.exceptions import UnassessableEmailError
from utils.scoring.service import DIMENSION_METADATA
from utils.scoring.weights import DIMENSIONS
from utils.transition_policy import CriterionFinding, active_transition_policy_set, policy_for_stage, terminal_policy_for_stage

_EXPLICIT_ASSESSMENT = re.compile(r"\b(?:assess|assessment|evaluate|evaluation|reassess|re-assess|score|review my idea)\b", re.IGNORECASE)
_AI_SIGNAL = re.compile(
    r"\b(?:AI|artificial intelligence|machine learning|ML|LLM|GenAI|NLP|RAG|computer vision|anomaly detection|forecasting|predictive)\b",
    re.IGNORECASE,
)
_INITIATIVE_SIGNAL = re.compile(
    r"\b(?:idea|initiative|proposal|pilot|proof[- ]of[- ]concept|PoC|we\s+(?:want|plan|propose|intend|will|should)|"
    r"(?:use|using|build|develop|implement|apply|automate|predict|detect|classify|forecast|extract|recommend)\b)",
    re.IGNORECASE,
)
_NEW_EVIDENCE = re.compile(
    r"\b(?:new evidence|updated|attached|tested|testing|pilot(?:ed)?|result(?:s)?|achieved|accuracy|baseline|measured|"
    r"validated|completed|data (?:is|are|was|were|has|have)|reduced|increased|improved|confirmed)\b",
    re.IGNORECASE,
)
_SHORT_CONVERSATION = re.compile(
    r"^\s*(?:thanks|thank you|hello|hi|please explain|can you (?:explain|clarify)|what do you mean|any update|status update)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AssessmentRequest:
    """Evidence required to decide whether and how to run canonical assessment."""

    subject: str | None
    latest_message_html: str
    inbound_messages_html: tuple[str, ...]
    has_previous_assessment: bool
    attachment_texts: tuple[str, ...] = ()
    current_stage: DIStage = DIStage.DI1


def _should_assess(request: AssessmentRequest) -> bool:
    latest_text = current_message_text(request.latest_message_html)
    subject_and_body = f"{request.subject or ''}\n{latest_text}"
    if _EXPLICIT_ASSESSMENT.search(latest_text):
        return True
    if request.has_previous_assessment:
        return bool(_NEW_EVIDENCE.search(latest_text))
    if _EXPLICIT_ASSESSMENT.search(request.subject or ""):
        return True
    if len(latest_text) < 20:
        return False
    if _SHORT_CONVERSATION.search(latest_text) and len(latest_text) < 160:
        return False
    return bool(_AI_SIGNAL.search(subject_and_body) and _INITIATIVE_SIGNAL.search(subject_and_body))


def _accumulated_evidence(message_html: tuple[str, ...], attachment_texts: tuple[str, ...]) -> str:
    """Build one ordered evidence view without repeating identical message bodies."""
    evidence: list[str] = []
    seen: set[str] = set()
    for content_html in message_html:
        normalized = current_message_text(content_html)
        fingerprint = normalized.casefold()
        if normalized and fingerprint not in seen:
            evidence.append(normalized)
            seen.add(fingerprint)
    for extracted_text in attachment_texts:
        normalized = extracted_text.strip()
        fingerprint = normalized.casefold()
        if normalized and fingerprint not in seen:
            evidence.append(f"Attachment evidence:\n{normalized}")
            seen.add(fingerprint)
    return "\n\n".join(evidence)


class AssessmentAgent(Protocol):
    """Shared interface for configured assessment evaluators."""

    def assess(self, request: AssessmentRequest) -> CanonicalAssessment | None:
        """Assess accumulated evidence when the request is assessment-worthy."""


class RubricAssessmentAgent:
    """Offline fallback evaluator using the deterministic evidence rubric."""

    def assess(self, request: AssessmentRequest) -> CanonicalAssessment | None:
        if not _should_assess(request):
            return None
        evidence = _accumulated_evidence(request.inbound_messages_html, request.attachment_texts)
        try:
            return assess_email(request.subject, evidence, request.current_stage)
        except UnassessableEmailError:
            return None


DimensionName = Literal[
    "ideaCompleteness",
    "ideaQuality",
    "strategicValue",
    "technicalFeasibility",
    "executionReadiness",
]


class EvidenceFinding(BaseModel):
    """One model-interpreted dimension finding with no policy authority."""

    dimension: DimensionName
    state: Literal["SATISFIED", "CONCERN", "UNKNOWN", "NOT_APPLICABLE"]
    value: int | None = Field(default=None, ge=0, le=100)
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=20)
    evidence: list[str] = Field(default_factory=list, max_length=12)
    gaps: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_state_value_pair(self) -> "EvidenceFinding":
        """Keep unknown evidence separate from negative numeric assessment."""
        if self.state in {"UNKNOWN", "NOT_APPLICABLE"} and self.value is not None:
            raise ValueError(f"{self.state} findings cannot have a numeric value")
        if self.state in {"SATISFIED", "CONCERN"} and self.value is None:
            raise ValueError(f"{self.state} findings require a numeric value")
        return self


class ModelCriterionFinding(BaseModel):
    """Provider-facing criterion result normalized into the canonical contract after parsing."""

    criterion_id: str
    state: Literal["SATISFIED", "CONCERN", "UNKNOWN", "NOT_APPLICABLE"]
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=10)
    evidence: list[str] = Field(default_factory=list, max_length=12)
    gaps: list[str] = Field(default_factory=list, max_length=12)


class EvidenceFindings(BaseModel):
    """Evidence interpretation for portfolio dimensions and approved transition criteria."""

    findings: list[EvidenceFinding] = Field(min_length=5, max_length=5)
    criterion_findings: list[ModelCriterionFinding] = Field(default_factory=list)


class AssessmentContractError(RuntimeError):
    """A schema-valid response did not satisfy Oliver's canonical identity contract."""


def _bounded_evidence(evidence: str, maximum_chars: int) -> str:
    """Keep initial context and newest evidence within a configured request bound."""
    if len(evidence) <= maximum_chars:
        return evidence
    marker = "\n\n[Earlier evidence omitted at configured boundary]\n\n"
    if maximum_chars <= len(marker):
        return evidence[:maximum_chars]
    available = maximum_chars - len(marker)
    beginning = max(1, available // 3)
    return evidence[:beginning] + marker + evidence[-(available - beginning) :]


class EvidenceAssessmentAgent:
    """Use a model for evidence judgment and code for official scoring policy."""

    def __init__(
        self,
        *,
        client: OpenAI,
        model: str,
        reasoning_effort: str,
        max_evidence_chars: int,
        request_timeout_seconds: float = 300,
        response_retries: int = 1,
    ) -> None:
        self._client = client
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._max_evidence_chars = max_evidence_chars
        self._request_timeout_seconds = request_timeout_seconds
        self._response_retries = response_retries

    def assess(self, request: AssessmentRequest) -> CanonicalAssessment | None:
        if not _should_assess(request):
            return None
        evidence = _accumulated_evidence(request.inbound_messages_html, request.attachment_texts)
        if len(evidence.strip()) < 10:
            return None
        payload = {
            "subject": request.subject or "(no subject)",
            "current_stage": request.current_stage.value,
            "current_stage_name": request.current_stage.display_name,
            "accumulated_evidence": _bounded_evidence(evidence, self._max_evidence_chars),
        }
        transition_policy_set = active_transition_policy_set()
        transition_policy = policy_for_stage(request.current_stage)
        terminal_policy = terminal_policy_for_stage(request.current_stage)
        configured_policy = transition_policy or terminal_policy
        payload["transition_policy_version"] = transition_policy_set.version
        payload["approved_transition_policy"] = configured_policy.model_dump(mode="json") if configured_policy is not None else None
        expected_criterion_ids = {criterion.criterion_id for criterion in configured_policy.criteria} if configured_policy is not None else set()

        def request_validated_findings(remaining_seconds: float) -> EvidenceFindings:
            response = self._client.responses.create(
                model=self._model,
                instructions=assessment_agent_prompt(),
                input=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                text=structured_text_config(EvidenceFindings),
                reasoning={"effort": self._reasoning_effort},
                store=False,
                timeout=min(self._request_timeout_seconds, remaining_seconds),
            )
            output = parse_structured_output(response, EvidenceFindings)
            findings_by_name = {finding.dimension: finding for finding in output.findings}
            if len(findings_by_name) != len(output.findings) or set(findings_by_name) != set(DIMENSIONS):
                raise AssessmentContractError("Assessment response did not contain each canonical dimension exactly once")
            returned_criterion_ids = {finding.criterion_id for finding in output.criterion_findings}
            if len(returned_criterion_ids) != len(output.criterion_findings) or returned_criterion_ids != expected_criterion_ids:
                raise AssessmentContractError("Assessment response did not contain each approved transition criterion exactly once")
            return output

        output = call_with_bounded_provider_retry(
            request_validated_findings,
            timeout_seconds=self._request_timeout_seconds * (self._response_retries + 1),
            max_retries=self._response_retries,
            retryable_result_errors=(StructuredOutputError, AssessmentContractError),
        )
        findings_by_name = {finding.dimension: finding for finding in output.findings}

        criterion_findings = [
            CriterionFinding(
                criterion_id=finding.criterion_id,
                state=finding.state,
                confidence=finding.confidence,
                summary=bound_finding_text(finding.summary),
                evidence=bound_finding_items(finding.evidence),
                gaps=bound_finding_items(finding.gaps),
            )
            for finding in output.criterion_findings
        ]

        dimensions: list[DimensionScore] = []
        for dimension_name in DIMENSIONS:
            finding = findings_by_name[dimension_name]
            label, agent = DIMENSION_METADATA[dimension_name]
            dimensions.append(
                DimensionScore(
                    agent=agent,
                    dimension=dimension_name,
                    dimension_label=label,
                    state=finding.state,
                    value=finding.value,
                    confidence=finding.confidence,
                    weight=0,
                    summary=bound_finding_text(finding.summary),
                    evidence=bound_finding_items(finding.evidence),
                    gaps=bound_finding_items(finding.gaps),
                    scored_by=f"llm:{self._model}",
                )
            )
        return consolidate_dimensions(
            dimensions,
            request.current_stage,
            criterion_findings=criterion_findings,
            model_version=f"evidence-agent:{self._model}",
        )


def build_assessment_agent(
    *,
    client: OpenAI,
    mode: Literal["llm", "rubric"],
    model: str,
    reasoning_effort: str,
    max_evidence_chars: int,
    request_timeout_seconds: float = 300,
    response_retries: int = 1,
) -> AssessmentAgent:
    """Construct the configured evaluator from one shared composition boundary."""
    if mode == "rubric":
        return RubricAssessmentAgent()
    return EvidenceAssessmentAgent(
        client=client,
        model=model,
        reasoning_effort=reasoning_effort,
        max_evidence_chars=max_evidence_chars,
        request_timeout_seconds=request_timeout_seconds,
        response_retries=response_retries,
    )


def canonical_assessment_context(assessment: CanonicalAssessment | None) -> str | None:
    """Serialize the single canonical result supplied to the Coach Agent."""
    if assessment is None:
        return None
    return json.dumps(
        {
            "current_stage": assessment.current_stage.value,
            "composite_score": assessment.composite_score,
            "transition_target": assessment.transition_target.value if assessment.transition_target is not None else None,
            "recommended_next_stage": (assessment.recommended_next_stage.value if assessment.recommended_next_stage is not None else None),
            "gate_outcome": assessment.gate_outcome.value,
            "lifecycle_state": assessment.lifecycle_state.value,
            "composite_confidence": assessment.composite_confidence,
            "requires_human_review": assessment.requires_human_review,
            "response_depth": assessment.response_depth.value,
            "rating": assessment.rating,
            "score_rationale": assessment.score_rationale,
            "transition_rationale": assessment.transition_rationale,
            "model_version": assessment.model_version,
            "weight_set_version": assessment.weight_set_version,
            "transition_policy_version": assessment.transition_policy_version,
            "dimensions": [
                {
                    "dimension": dimension.dimension,
                    "label": dimension.dimension_label,
                    "state": dimension.state.value,
                    "score": dimension.value,
                    "confidence": dimension.confidence,
                    "weight": dimension.weight,
                }
                for dimension in assessment.dimensions
            ],
            "criteria": [criterion.model_dump(mode="json") for criterion in assessment.criteria],
        }
    )
