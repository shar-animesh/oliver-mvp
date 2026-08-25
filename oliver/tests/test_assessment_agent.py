"""Assessment Agent contract tests with a provider stub."""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from utils.agents.assessment import (
    AssessmentRequest,
    EvidenceAssessmentAgent,
    EvidenceFinding,
    EvidenceFindings,
    _bounded_evidence,
)
from utils.evidence_contracts import (
    FINDING_ITEM_MAX_CHARS,
    FINDING_ITEMS_MAX,
    FINDING_SUMMARY_MAX_CHARS,
    bound_finding_items,
    bound_finding_text,
)
from utils.scoring import DIStage
from utils.scoring.weights import DIMENSIONS, active_weight_set
from utils.transition_policy import CriterionFinding, CriterionState, policy_for_stage


class _ResponsesStub:
    def __init__(self, output: EvidenceFindings) -> None:
        self.output = output
        self.request: dict[str, Any] | None = None

    def create(self, **request: Any) -> SimpleNamespace:
        self.request = request
        return SimpleNamespace(output=[SimpleNamespace(content=[SimpleNamespace(text=self.output.model_dump_json())])])


class _ClientStub:
    def __init__(self, output: EvidenceFindings) -> None:
        self.responses = _ResponsesStub(output)


class _ResponsesSequenceStub:
    def __init__(self, outputs: list[EvidenceFindings]) -> None:
        self.outputs = outputs
        self.calls = 0

    def create(self, **_request: Any) -> SimpleNamespace:
        output = self.outputs[self.calls]
        self.calls += 1
        return SimpleNamespace(output=[SimpleNamespace(content=[SimpleNamespace(text=output.model_dump_json())])])


class _ClientSequenceStub:
    def __init__(self, outputs: list[EvidenceFindings]) -> None:
        self.responses = _ResponsesSequenceStub(outputs)


def _output(stage: DIStage = DIStage.DI1) -> EvidenceFindings:
    policy = policy_for_stage(stage)
    return EvidenceFindings(
        findings=[
            EvidenceFinding(
                dimension=dimension,
                state="SATISFIED",
                value=75,
                confidence=0.8,
                summary="The accumulated evidence supports this dimension at the stated level.",
                evidence=["A concrete evidence statement is present"],
                gaps=["Further independently verified evidence would improve confidence"],
            )
            for dimension in DIMENSIONS
        ],
        criterion_findings=(
            [
                CriterionFinding(
                    criterion_id=criterion.criterion_id,
                    state=CriterionState.SATISFIED,
                    confidence=0.8,
                    summary="The accumulated evidence supports this approved criterion.",
                    evidence=["A concrete evidence statement is present"],
                ).model_dump()
                for criterion in policy.criteria
            ]
            if policy is not None
            else []
        ),
    )


def test_model_interprets_evidence_but_policy_assigns_weights() -> None:
    client = _ClientStub(_output(DIStage.DI3))
    agent = EvidenceAssessmentAgent(
        client=client,  # type: ignore[arg-type]
        model="provider/model-from-env",
        reasoning_effort="high",
        max_evidence_chars=10_000,
    )
    result = agent.assess(
        AssessmentRequest(
            subject="Predictive maintenance assessment",
            latest_message_html="We want to assess an AI predictive maintenance pilot using sensor data.",
            inbound_messages_html=("We want to assess an AI predictive maintenance pilot using sensor data.",),
            has_previous_assessment=False,
            current_stage=DIStage.DI3,
        )
    )

    assert result is not None
    assert result.composite_score == 75
    assert result.model_version == "evidence-agent:provider/model-from-env"
    assert {item.dimension: item.weight for item in result.dimensions} == active_weight_set().weights_for("DI3")
    assert all(item.scored_by == "llm:provider/model-from-env" for item in result.dimensions)
    assert client.responses.request is not None
    assert client.responses.request["model"] == "provider/model-from-env"


