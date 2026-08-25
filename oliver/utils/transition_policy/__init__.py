"""Versioned evidence-state policy for DI stage transitions."""

from .engine import evaluate_terminal_stage, evaluate_transition, unavailable_transition_evaluation
from .loader import active_transition_policy_set, policy_for_stage, terminal_policy_for_stage
from .models import (
    BlockingBehavior,
    CriterionFinding,
    CriterionRole,
    CriterionState,
    CriterionTiming,
    EvaluatedCriterion,
    GateOutcome,
    ReportDepth,
    StageTransitionPolicy,
    TerminalStagePolicy,
    TransitionCriterion,
    TransitionEvaluation,
    TransitionPolicySet,
)

__all__ = [
    "BlockingBehavior",
    "CriterionFinding",
    "CriterionRole",
    "CriterionState",
    "CriterionTiming",
    "EvaluatedCriterion",
    "GateOutcome",
    "ReportDepth",
    "StageTransitionPolicy",
    "TerminalStagePolicy",
    "TransitionCriterion",
    "TransitionEvaluation",
    "TransitionPolicySet",
    "active_transition_policy_set",
    "evaluate_transition",
    "evaluate_terminal_stage",
    "policy_for_stage",
    "terminal_policy_for_stage",
    "unavailable_transition_evaluation",
]
