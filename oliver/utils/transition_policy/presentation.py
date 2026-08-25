"""Participant-safe presentation of canonical transition evaluations."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .models import CriterionRole, CriterionState, GateOutcome

if TYPE_CHECKING:
    from utils.scoring.models import CanonicalAssessment

_INTERNAL_CRITERION_ID = re.compile(r"\bDI[1-5]_DI[1-5]_[A-Z0-9_]+\b")
_OUTCOME_LABELS = {
    GateOutcome.ADVANCE: "Advance",
    GateOutcome.CONDITIONAL_ADVANCE: "Conditional advance",
    GateOutcome.HOLD_FOR_EVIDENCE: "Hold for evidence",
    GateOutcome.DO_NOT_ADVANCE: "Do not advance",
    GateOutcome.CONTINUE_MONITORING: "Continue monitoring",
}


@dataclass(frozen=True)
class TransitionRecommendation:
    """Plain-language recommendation safe to display outside audit/admin views."""

    label: str
    detail: str
    basis: str


def _natural_list(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def participant_transition_recommendation(assessment: "CanonicalAssessment") -> TransitionRecommendation:
    """Translate policy state into participant language without exposing internal IDs."""
    target = assessment.transition_target
    target_label = target.value if target is not None else "the next stage"
    outcome = assessment.gate_outcome

    if outcome == GateOutcome.HOLD_FOR_EVIDENCE:
        relevant = [
            criterion
            for criterion in assessment.criteria
            if criterion.role == CriterionRole.ENTRY_CRITERION and criterion.state == CriterionState.UNKNOWN
        ]
        actions = _natural_list([criterion.user_action for criterion in relevant])
        detail = (
            f"Before moving to {target_label}, please {actions}." if actions else "More evidence is needed before a stage recommendation can be made."
        )
        basis = f"This recommendation is based on missing {assessment.current_stage.value} exit evidence."
    elif outcome == GateOutcome.CONDITIONAL_ADVANCE:
        relevant = [
            criterion
            for criterion in assessment.criteria
            if criterion.role == CriterionRole.NEXT_STAGE_EXPECTATION
            and criterion.conditional_if_unresolved
            and criterion.state in {CriterionState.UNKNOWN, CriterionState.CONCERN}
        ]
        actions = _natural_list([criterion.user_action for criterion in relevant])
        detail = (
            f"The evidence supports moving to {target_label}, provided you {actions}."
            if actions
            else f"The evidence supports moving to {target_label}, subject to the stated entry conditions."
        )
        basis = f"This recommendation is based on the {assessment.current_stage.value} exit evidence and open conditions."
    elif outcome == GateOutcome.DO_NOT_ADVANCE:
        relevant = [
            criterion
            for criterion in assessment.criteria
            if criterion.role in {CriterionRole.ENTRY_CRITERION, CriterionRole.BLOCKING_CONDITION} and criterion.state == CriterionState.CONCERN
        ]
        actions = _natural_list([criterion.user_action for criterion in relevant])
        detail = (
            f"The current evidence does not support moving to {target_label}. Please {actions} before reassessment."
            if actions
            else f"The current evidence does not support moving to {target_label}."
        )
        basis = f"This recommendation is based on blocking concerns in the {assessment.current_stage.value} exit evidence."
    elif outcome == GateOutcome.CONTINUE_MONITORING:
        concerns = [criterion for criterion in assessment.criteria if criterion.state == CriterionState.CONCERN]
        unknown = [criterion for criterion in assessment.criteria if criterion.state == CriterionState.UNKNOWN]
        if concerns:
            actions = _natural_list([criterion.user_action for criterion in concerns])
            detail = f"DI5 remains the current stage. Please {actions}; any retire or rollback decision requires human approval."
            basis = "This recommendation is based on current operational or value concerns."
        elif unknown:
            actions = _natural_list([criterion.user_action for criterion in unknown])
            detail = f"DI5 remains the current stage. Please {actions} to keep the operational record current."
            basis = "This recommendation is based on incomplete DI5 monitoring evidence."
        else:
            detail = "DI5 remains the current stage. Continue operational monitoring and measured-value tracking."
            basis = "This recommendation is based on current DI5 monitoring and value evidence."
    else:
        detail = f"The current evidence supports moving to {target_label}."
        basis = f"This recommendation is based on satisfied {assessment.current_stage.value} exit criteria."

    return TransitionRecommendation(
        label=_OUTCOME_LABELS[outcome],
        detail=detail,
        basis=basis,
    )


def remove_internal_criterion_ids(text: str) -> str:
    """Apply a final safety boundary to participant-facing rendered content."""
    return _INTERNAL_CRITERION_ID.sub("an internal policy criterion", text)
