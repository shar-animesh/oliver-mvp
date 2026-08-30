// Path: src/pages/initiative-detail.tsx
// Description: Decision-focused detail view for one authoritative initiative.

import { useEffect, useState } from "react";

import { api } from "../api";
import MetricCard from "../components/metric-card";
import { formatDate, formatGate } from "../lib/format";
import type { InitiativeDetail as InitiativeDetailModel } from "../lib/models";

interface InitiativeDetailProps {
    initiativeId: string;
    onBack: () => void;
    onOpenThread: (threadId: string) => void;
}

function scoreLabel(initiative: InitiativeDetailModel): string {
    if (initiative.latest_score !== null) return `${initiative.latest_score}/100`;
    if (initiative.latest_assessment_at) return "Incomplete";
    return "Not assessed";
}

export default function InitiativeDetail({ initiativeId, onBack, onOpenThread }: InitiativeDetailProps) {
    const [initiative, setInitiative] = useState<InitiativeDetailModel | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let active = true;
        void api
            .getInitiative(initiativeId)
            .then((value) => {
                if (active) setInitiative(value);
            })
            .catch((reason: unknown) => {
                if (active) setError(reason instanceof Error ? reason.message : "Could not load this pilot");
            })
            .finally(() => {
                if (active) setLoading(false);
            });
        return () => {
            active = false;
        };
    }, [initiativeId]);

    if (loading) {
        return <p className="empty-state">Loading pilot details…</p>;
    }
    if (error || !initiative) {
        return (
            <section className="detail-view">
                <button className="back-link" type="button" onClick={onBack}>
                    <span aria-hidden="true">←</span> Portfolio
                </button>
                <p className="error-message">{error || "Pilot not found"}</p>
            </section>
        );
    }

    const latestAssessment = initiative.assessments[0];
    const pendingTransitions = initiative.transitions.filter((transition) => transition.status === "PENDING");

    return (
        <section className="detail-view" aria-labelledby="pilot-title">
            <button className="back-link" type="button" onClick={onBack}>
                <span aria-hidden="true">←</span> Portfolio
            </button>

            <div className="detail-heading">
                <div>
                    <p className="eyebrow">Pilot detail</p>
                    <h2 id="pilot-title">{initiative.title}</h2>
                    <p>{initiative.owner_email || "Owner not recorded"}</p>
                </div>
                <div className="detail-heading-actions">
                    <span className={`stage-badge stage-${initiative.current_stage.toLowerCase()}`}>{initiative.current_stage}</span>
                    <span className="detail-date">Updated {formatDate(initiative.updated_at)}</span>
                </div>
            </div>

            <div className="metric-grid" aria-label="Pilot summary">
                <MetricCard label="Current stage" value={initiative.current_stage} note={initiative.stage_name} tone="accent" />
                <MetricCard label="Overall score" value={scoreLabel(initiative)} note={initiative.latest_rating || "Needs evidence"} tone="operational" />
                <MetricCard label="Evidence versions" value={initiative.evidence_version_count} note={`${initiative.days_in_stage} days in stage`} />
                <MetricCard
                    label="Lifecycle state"
                    value={initiative.is_on_hold ? "On hold" : initiative.lifecycle_state}
                    note={pendingTransitions.length ? `${pendingTransitions.length} decision${pendingTransitions.length === 1 ? "" : "s"} pending` : "No pending decisions"}
                />
            </div>

            <div className="detail-grid initiative-detail-grid">
                <div className="detail-main">
                    <section className="panel">
                        <div className="panel-heading">
                            <div>
                                <p className="eyebrow">Decision readout</p>
                                <h3>What happens next</h3>
                            </div>
                            <span className={`status-badge ${initiative.is_on_hold ? "status-pending" : "status-complete"}`}>
                                <span /> {initiative.is_on_hold ? "On hold" : formatGate(initiative.latest_gate_outcome)}
                            </span>
                        </div>
                        <div className="assessment-readout">
                            <span className="readout-label">Current position</span>
                            <p>
                                {initiative.latest_gate_outcome
                                    ? `The latest assessment returned ${formatGate(initiative.latest_gate_outcome)} at ${latestAssessment?.current_stage || initiative.current_stage}.`
                                    : "This pilot has not received an assessment yet."}
                            </p>
                        </div>
                        {initiative.hold_reason ? <p className="assessment-copy">Hold reason: {initiative.hold_reason}</p> : null}
                        {pendingTransitions.length ? (
                            <div className="timeline-list">
                                {pendingTransitions.map((transition) => (
                                    <article className="timeline-item" key={transition.id}>
                                        <strong>{transition.transition_type.replaceAll("_", " ")}</strong>
                                        <span>{transition.from_stage}{transition.to_stage ? ` → ${transition.to_stage}` : ""} · Awaiting human decision</span>
                                        <p>{transition.reason}</p>
                                    </article>
                                ))}
                            </div>
                        ) : null}
                    </section>

                    <section className="panel">
                        <div className="panel-heading">
                            <div>
                                <p className="eyebrow">Evidence and assessments</p>
                                <h3>Assessment history</h3>
                            </div>
                            <span className="refresh-note">{initiative.assessments.length} assessment{initiative.assessments.length === 1 ? "" : "s"}</span>
                        </div>
                        {initiative.assessments.length ? (
                            <div className="timeline-list">
                                {initiative.assessments.map((assessment) => (
                                    <article className="timeline-item" key={assessment.run_id}>
                                        <strong>{assessment.composite_score === null ? "Incomplete score" : `${assessment.composite_score}/100`}</strong>
                                        <span>{assessment.current_stage} · {formatGate(assessment.gate_outcome)} · {formatDate(assessment.created_at)}</span>
                                        <p>{assessment.requires_human_review ? "Human review is required for this assessment." : "No human decision is pending for this assessment."}</p>
                                        {assessment.thread_id ? (
                                            <button className="inline-link" type="button" onClick={() => onOpenThread(assessment.thread_id as string)}>
                                                View assessment details -&gt;
                                            </button>
                                        ) : null}
                                    </article>
                                ))}
                            </div>
                        ) : (
                            <p className="empty-state">No assessments recorded yet.</p>
                        )}
                    </section>

                    <section className="panel">
                        <div className="panel-heading">
                            <div>
                                <p className="eyebrow">Communication history</p>
                                <h3>Conversations for this pilot</h3>
                            </div>
                            <span className="refresh-note">{initiative.threads.length} conversation{initiative.threads.length === 1 ? "" : "s"}</span>
                        </div>
                        {initiative.threads.length ? (
                            <div className="linked-list">
                                {initiative.threads.map((thread) => (
                                    <button className="linked-row" type="button" key={thread.id} onClick={() => onOpenThread(thread.id)}>
                                        <span>
                                            <strong>{thread.subject || "Untitled conversation"}</strong>
                                            <small>{thread.participant_email || "Unknown participant"} · Updated {formatDate(thread.updated_at)}</small>
                                        </span>
                                        <span aria-hidden="true">→</span>
                                    </button>
                                ))}
                            </div>
                        ) : (
                            <p className="empty-state">No conversations are linked to this pilot.</p>
                        )}
                    </section>
                </div>

                <aside className="detail-rail">
                    <section className="panel">
                        <p className="eyebrow">Lifecycle timeline</p>
                        <div className="timeline-list">
                            {initiative.transitions.length ? (
                                initiative.transitions.map((transition) => (
                                    <article className="timeline-item" key={transition.id}>
                                        <strong>{transition.transition_type.replaceAll("_", " ")}</strong>
                                        <span>{transition.from_stage}{transition.to_stage ? ` → ${transition.to_stage}` : ""} · {transition.status}</span>
                                        <small>{formatDate(transition.created_at)}</small>
                                    </article>
                                ))
                            ) : (
                                <p className="empty-state">No lifecycle transitions recorded.</p>
                            )}
                        </div>
                    </section>

                    <section className="panel">
                        <p className="eyebrow">Audit trail</p>
                        <div className="timeline-list">
                            {initiative.audit_events.slice(0, 12).map((event) => (
                                <article className="timeline-item" key={event.id}>
                                    <strong>{event.event_type.replaceAll("_", " ")}</strong>
                                    <span>{event.actor_id}</span>
                                    <small>{formatDate(event.occurred_at)}</small>
                                </article>
                            ))}
                            {!initiative.audit_events.length ? <p className="empty-state">No audit events recorded.</p> : null}
                        </div>
                    </section>
                </aside>
            </div>
        </section>
    );
}
