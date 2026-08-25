// Path: src/pages/initiatives.tsx
// Description: Canonical initiative portfolio and lifecycle overview.

import { useEffect, useMemo, useState } from "react";

import { api } from "../api";
import { formatDate } from "../lib/format";
import type { InitiativeSummary, IntelligenceOverview } from "../lib/models";

function Metric({ label, value, note }: { label: string; value: string; note: string }) {
    return (
        <article className="metric-card">
            <span>{label}</span>
            <strong>{value}</strong>
            <small>{note}</small>
        </article>
    );
}

export default function Initiatives() {
    const [initiatives, setInitiatives] = useState<InitiativeSummary[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [intelligence, setIntelligence] = useState<IntelligenceOverview | null>(null);

    useEffect(() => {
        let active = true;
        void Promise.allSettled([api.listInitiatives(), api.getIntelligence()]).then(([initiativeResult, intelligenceResult]) => {
            if (!active) return;
            if (initiativeResult.status === "fulfilled") setInitiatives(initiativeResult.value);
            if (intelligenceResult.status === "fulfilled") setIntelligence(intelligenceResult.value);

            if (initiativeResult.status === "rejected") {
                const reason: unknown = initiativeResult.reason;
                setError(reason instanceof Error ? reason.message : "Unable to load initiatives");
            } else if (intelligenceResult.status === "rejected") {
                setError("Portfolio intelligence is temporarily unavailable; the initiative register remains available.");
            }
            setLoading(false);
        });
        return () => {
            active = false;
        };
    }, []);

    const metrics = useMemo(() => {
        const scored = initiatives.filter((initiative) => initiative.latest_score !== null);
        const average = scored.length
            ? Math.round(scored.reduce((total, initiative) => total + (initiative.latest_score ?? 0), 0) / scored.length)
            : null;
        return {
            active: initiatives.filter((initiative) => initiative.lifecycle_state === "Active").length,
            review: initiatives.reduce((total, initiative) => total + initiative.pending_review_count, 0),
            held: initiatives.filter((initiative) => initiative.is_on_hold).length,
            average,
        };
    }, [initiatives]);

    return (
        <section id="portfolio">
            <div className="page-intro">
                <div>
                    <p className="eyebrow">Lifecycle portfolio</p>
                    <h2>Authoritative initiatives</h2>
                    <p>Current DI state, evidence maturity and governed decisions from Oliver's system of record.</p>
                </div>
                <div className="refresh-note">
                    <span className="status-dot" />
                    {loading ? "Refreshing..." : "Live data from PostgreSQL"}
                </div>
            </div>

            <div className="metric-grid" aria-label="Portfolio metrics">
                <Metric label="Initiatives" value={`${initiatives.length}`} note="Canonical records" />
                <Metric label="Active" value={`${metrics.active}`} note="Progressing through DI" />
                <Metric label="Awaiting review" value={`${metrics.review}`} note="Human authority required" />
                <Metric label="Average score" value={metrics.average === null ? "-" : `${metrics.average}`} note="Latest assessments" />
            </div>

            <section className="panel initiative-panel portfolio-panel" aria-labelledby="portfolio-heading">
                <div className="panel-heading inbox-heading">
                    <div>
                        <p className="eyebrow">Initiative register</p>
                        <h3 id="portfolio-heading">DI1-DI5 lifecycle</h3>
                        <p>{initiatives.length} total records</p>
                    </div>
                    <span className="refresh-note">{metrics.held} on hold</span>
                </div>
                {error ? <p className="error-message">{error}</p> : null}
                {!loading && !error && initiatives.length === 0 ? (
                    <p className="empty-state">No assessed initiatives have been registered yet.</p>
                ) : null}
                {initiatives.length ? (
                    <div className="portfolio-table">
                        <div className="portfolio-header" aria-hidden="true">
                            <span>Initiative</span>
                            <span>Stage</span>
                            <span>Score</span>
                            <span>Evidence</span>
                            <span>Review</span>
                            <span>Updated</span>
                        </div>
                        {initiatives.map((initiative) => (
                            <article className="portfolio-row" key={initiative.id}>
                                <div className="initiative-cell">
                                    <span className="initiative-mark" />
                                    <span>
                                        <strong>{initiative.title}</strong>
                                        <small>{initiative.owner_email || "Owner not recorded"}</small>
                                    </span>
                                </div>
                                <div>
                                    <span className={`stage-badge stage-${initiative.current_stage.toLowerCase()}`}>{initiative.current_stage}</span>
                                    <small>{initiative.stage_name}</small>
                                </div>
                                <div className="portfolio-score">
                                    <strong>{initiative.latest_score ?? "-"}</strong>
                                    <small>{initiative.latest_rating || "Not scored"}</small>
                                </div>
                                <div>
                                    <strong>{initiative.evidence_version_count}</strong>
                                    <small>{initiative.days_in_stage} days in stage</small>
                                </div>
                                <div>
                                    <strong>{initiative.pending_review_count ?? "-"}</strong>
                                    <small>{initiative.is_on_hold ? "On hold" : initiative.lifecycle_state}</small>
                                </div>
                                <time dateTime={initiative.updated_at}>{formatDate(initiative.updated_at)}</time>
                            </article>
                        ))}
                    </div>
                ) : null}
            </section>

            <div className="intelligence-grid">
                <section className="panel intelligence-panel">
                    <div className="panel-heading">
                        <div>
                            <p className="eyebrow">Portfolio intelligence</p>
                            <h3>Verified cross-initiative patterns</h3>
                        </div>
                    </div>
                    {intelligence?.latest_portfolio_insight ? (
                        <div className="intelligence-body">
                            <p>{intelligence.latest_portfolio_insight.report.executive_summary}</p>
                            <ul>
                                {intelligence.latest_portfolio_insight.report.patterns.map((pattern) => (
                                    <li key={pattern.title}>
                                        <strong>{pattern.title}</strong>
                                        <span>{pattern.finding}</span>
                                        <small>{pattern.evidence_count} cited initiatives</small>
                                    </li>
                                ))}
                            </ul>
                            <small>Generated {formatDate(intelligence.latest_portfolio_insight.created_at)}</small>
                        </div>
                    ) : (
                        <p className="empty-state">No portfolio insight has been generated for the current data.</p>
                    )}
                </section>

                <section className="panel intelligence-panel">
                    <div className="panel-heading">
                        <div>
                            <p className="eyebrow">Scout</p>
                            <h3>Governed candidate queue</h3>
                        </div>
                        <span className="refresh-note">{intelligence?.scout_candidates.length ?? 0} open</span>
                    </div>
                    {intelligence?.scout_candidates.length ? (
                        <div className="scout-list">
                            {intelligence.scout_candidates.map((candidate) => (
                                <article key={candidate.id}>
                                    <span>{candidate.source_system}</span>
                                    <strong>{candidate.title}</strong>
                                    <p>{candidate.summary}</p>
                                    <small>{Math.round(candidate.confidence * 100)}% classification confidence</small>
                                </article>
                            ))}
                        </div>
                    ) : (
                        <p className="empty-state">No Scout candidates are awaiting review.</p>
                    )}
                </section>
            </div>
        </section>
    );
}
