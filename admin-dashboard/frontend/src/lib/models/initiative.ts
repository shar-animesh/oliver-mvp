// Path: src/lib/models/initiative.ts
// Description: Initiative lifecycle, portfolio intelligence, and Scout API contracts.

export interface InitiativeSummary {
    id: string;
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
}

export interface PortfolioPattern {
    title: string;
    finding: string;
    supporting_initiative_ids: string[];
    evidence_count: number;
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
