// Path: src/lib/models/email-thread.ts
// Description: TypeScript contracts for Oliver email communication history.

export interface EmailThreadSummary {
    id: string;
    initiative_id: string | null;
    initiative_title: string | null;
    conversation_id: string;
    subject: string | null;
    participant_email: string | null;
    message_count: number;
    run_count: number;
    assessment_count: number;
    canonical_score: number | null;
    di_stage: string | null;
    assessment_stage: string | null;
    initiative_current_stage: string | null;
    initiative_lifecycle_state: string | null;
    gate_outcome: string | null;
    rating: string | null;
    last_activity_at: string;
}

export interface EmailMessage {
    id: string;
    direction: "INBOUND" | "OUTBOUND";
    sender_email: string | null;
    recipient_emails: string | null;
    subject: string | null;
    content_html: string | null;
    received_at: string;
    message_kind: "NEW" | "REPLY" | "FORWARDED" | "OLIVER_RESPONSE";
}

export interface OliverRun {
    id: string;
    action: "SEND_EMAIL" | "NO_REPLY";
    model_name: string;
    subject: string | null;
    delivery_status: string | null;
    delivery_attempt_count: number;
    delivery_last_error: string | null;
    delivered_at: string | null;
    assessment: CanonicalAssessment | null;
    related_ideas: RelatedIdea[];
    prompt_tokens: number | null;
    completion_tokens: number | null;
    created_at: string;
}

export interface DimensionScore {
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

export interface CanonicalAssessment {
    current_stage: string;
    composite_score: number | null;
    transition_target: string | null;
    recommended_next_stage: string | null;
    gate_outcome: string;
    lifecycle_state: string;
    composite_confidence: number | null;
    lowest_confidence_dimension: string;
    requires_human_review: boolean;
    response_depth: string;
    rating: string;
    score_rationale: string;
    transition_rationale: string;
    model_version: string;
    weight_set_version: string;
    transition_policy_version: string;
    dimensions: DimensionScore[];
    criteria: Array<Record<string, unknown>>;
    created_at: string;
}

export interface RelatedIdea {
    thread_id: string;
    subject: string | null;
    participant_email: string | null;
    rank: number;
    cosine_distance: number;
}

export interface EmailThreadDetail {
    id: string;
    initiative_id: string | null;
    initiative_title: string | null;
    initiative_current_stage: string | null;
    initiative_lifecycle_state: string | null;
    conversation_id: string;
    subject: string | null;
    participant_email: string | null;
    embedding_model: string | null;
    embedding_dimensions: number | null;
    embedded_at: string | null;
    created_at: string;
    updated_at: string;
    messages: EmailMessage[];
    runs: OliverRun[];
}
