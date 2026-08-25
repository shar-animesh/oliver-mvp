"""Email normalization, deterministic evidence rubric, and canonical consolidation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from utils.email_content import current_message_text
from utils.transition_policy import (
    CriterionFinding,
    CriterionState,
    GateOutcome,
    active_transition_policy_set,
    evaluate_terminal_stage,
    evaluate_transition,
    policy_for_stage,
    terminal_policy_for_stage,
    unavailable_transition_evaluation,
)

from .exceptions import UnassessableEmailError
from .models import CanonicalAssessment, DimensionScore, DIStage, LifecycleState, Submission
from .weights import DIMENSIONS, active_weight_set

COMPLETENESS_FLOOR = 30
CONFIDENCE_FLOOR = 0.6

DIMENSION_METADATA = {
    "ideaCompleteness": ("Idea Completeness", "DocGuard"),
    "ideaQuality": ("Idea Quality", "IdeaPulse"),
    "strategicValue": ("Strategic / Business Value", "ValuePulse"),
    "technicalFeasibility": ("Technical Feasibility", "TechScope"),
    "executionReadiness": ("Execution Readiness", "PathFinder"),
}

_QUANTITY = re.compile(
    r"\d[\d,.]*\s*(%|EUR|USD|GBP|€|\$|£|million|mio|billion|bn|hours?|days?|weeks?|months?|years?|mins?|[kKmM]\b|pct|percent)",
    re.IGNORECASE,
)
_SPONSOR = re.compile(
    r"\b(?:VP|SVP|EVP|CEO|CTO|CFO|COO|CIO|CISO|President|Vice[- ]President|Chief|Head\s+of)\b"
    r"|\b(?:Director|Manager|Lead|Officer|Owner)\s+of\s+[A-Z][\w&/ -]{2,40}"
    r"|\b(?:on behalf of|sponsored by|backed by|reporting to)\s+[A-Za-z][\w .-]{2,40}",
    re.IGNORECASE,
)
_DATA = re.compile(
    r"\b(?:data|logs?|records?|readings?|telemetry)\s+from\s+(?:our\s+|the\s+)?[A-Z][\w -]{2,30}"
    r"|\b(?:system|database|historian|dataset|warehouse|repository|API|feed|telemetry|sensor data)\b"
    r"|\b(?:historical|past|existing|archived)\s+(?:[\w-]+\s+){0,3}(?:records?|data|documents?|reports?|contracts?|logs?)\b",
    re.IGNORECASE,
)
_APPROACH = re.compile(
    r"\b(?:using|use|build|building|train|develop|deploy|implement|apply|leverage|integrate)\s+(?:an?\s+|the\s+)?[\w .-]{3,40}"
    r"|\b(?:predict|detect|classify|forecast|automat\w+|recommend|extract|summari[sz]e|cluster|rank|score|flag|identif\w+|optimi[sz]e)\b"
    r"|\b(?:machine learning|deep learning|neural network|LLMs?|generative AI|GenAI|copilot|chatbot|RAG"
    r"|AI[- ](?:powered|based|driven|assisted)|NLP|anomaly detection|time[- ]series|computer vision|OCR)\b",
    re.IGNORECASE,
)
_EXECUTION = re.compile(
    r"\bteam of\s+\w+|\b\d+\s+(?:people|persons?|engineers?|developers?|analysts?|FTEs?|resources?|members?)\b"
    r"|\b(?:ready to|prepared to|able to|we can|we have|I've got)\s+[\w .-]{3,40}"
    r"|\bnext\s+(?:quarter|month|sprint|week|year)\b"
    r"|\b(?:prototype|pilot|proof[- ]of[- ]concept|PoC|kick[- ]?off|roll ?out)\b"
    r"|\bwithin\s+\d+\s+(?:weeks?|months?|quarters?)\b",
    re.IGNORECASE,
)
_SUBJECT_PREFIX = re.compile(r"^(?:(?:re|fw|fwd)\s*:\s*)+", re.IGNORECASE)


@dataclass(frozen=True)
class _Check:
    passed: bool
    points: int
    evidence: str


@dataclass(frozen=True)
class _Signals:
    quantity: str | None
    approach: str | None
    data: str | None
    sponsor: str | None
    execution: str | None


def email_to_submission(subject: str | None, content_html: str, stage: DIStage = DIStage.DI1) -> Submission:
    """Normalize an inbound email into the historical scoring input contract."""
    body = current_message_text(content_html)
    if len(body) < 10:
        raise UnassessableEmailError("Email body has no assessable content after cleaning")
    cleaned_subject = _SUBJECT_PREFIX.sub("", (subject or "").strip())
    title = cleaned_subject if len(cleaned_subject) >= 3 else "Untitled initiative"
    return Submission(title=title[:200], problem_statement=body, current_stage=stage)


def _citation(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if match is None:
        return None
    boundary = text.rfind(". ", 0, match.start())
    start = boundary + 2 if boundary >= 0 else 0
    end = text.find(". ", match.end())
    if end < 0:
        end = min(len(text), match.end() + 70)
    phrase = " ".join(text[start:end].split()).strip(" .")
    if len(phrase) > 140:
        phrase = phrase[:137].rsplit(" ", 1)[0] + "..."
    return phrase


def _signals(text: str) -> _Signals:
    quantity_match = _QUANTITY.search(text)
    return _Signals(
        quantity=quantity_match.group(0).strip() if quantity_match else None,
        approach=_citation(_APPROACH, text),
        data=_citation(_DATA, text),
        sponsor=_citation(_SPONSOR, text),
        execution=_citation(_EXECUTION, text),
    )


def _finalize(checks: list[_Check], summary: str) -> tuple[int, float, str, list[str], list[str]]:
    score = sum(check.points for check in checks if check.passed)
    passed = sum(check.passed for check in checks)
    confidence = round(min(0.95, 0.3 + 0.65 * (passed / len(checks))), 2)
    evidence = [check.evidence for check in checks if check.passed]
    gaps = [check.evidence for check in checks if not check.passed]
    strength = "strong evidence" if passed / len(checks) >= 0.8 else "partial evidence" if passed / len(checks) >= 0.5 else "limited evidence"
    return score, confidence, f"{summary} {passed}/{len(checks)} checks passed, {strength}.", evidence, gaps


def _completeness(text: str, signals: _Signals) -> tuple[int, float, str, list[str], list[str]]:
    checks = [
        _Check(True, 15, f"Problem statement provided ({len(text)} characters)"),
        _Check(
            len(text) >= 50,
            15,
            "Problem statement identifies a concrete process and impact"
            if len(text) >= 50
            else "Add enough problem detail to identify the process and impact",
        ),
        _Check(
            len(text) >= 120,
            10,
            "Problem statement includes supporting context" if len(text) >= 120 else "Add more context, constraints, or cause-and-effect detail",
        ),
        _Check(
            signals.approach is not None, 12, f'Approach evidence: "{signals.approach}"' if signals.approach else "Describe the proposed approach"
        ),
        _Check(
            signals.approach is not None and len(text) >= 80,
            8,
            "Approach has supporting narrative detail"
            if signals.approach is not None and len(text) >= 80
            else "Add implementation detail to the proposed approach",
        ),
        _Check(
            signals.quantity is not None,
            12,
            f'Quantified value evidence: "{signals.quantity}"'
            if signals.quantity
            else "State expected value with a number, percentage, time, or financial measure",
        ),
        _Check(signals.data is not None, 10, f'Data evidence: "{signals.data}"' if signals.data else "Name the data source, system, or document set"),
        _Check(
            signals.sponsor is not None, 8, f'Sponsor evidence: "{signals.sponsor}"' if signals.sponsor else "Name a sponsor or accountable owner"
        ),
        _Check(
            signals.execution is not None,
            5,
            f'Execution evidence: "{signals.execution}"' if signals.execution else "Indicate a team, capacity, pilot, or timeline",
        ),
        _Check(
            len(text) >= 200,
            5,
            "Additional supporting context is present" if len(text) >= 200 else "Add prior work, constraints, or early results",
        ),
    ]
    return _finalize(checks, "Completeness assessed from evidence presence and depth.")


def _quality(text: str, signals: _Signals) -> tuple[int, float, str, list[str], list[str]]:
    clauses = [part for part in re.split(r"[.!?;]", text) if len(part.strip()) > 8]
    depth = sum(value is not None for value in (signals.approach, signals.quantity, signals.data))
    stakeholders = signals.sponsor is not None or signals.execution is not None
    assessable_problem_and_approach = len(text) >= 30 and signals.approach is not None
    checks = [
        _Check(
            len(text) >= 70,
            15,
            "The problem is specific enough for evaluation" if len(text) >= 70 else "Clarify the concrete problem, affected workflow, and users",
        ),
        _Check(
            signals.quantity is not None,
            20,
            f'Impact evidence: "{signals.quantity}"' if signals.quantity else "Quantify the current impact or intended improvement",
        ),
        _Check(
            len(clauses) >= 2,
            15,
            "Problem and consequence are both articulated" if len(clauses) >= 2 else "Explain both the problem and its consequence",
        ),
        _Check(stakeholders, 10, "Stakeholders are identifiable" if stakeholders else "Identify the affected users, sponsor, or delivery team"),
        _Check(
            signals.approach is not None,
            15,
            f'Concrete approach: "{signals.approach}"' if signals.approach else "Describe a concrete solution approach",
        ),
        _Check(
            assessable_problem_and_approach,
            10,
            "Problem and approach can be assessed together"
            if assessable_problem_and_approach
            else "Explain how the approach addresses the stated problem",
        ),
        _Check(
            depth >= 2,
            15,
            f"{depth} supporting evidence types identified" if depth >= 2 else "Add at least two of: approach, measurable value, and data source",
        ),
    ]
    return _finalize(checks, "Idea quality assessed from structural evidence.")


def _value(text: str, signals: _Signals) -> tuple[int, float, str, list[str], list[str]]:
    quantified = signals.quantity is not None
    quantified_with_context = quantified and len(text) >= 80
    quantified_with_detail = quantified and len(text) >= 120
    checks = [
        _Check(quantified, 20, f'Value claim: "{signals.quantity}"' if quantified else "State the expected business or operational value"),
        _Check(quantified, 20, f'Quantified impact: "{signals.quantity}"' if quantified else "Quantify at least one benefit"),
        _Check(
            quantified_with_context,
            15,
            "Efficiency or outcome is expressed with measurable context" if quantified_with_context else "Describe who benefits and how",
        ),
        _Check(
            quantified_with_context,
            15,
            "Scale indicators are present" if quantified_with_context else "Indicate the affected population, volume, or frequency",
        ),
        _Check(
            quantified_with_detail,
            15,
            "Value statement has supporting detail" if quantified_with_detail else "Connect the measure to the intended outcome",
        ),
        _Check(
            (baseline_present := _QUANTITY.search(text[: max(1, len(text) // 2)]) is not None),
            15,
            "A quantified current-state or early baseline is present" if baseline_present else "Add a measurable current-state baseline",
        ),
    ]
    return _finalize(checks, "Strategic value assessed from value claims and quantification.")


def _technical(text: str, signals: _Signals) -> tuple[int, float, str, list[str], list[str]]:
    approach = signals.approach is not None
    data = signals.data is not None
    approach_with_context = approach and len(text) >= 120
    data_with_context = data and len(text) >= 80
    checks = [
        _Check(approach, 20, f'Technical approach: "{signals.approach}"' if approach else "Specify the technical approach"),
        _Check(
            approach_with_context,
            15,
            "Approach includes contextual detail" if approach_with_context else "Add implementation inputs and outputs",
        ),
        _Check(data, 20, f'Data source: "{signals.data}"' if data else "Identify the data source needed by the solution"),
        _Check(
            data_with_context,
            15,
            "Data source is described in context" if data_with_context else "Describe data availability, format, and access",
        ),
        _Check(
            approach or data,
            15,
            "An integration surface can be identified" if approach or data else "Name the system or workflow integration surface",
        ),
        _Check(
            approach and data,
            15,
            "Approach and data evidence support feasibility review" if approach and data else "Connect the proposed approach to a named data source",
        ),
    ]
    return _finalize(checks, "Technical feasibility assessed from approach and data evidence.")


def _execution(text: str, signals: _Signals) -> tuple[int, float, str, list[str], list[str]]:
    sponsor = signals.sponsor is not None
    execution = signals.execution is not None
    checks = [
        _Check(sponsor, 25, f'Sponsor: "{signals.sponsor}"' if sponsor else "Name a sponsor or accountable owner"),
        _Check(sponsor, 10, "A sponsor role or authority is identifiable" if sponsor else "Provide the sponsor's role or name"),
        _Check(execution, 20, f'Capacity evidence: "{signals.execution}"' if execution else "Identify a delivery team or capacity"),
        _Check(execution, 10, "Execution capacity is indicated" if execution else "State who would run the first experiment"),
        _Check(
            30 <= len(text) <= 1200,
            15,
            "The submitted scope is bounded enough for initial review"
            if 30 <= len(text) <= 1200
            else "Bound the first-use case or pilot scope more clearly",
        ),
        _Check(
            sponsor and execution,
            20,
            "Ownership and execution signals are both present" if sponsor and execution else "Add both accountable ownership and an execution plan",
        ),
    ]
    return _finalize(checks, "Execution readiness assessed from ownership, capacity, and scope evidence.")


def _round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _rating(score: int | None) -> str:
    if score is None:
        return "Incomplete"
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Strong"
    if score >= 55:
        return "Developing"
    if score >= 40:
        return "Early"
    return "Nascent"


def consolidate_dimensions(
    dimensions: list[DimensionScore],
    stage: DIStage,
    *,
    criterion_findings: list[CriterionFinding] | None = None,
    model_version: str | None = None,
) -> CanonicalAssessment:
    """Calculate a portfolio score and independently evaluate transition readiness.

    Evaluators may interpret evidence and propose dimension values, but they cannot
    control weights, criterion timing, blocking behavior, lifecycle outcomes, or
    human-review requirements.
    """
    dimensions_by_name = {dimension.dimension: dimension for dimension in dimensions}
    if len(dimensions_by_name) != len(dimensions) or set(dimensions_by_name) != set(DIMENSIONS):
        raise ValueError(f"Assessment must contain each canonical dimension exactly once: {list(DIMENSIONS)}")

    weight_set = active_weight_set()
    stage_weights = weight_set.weights_for(stage.value)
    canonical_dimensions: list[DimensionScore] = []
    for dimension_name in DIMENSIONS:
        finding = dimensions_by_name[dimension_name]
        label, agent = DIMENSION_METADATA[dimension_name]
        canonical_dimensions.append(
            finding.model_copy(
                update={
                    "agent": agent,
                    "dimension_label": label,
                    "weight": stage_weights[dimension_name],
                }
            )
        )

    scores = {dimension.dimension: dimension.value for dimension in canonical_dimensions}
    confidences = {dimension.dimension: dimension.confidence for dimension in canonical_dimensions}
    lowest_confidence_dimension = min(DIMENSIONS, key=lambda key: (confidences[key], DIMENSIONS.index(key)))

    if any(score is None for score in scores.values()):
        composite = None
        confidence = None
        unknown_dimensions = [name for name, score in scores.items() if score is None]
        score_rationale = "Portfolio composite is withheld because dimensions remain unknown: " + ", ".join(unknown_dimensions)
    else:
        numeric_scores = {key: score for key, score in scores.items() if score is not None}
        weighted_score = sum(Decimal(numeric_scores[key]) * Decimal(stage_weights[key]) for key in DIMENSIONS)
        weighted_confidence = sum(Decimal(str(confidences[key])) * Decimal(stage_weights[key]) for key in DIMENSIONS)
        composite = _round_half_up(weighted_score / Decimal(100))
        confidence = float((weighted_confidence / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        score_rationale = f"Composite {composite}/100 is a stage-weighted portfolio signal only; it does not determine lifecycle movement."

    transition_policy_set = active_transition_policy_set()
    transition_policy = policy_for_stage(stage)
    terminal_policy = terminal_policy_for_stage(stage)
    if transition_policy is None and terminal_policy is None:
        transition = unavailable_transition_evaluation(stage, transition_policy_set.version)
    else:
        configured_policy = transition_policy or terminal_policy
        assert configured_policy is not None
        findings = criterion_findings
        if findings is None:
            findings = [
                CriterionFinding(
                    criterion_id=criterion.criterion_id,
                    state=CriterionState.UNKNOWN,
                    confidence=0.0,
                    summary="The fallback rubric did not evaluate this transition criterion.",
                    gaps=[criterion.description],
                )
                for criterion in configured_policy.criteria
            ]
        if transition_policy is not None:
            transition = evaluate_transition(
                transition_policy,
                findings,
                policy_version=transition_policy_set.version,
                confidence_floor=CONFIDENCE_FLOOR,
            )
        else:
            assert terminal_policy is not None
            transition = evaluate_terminal_stage(
                terminal_policy,
                findings,
                policy_version=transition_policy_set.version,
                confidence_floor=CONFIDENCE_FLOOR,
            )

    lifecycle_state = {
        GateOutcome.ADVANCE: LifecycleState.ACTIVE,
        GateOutcome.CONDITIONAL_ADVANCE: LifecycleState.ACTIVE,
        GateOutcome.HOLD_FOR_EVIDENCE: LifecycleState.STALLED,
        GateOutcome.DO_NOT_ADVANCE: LifecycleState.ASSESSED,
        GateOutcome.CONTINUE_MONITORING: LifecycleState.ACTIVE,
    }[transition.gate_outcome]

    return CanonicalAssessment(
        current_stage=stage,
        composite_score=composite,
        transition_target=transition.transition_target,
        recommended_next_stage=transition.recommended_next_stage,
        gate_outcome=transition.gate_outcome,
        lifecycle_state=lifecycle_state,
        composite_confidence=confidence,
        lowest_confidence_dimension=lowest_confidence_dimension,
        requires_human_review=transition.requires_human_review,
        response_depth=transition.response_depth,
        rating=_rating(composite),
        score_rationale=score_rationale,
        transition_rationale=transition.rationale,
        model_version=model_version or weight_set.model_version,
        weight_set_version=weight_set.version,
        transition_policy_version=transition.policy_version,
        dimensions=canonical_dimensions,
        criteria=transition.criteria,
    )


def assess_email(subject: str | None, content_html: str, stage: DIStage = DIStage.DI1) -> CanonicalAssessment:
    """Produce an assessment with the deterministic fallback rubric."""
    submission = email_to_submission(subject, content_html, stage)
    signals = _signals(submission.problem_statement)
    evaluators = {
        "ideaCompleteness": _completeness,
        "ideaQuality": _quality,
        "strategicValue": _value,
        "technicalFeasibility": _technical,
        "executionReadiness": _execution,
    }
    dimensions: list[DimensionScore] = []
    for dimension in DIMENSIONS:
        value, confidence, summary, evidence, gaps = evaluators[dimension](submission.problem_statement, signals)
        state = CriterionState.UNKNOWN if value < COMPLETENESS_FLOOR else CriterionState.SATISFIED
        label, agent = DIMENSION_METADATA[dimension]
        dimensions.append(
            DimensionScore(
                agent=agent,
                dimension=dimension,
                dimension_label=label,
                state=state,
                value=None if state == CriterionState.UNKNOWN else value,
                confidence=confidence,
                weight=0,
                summary=summary,
                evidence=evidence,
                gaps=gaps,
            )
        )
    return consolidate_dimensions(dimensions, stage)
