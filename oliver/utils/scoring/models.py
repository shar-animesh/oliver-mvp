"""Typed contracts for the canonical five-dimension scoring result."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from utils.stages import DIStage
from utils.transition_policy.models import CriterionState, EvaluatedCriterion, GateOutcome, ReportDepth


class LifecycleState(str, Enum):
    """Lifecycle state derived from the gate outcome."""

    ASSESSED = "Assessed"
    ACTIVE = "Active"
    STALLED = "Stalled"


class Submission(BaseModel):
    """Normalized evidence supplied to the deterministic rubric."""

    title: str = Field(min_length=3, max_length=200)
    problem_statement: str = Field(min_length=10)
    current_stage: DIStage = DIStage.DI1


class DimensionScore(BaseModel):
    """One evidence-backed canonical dimension result."""

    agent: str
    dimension: str
    dimension_label: str
    state: CriterionState
    value: Optional[int] = Field(default=None, ge=0, le=100)
    confidence: float = Field(ge=0.0, le=1.0)
    weight: int = Field(ge=0, le=100)
    summary: str
    evidence: list[str]
    gaps: list[str]
    scored_by: str = "rubric"


class CanonicalAssessment(BaseModel):
    """Portfolio score plus an independent transition-readiness evaluation."""

    current_stage: DIStage
    composite_score: Optional[int] = Field(default=None, ge=0, le=100)
    transition_target: Optional[DIStage] = None
    recommended_next_stage: Optional[DIStage] = None
    gate_outcome: GateOutcome
    lifecycle_state: LifecycleState
    composite_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    lowest_confidence_dimension: str
    requires_human_review: bool
    response_depth: ReportDepth
    rating: str
    score_rationale: str
    transition_rationale: str
    model_version: str
    weight_set_version: str
    transition_policy_version: str
    dimensions: list[DimensionScore] = Field(min_length=5, max_length=5)
    criteria: list[EvaluatedCriterion]
