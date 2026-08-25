"""Typed contracts for evidence-state transition policy and its result."""

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from utils.evidence_contracts import FINDING_ITEMS_MAX, FINDING_SUMMARY_MAX_CHARS, FindingStatement
from utils.stages import DIStage


class CriterionState(str, Enum):
    """What the supplied evidence says about one approved criterion."""

    SATISFIED = "SATISFIED"
    CONCERN = "CONCERN"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CriterionTiming(str, Enum):
    """When a criterion matters relative to the proposed target stage."""

    REQUIRED_BEFORE_ENTRY = "REQUIRED_BEFORE_ENTRY"
    REQUIRED_DURING_STAGE = "REQUIRED_DURING_STAGE"
    ADVISORY = "ADVISORY"


class BlockingBehavior(str, Enum):
    """Whether actual negative evidence can block the transition."""

    BLOCK_ON_CONCERN = "BLOCK_ON_CONCERN"
    NON_BLOCKING = "NON_BLOCKING"


class CriterionRole(str, Enum):
    """Functional role a criterion plays in the transition decision."""

    ENTRY_CRITERION = "ENTRY_CRITERION"
    NEXT_STAGE_EXPECTATION = "NEXT_STAGE_EXPECTATION"
    BLOCKING_CONDITION = "BLOCKING_CONDITION"
    TERMINAL_MONITORING = "TERMINAL_MONITORING"


class GateOutcome(str, Enum):
    """Authoritative transition recommendation produced by policy code."""

    ADVANCE = "ADVANCE"
    CONDITIONAL_ADVANCE = "CONDITIONAL_ADVANCE"
    HOLD_FOR_EVIDENCE = "HOLD_FOR_EVIDENCE"
    DO_NOT_ADVANCE = "DO_NOT_ADVANCE"
    CONTINUE_MONITORING = "CONTINUE_MONITORING"


class ReportDepth(str, Enum):
    """Deterministic communication depth supplied to the Coach."""

    BRIEF = "BRIEF"
    STANDARD = "STANDARD"
    DETAILED = "DETAILED"


class TransitionCriterion(BaseModel):
    """One approved policy criterion; the model cannot alter these fields."""

    criterion_id: str = Field(pattern=r"^DI[1-5]_DI[1-5]_[A-Z0-9_]+$")
    title: str = Field(min_length=3)
    description: str = Field(min_length=10)
    user_action: str = Field(
        min_length=5,
        description="Plain-language action used in participant communications; never an internal policy identifier.",
    )
    role: CriterionRole
    timing: CriterionTiming
    blocking_behavior: BlockingBehavior
    conditional_if_unresolved: bool = False
    source: str = Field(min_length=5)


class StageTransitionPolicy(BaseModel):
    """Versioned criteria for one forward DI transition."""

    current_stage: DIStage
    target_stage: DIStage
    current_stage_objective: str = Field(min_length=20)
    next_stage_objective: str = Field(min_length=20)
    human_review_always: bool = False
    criteria: list[TransitionCriterion] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_forward_transition(self) -> "StageTransitionPolicy":
        if self.current_stage.next_stage != self.target_stage:
            raise ValueError("A transition policy must target the immediately following DI stage")
        criterion_ids = [criterion.criterion_id for criterion in self.criteria]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("Transition criterion IDs must be unique")
        if not any(criterion.role == CriterionRole.ENTRY_CRITERION for criterion in self.criteria):
            raise ValueError("A transition policy must define at least one entry criterion")
        for criterion in self.criteria:
            if criterion.role == CriterionRole.TERMINAL_MONITORING:
                raise ValueError(f"{criterion.criterion_id} cannot be used in a forward transition policy")
            if criterion.role in {CriterionRole.ENTRY_CRITERION, CriterionRole.BLOCKING_CONDITION}:
                if criterion.timing != CriterionTiming.REQUIRED_BEFORE_ENTRY:
                    raise ValueError(f"{criterion.criterion_id} must be required before entry")
                if criterion.blocking_behavior != BlockingBehavior.BLOCK_ON_CONCERN:
                    raise ValueError(f"{criterion.criterion_id} must block on actual concern")
            if criterion.role == CriterionRole.NEXT_STAGE_EXPECTATION:
                if criterion.timing != CriterionTiming.REQUIRED_DURING_STAGE:
                    raise ValueError(f"{criterion.criterion_id} must be evaluated during the next stage")
                if criterion.blocking_behavior != BlockingBehavior.NON_BLOCKING:
                    raise ValueError(f"{criterion.criterion_id} cannot block entry")
            if criterion.conditional_if_unresolved and criterion.role != CriterionRole.NEXT_STAGE_EXPECTATION:
                raise ValueError("Only a next-stage expectation can become an entry condition")
        return self


