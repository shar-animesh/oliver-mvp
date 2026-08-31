// Path: src/lib/models/initiative.ts
// Description: Initiative lifecycle, portfolio intelligence, and Scout API contracts.

export interface InitiativeSummary {
    id: string;
    primary_thread_id: string | null;
    title: string;
    owner_email: string | null;
    current_stage: string;
    stage_name: string;
    lifecycle_state: string;
    is_on_hold: boolean;
    hold_reason: string | null;
    version: number;
    days_in_stage: number;
    evidence_version_count: number;
    pending_review_count: number;
    latest_score: number | null;
    latest_gate_outcome: string | null;
    latest_rating: string | null;
    latest_assessment_at: string | null;
    stage_entered_at: string;
    updated_at: string;
    latest_activity_type: string;
}

export interface InitiativeThread {
    id: string;
    subject: string | null;
    participant_email: string | null;
    updated_at: string;
}

export interface InitiativeAssessmentSummary {
    run_id: string;
    thread_id: string | null;
    evidence_version_id: string | null;
    current_stage: string;
    composite_score: number | null;
    transition_target: string | null;
    recommended_next_stage: string | null;
    gate_outcome: string;
    rating: string;
    requires_human_review: boolean;
    transition_policy_version: string;
    created_at: string;
}

export interface LifecycleTransition {
    id: string;
    assessment_run_id: string | null;
    transition_type: string;
    from_stage: string;
    to_stage: string | null;
    status: string;
    requires_human_review: boolean;
    expected_initiative_version: number;
    policy_version: string;
    reason: string;
    proposed_by: string;
    decided_by: string | null;
    created_at: string;
    decided_at: string | null;
}

export interface EvidenceVersion {
    id: string;
    version: number;
    source_fingerprint: string;
    trigger_message_id: string | null;
    created_at: string;
}

export interface AuditEvent {
    id: string;
    event_type: string;
    actor_type: string;
    actor_id: string;
    subject_type: string;
    subject_id: string;
    correlation_id: string | null;
    payload: Record<string, unknown>;
    occurred_at: string;
}

export interface InitiativeDetail extends InitiativeSummary {
    created_at: string;
    threads: InitiativeThread[];
    assessments: InitiativeAssessmentSummary[];
    evidence_versions: EvidenceVersion[];
    transitions: LifecycleTransition[];
    audit_events: AuditEvent[];
}

export interface PortfolioPattern {
    title: string;
    finding: string;
    supporting_initiative_ids: string[];
    evidence_count: number;
    category?: "EVIDENCE" | "EXECUTION" | "TECHNICAL" | "GOVERNANCE" | "SAFETY" | "DUPLICATE" | "PORTFOLIO";
    priority?: "HIGH" | "MEDIUM" | "LOW";
    why_it_matters?: string;
    recommended_action?: string;
}

export interface PortfolioInsightReport {
    executive_summary: string;
    patterns: PortfolioPattern[];
    recurring_blockers: PortfolioPattern[];
    possible_duplicates: PortfolioPattern[];
    recommendations: string[];
}

export interface PortfolioInsightAdmin {
    id: string;
    input_fingerprint: string;
    report: PortfolioInsightReport;
    model_name: string;
    generated_by: string;
    created_at: string;
}

export interface ScoutCandidate {
    id: string;
    source_system: string;
    source_reference: string;
    title: string;
    summary: string;
    proposed_owner: string | null;
    confidence: number;
    rationale: string;
    status: string;
    promoted_initiative_id: string | null;
    discovered_at: string;
}

export interface IntelligenceOverview {
    latest_portfolio_insight: PortfolioInsightAdmin | null;
    scout_candidates: ScoutCandidate[];
}
