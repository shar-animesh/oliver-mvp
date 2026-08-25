"""Deterministic gate semantics over approved criteria and evidence states."""

from utils.stages import DIStage

from .models import (
    BlockingBehavior,
    CriterionFinding,
    CriterionRole,
    CriterionState,
    EvaluatedCriterion,
    GateOutcome,
    ReportDepth,
    StageTransitionPolicy,
    TerminalStagePolicy,
    TransitionEvaluation,
)


def unavailable_transition_evaluation(stage: DIStage, policy_version: str) -> TransitionEvaluation:
    """Fail safely when no authorized criterion policy exists for a transition."""
    return TransitionEvaluation(
        current_stage=stage,
        transition_target=stage.next_stage,
        recommended_next_stage=None,
        gate_outcome=GateOutcome.HOLD_FOR_EVIDENCE,
        policy_version=policy_version,
        policy_available=False,
        criteria=[],
        rationale=f"No approved transition criteria are configured for {stage.value}; lifecycle movement is held.",
        requires_human_review=True,
        response_depth=ReportDepth.BRIEF,
    )


def evaluate_transition(
    policy: StageTransitionPolicy,
    findings: list[CriterionFinding],
    *,
    policy_version: str,
    confidence_floor: float,
) -> TransitionEvaluation:
    """Apply policy-owned timing and blocking semantics to evaluator findings."""
    findings_by_id = {finding.criterion_id: finding for finding in findings}
    expected_ids = {criterion.criterion_id for criterion in policy.criteria}
    if len(findings_by_id) != len(findings) or set(findings_by_id) != expected_ids:
        raise ValueError(f"Criterion findings must match approved policy IDs exactly: {sorted(expected_ids)}")

    evaluated = [
        EvaluatedCriterion(
            **findings_by_id[criterion.criterion_id].model_dump(),
            title=criterion.title,
            description=criterion.description,
            user_action=criterion.user_action,
            role=criterion.role,
            timing=criterion.timing,
            blocking_behavior=criterion.blocking_behavior,
            conditional_if_unresolved=criterion.conditional_if_unresolved,
            source=criterion.source,
        )
        for criterion in policy.criteria
    ]
    entry = [criterion for criterion in evaluated if criterion.role == CriterionRole.ENTRY_CRITERION]
    blockers = [criterion for criterion in evaluated if criterion.role == CriterionRole.BLOCKING_CONDITION]
    conditional_during = [
        criterion for criterion in evaluated if criterion.role == CriterionRole.NEXT_STAGE_EXPECTATION and criterion.conditional_if_unresolved
    ]
    blocking_concerns = [
        criterion
        for criterion in [*entry, *blockers]
        if criterion.state == CriterionState.CONCERN and criterion.blocking_behavior == BlockingBehavior.BLOCK_ON_CONCERN
    ]
    unknown_entry = [criterion for criterion in entry if criterion.state == CriterionState.UNKNOWN]
    unresolved_during = [criterion for criterion in conditional_during if criterion.state in {CriterionState.UNKNOWN, CriterionState.CONCERN}]

    if blocking_concerns:
        outcome = GateOutcome.DO_NOT_ADVANCE
        recommended_stage = None
        rationale = "Do not advance: actual evidence identifies a blocking entry concern in " + ", ".join(
            criterion.criterion_id for criterion in blocking_concerns
        )
        depth = ReportDepth.DETAILED
    elif unknown_entry:
        outcome = GateOutcome.HOLD_FOR_EVIDENCE
        recommended_stage = None
        rationale = "Hold for evidence: required entry criteria remain unknown: " + ", ".join(criterion.criterion_id for criterion in unknown_entry)
        depth = ReportDepth.BRIEF
    elif unresolved_during:
        outcome = GateOutcome.CONDITIONAL_ADVANCE
        recommended_stage = policy.target_stage
        rationale = "Conditional advance: entry criteria are satisfied; during-stage conditions remain open: " + ", ".join(
            criterion.criterion_id for criterion in unresolved_during
        )
        depth = ReportDepth.STANDARD
    else:
        outcome = GateOutcome.ADVANCE
        recommended_stage = policy.target_stage
        rationale = "Advance: all applicable required transition criteria are satisfied."
        depth = ReportDepth.DETAILED

    applicable_confidences = [
        criterion.confidence for criterion in evaluated if criterion.state in {CriterionState.SATISFIED, CriterionState.CONCERN}
    ]
    low_confidence = bool(applicable_confidences) and min(applicable_confidences) < confidence_floor
    requires_human_review = outcome == GateOutcome.DO_NOT_ADVANCE or policy.human_review_always or low_confidence
    if low_confidence:
        rationale += " Human review is required because at least one applicable criterion is below the confidence floor."

    return TransitionEvaluation(
        current_stage=policy.current_stage,
        transition_target=policy.target_stage,
        recommended_next_stage=recommended_stage,
        gate_outcome=outcome,
        policy_version=policy_version,
        policy_available=True,
        criteria=evaluated,
        rationale=rationale,
        requires_human_review=requires_human_review,
        response_depth=depth,
    )


def evaluate_terminal_stage(
    policy: TerminalStagePolicy,
    findings: list[CriterionFinding],
    *,
    policy_version: str,
    confidence_floor: float,
) -> TransitionEvaluation:
    """Evaluate DI5 health without inventing a forward transition or automatic retirement."""
    findings_by_id = {finding.criterion_id: finding for finding in findings}
    expected_ids = {criterion.criterion_id for criterion in policy.criteria}
    if len(findings_by_id) != len(findings) or set(findings_by_id) != expected_ids:
        raise ValueError(f"Criterion findings must match approved policy IDs exactly: {sorted(expected_ids)}")

    evaluated = [
        EvaluatedCriterion(
            **findings_by_id[criterion.criterion_id].model_dump(),
            title=criterion.title,
            description=criterion.description,
            user_action=criterion.user_action,
            role=criterion.role,
            timing=criterion.timing,
            blocking_behavior=criterion.blocking_behavior,
            conditional_if_unresolved=criterion.conditional_if_unresolved,
            source=criterion.source,
        )
        for criterion in policy.criteria
    ]
    concerns = [criterion for criterion in evaluated if criterion.state == CriterionState.CONCERN]
    unknown = [criterion for criterion in evaluated if criterion.state == CriterionState.UNKNOWN]
    known_confidences = [criterion.confidence for criterion in evaluated if criterion.state in {CriterionState.SATISFIED, CriterionState.CONCERN}]
    low_confidence = bool(known_confidences) and min(known_confidences) < confidence_floor

    if concerns:
        rationale = "Continue monitoring: operational concerns require human review: " + ", ".join(criterion.criterion_id for criterion in concerns)
        depth = ReportDepth.DETAILED
    elif unknown:
        rationale = "Continue monitoring: current evidence is unavailable for: " + ", ".join(criterion.criterion_id for criterion in unknown)
        depth = ReportDepth.STANDARD
    else:
        rationale = "Continue monitoring: all configured DI5 operational and value evidence is currently satisfied."
        depth = ReportDepth.STANDARD
    if low_confidence:
        rationale += " Human review is required because at least one applicable criterion is below the confidence floor."

    return TransitionEvaluation(
        current_stage=policy.current_stage,
        transition_target=None,
        recommended_next_stage=None,
        gate_outcome=GateOutcome.CONTINUE_MONITORING,
        policy_version=policy_version,
        policy_available=True,
        criteria=evaluated,
        rationale=rationale,
        requires_human_review=bool(concerns) or low_confidence,
        response_depth=depth,
    )