class TerminalStagePolicy(BaseModel):
    """Approved monitoring policy for a lifecycle stage with no forward transition."""

    current_stage: DIStage
    stage_objective: str = Field(min_length=20)
    criteria: list[TransitionCriterion] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_terminal_stage(self) -> "TerminalStagePolicy":
        if self.current_stage.next_stage is not None:
            raise ValueError("A terminal policy can only be configured for a terminal DI stage")
        criterion_ids = [criterion.criterion_id for criterion in self.criteria]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("Terminal monitoring criterion IDs must be unique")
        for criterion in self.criteria:
            if criterion.role != CriterionRole.TERMINAL_MONITORING:
                raise ValueError(f"{criterion.criterion_id} must be a terminal monitoring criterion")
            if criterion.timing != CriterionTiming.REQUIRED_DURING_STAGE:
                raise ValueError(f"{criterion.criterion_id} must be evaluated during the terminal stage")
            if criterion.blocking_behavior != BlockingBehavior.NON_BLOCKING:
                raise ValueError(f"{criterion.criterion_id} cannot cause automatic terminal-state mutation")
            if criterion.conditional_if_unresolved:
                raise ValueError(f"{criterion.criterion_id} cannot be an entry condition")
        return self


class TransitionPolicySet(BaseModel):
    """One immutable policy-data version containing approved transitions."""

    version: str = Field(min_length=5)
    extends: str | None = None
    transitions: dict[str, StageTransitionPolicy] = Field(default_factory=dict)
    terminal_stages: dict[str, TerminalStagePolicy] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_transition_keys(self) -> "TransitionPolicySet":
        for stage, transition in self.transitions.items():
            if stage != transition.current_stage.value:
                raise ValueError(f"Transition key {stage} does not match {transition.current_stage.value}")
        for stage, policy in self.terminal_stages.items():
            if stage != policy.current_stage.value:
                raise ValueError(f"Terminal policy key {stage} does not match {policy.current_stage.value}")
        return self


class CriterionFinding(BaseModel):
    """Evidence interpretation returned by an evaluator for one approved criterion."""

    criterion_id: str
    state: CriterionState
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=10, max_length=FINDING_SUMMARY_MAX_CHARS)
    evidence: list[FindingStatement] = Field(default_factory=list, max_length=FINDING_ITEMS_MAX)
    gaps: list[FindingStatement] = Field(default_factory=list, max_length=FINDING_ITEMS_MAX)


class EvaluatedCriterion(CriterionFinding):
    """Criterion finding enriched only from authenticated policy data."""

    title: str
    description: str
    user_action: str
    role: CriterionRole
    timing: CriterionTiming
    blocking_behavior: BlockingBehavior
    conditional_if_unresolved: bool
    source: str


class TransitionEvaluation(BaseModel):
    """Complete deterministic transition recommendation supplied to StageMaster."""

    current_stage: DIStage
    transition_target: DIStage | None
    recommended_next_stage: DIStage | None
    gate_outcome: GateOutcome
    policy_version: str
    policy_available: bool
    criteria: list[EvaluatedCriterion]
    rationale: str
    requires_human_review: bool
    response_depth: ReportDepth
