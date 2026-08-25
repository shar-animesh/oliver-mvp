// Path: src/lib/models/assessment.ts
// Description: Assessment-lab and transition-policy API contracts.

export type DIStage = "DI1" | "DI2" | "DI3" | "DI4" | "DI5";

export interface AssessmentTestInput {
    subject: string;
    evidence: string;
    current_stage: DIStage;
}

export interface AssessmentDimension {
    agent: string;
    dimension: string;
    dimension_label: string;
    state: "SATISFIED" | "CONCERN" | "UNKNOWN" | "NOT_APPLICABLE";
    value: number | null;
    confidence: number;
    weight: number;
    summary: string;
    evidence: string[];
    gaps: string[];
    scored_by: string;
}

export interface AssessmentTestResult {
    current_stage: DIStage;
    composite_score: number | null;
    transition_target: DIStage | null;
    recommended_next_stage: DIStage | null;
    gate_outcome: "ADVANCE" | "CONDITIONAL_ADVANCE" | "HOLD_FOR_EVIDENCE" | "DO_NOT_ADVANCE" | "CONTINUE_MONITORING";
    lifecycle_state: string;
    composite_confidence: number | null;
    lowest_confidence_dimension: string;
    requires_human_review: boolean;
    response_depth: "BRIEF" | "STANDARD" | "DETAILED";
    rating: string;
    score_rationale: string;
    transition_rationale: string;
    model_version: string;
    weight_set_version: string;
    transition_policy_version: string;
    dimensions: AssessmentDimension[];
    criteria: TransitionCriterion[];
    response_action: "SEND_EMAIL" | "NO_REPLY";
    response_kind: "assessment" | "message" | null;
    email_subject: string | null;
    email_html: string | null;
}

export interface TransitionCriterion {
    criterion_id: string;
    title: string;
    description: string;
    role: "ENTRY_CRITERION" | "NEXT_STAGE_EXPECTATION" | "BLOCKING_CONDITION";
    state: "SATISFIED" | "CONCERN" | "UNKNOWN" | "NOT_APPLICABLE";
    timing: "REQUIRED_BEFORE_ENTRY" | "REQUIRED_DURING_STAGE" | "ADVISORY";
    conditional_if_unresolved: boolean;
    confidence: number;
    summary: string;
    evidence: string[];
    gaps: string[];
}