def test_non_initiative_follow_up_does_not_call_model() -> None:
    client = _ClientStub(_output())
    agent = EvidenceAssessmentAgent(
        client=client,  # type: ignore[arg-type]
        model="provider/model-from-env",
        reasoning_effort="high",
        max_evidence_chars=10_000,
    )
    result = agent.assess(
        AssessmentRequest(
            subject="Re: Previous idea",
            latest_message_html="Thanks, please explain that.",
            inbound_messages_html=("Thanks, please explain that.",),
            has_previous_assessment=True,
        )
    )

    assert result is None
    assert client.responses.request is None


def test_retries_schema_valid_response_with_incomplete_policy_identity() -> None:
    valid_output = _output()
    incomplete_output = valid_output.model_copy(
        update={"criterion_findings": valid_output.criterion_findings[:-1]},
    )
    client = _ClientSequenceStub([incomplete_output, valid_output])
    agent = EvidenceAssessmentAgent(
        client=client,  # type: ignore[arg-type]
        model="provider/model-from-env",
        reasoning_effort="medium",
        max_evidence_chars=10_000,
        request_timeout_seconds=30,
        response_retries=1,
    )

    result = agent.assess(
        AssessmentRequest(
            subject="Predictive maintenance assessment",
            latest_message_html="Assess an AI predictive maintenance pilot using sensor data.",
            inbound_messages_html=("Assess an AI predictive maintenance pilot using sensor data.",),
            has_previous_assessment=False,
        )
    )

    assert result is not None
    assert client.responses.calls == 2


def test_long_evidence_is_preserved_in_provider_payload() -> None:
    client = _ClientStub(_output())
    agent = EvidenceAssessmentAgent(
        client=client,  # type: ignore[arg-type]
        model="provider/model-from-env",
        reasoning_effort="medium",
        max_evidence_chars=120_000,
    )
    evidence = "Assess this AI service-routing pilot. " + ("Measured operational evidence. " * 100)

    result = agent.assess(
        AssessmentRequest(
            subject="Service request routing pilot",
            latest_message_html=evidence,
            inbound_messages_html=(evidence,),
            has_previous_assessment=False,
        )
    )

    assert result is not None
    assert len(evidence) > 2_300
    assert client.responses.request is not None
    request_payload = json.loads(client.responses.request["input"][0]["content"])
    assert request_payload["accumulated_evidence"] == evidence.strip()


def test_model_authored_findings_are_bounded_after_valid_parsing() -> None:
    summary = "A complete sentence about supplied evidence. " * 20
    statements = [f"Evidence statement {index} " + ("detail " * 80) for index in range(5)]

    bounded_summary = bound_finding_text(summary)
    bounded_statements = bound_finding_items(statements)

    assert len(bounded_summary) <= FINDING_SUMMARY_MAX_CHARS
    assert bounded_summary.endswith("…")
    assert len(bounded_statements) == FINDING_ITEMS_MAX
    assert all(len(statement) <= FINDING_ITEM_MAX_CHARS for statement in bounded_statements)


def test_evidence_bound_holds_when_limit_is_shorter_than_the_marker() -> None:
    assert _bounded_evidence("abcdefghij", 4) == "abcd"


def test_evidence_bound_preserves_beginning_and_newest_evidence() -> None:
    bounded = _bounded_evidence("a" * 100 + "newest", 70)
    assert len(bounded) == 70
    assert bounded.startswith("a")
    assert bounded.endswith("newest")


@pytest.mark.parametrize(
    ("state", "value"),
    [
        ("UNKNOWN", 10),
        ("NOT_APPLICABLE", 50),
        ("SATISFIED", None),
        ("CONCERN", None),
    ],
)
def test_finding_contract_rejects_inconsistent_state_and_value(state: str, value: int | None) -> None:
    with pytest.raises(ValidationError):
        EvidenceFinding(
            dimension="technicalFeasibility",
            state=state,  # type: ignore[arg-type]
            value=value,
            confidence=0.8,
            summary="The supplied evidence supports a contract consistency test.",
        )
