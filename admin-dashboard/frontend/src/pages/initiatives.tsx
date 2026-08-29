// Path: src/pages/initiatives.tsx
// Description: Canonical initiative portfolio and lifecycle overview.

import { useEffect, useMemo, useState } from "react";

import { api } from "../api";
import MetricCard from "../components/metric-card";
import { formatDate } from "../lib/format";
import type { InitiativeSummary, IntelligenceOverview } from "../lib/models";

interface InitiativesProps {
    onOpenInitiative: (initiativeId: string) => void;
}

export default function Initiatives({ onOpenInitiative }: InitiativesProps) {
    const [initiatives, setInitiatives] = useState<InitiativeSummary[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [intelligence, setIntelligence] = useState<IntelligenceOverview | null>(null);
    const [stageFilter, setStageFilter] = useState("ALL");

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

    const stageSummary = useMemo(
        () => ["DI1", "DI2", "DI3", "DI4", "DI5"].map((stage) => ({ stage, count: initiatives.filter((initiative) => initiative.current_stage === stage).length })),
        [initiatives],
    );
    const visibleInitiatives = stageFilter === "ALL" ? initiatives : initiatives.filter((initiative) => initiative.current_stage === stageFilter);

    return (
        <section id="portfolio">
            <div className="page-intro">
                <div>
                    <p className="eyebrow">Lifecycle portfolio</p>
                    <h2>Initiative portfolio</h2>
                    <p>Track every initiative from concept to scale, with evidence, scores, and review decisions in one place.</p>
                </div>
                <div className="refresh-note">
                    <span className={`status-dot${error ? " status-dot-error" : loading ? " status-dot-loading" : ""}`} />
                    {loading ? "Refreshing…" : error ? "Data connection needs attention" : "Connected to live data"}
                </div>
            </div>

            <div className="metric-grid" aria-label="Portfolio metrics">
                <MetricCard label="Initiatives" value={initiatives.length} note="Registered initiatives" loading={loading} tone="accent" />
                <MetricCard label="Active" value={metrics.active} note="Currently moving" loading={loading} tone="operational" />
                <MetricCard label="Awaiting review" value={metrics.review} note="Human authority required" loading={loading} />
                <MetricCard label="Average overall score" value={metrics.average ?? "—"} note={metrics.average === null ? "No complete scores" : "Across complete scores"} loading={loading} />
            </div>

            <section className="stage-overview" aria-label="Initiative stages">
                <div className="stage-overview-copy">
                    <p className="eyebrow">Pilot pipeline</p>
                    <h3>Initiative pipeline</h3>
                    <p>Select a stage to filter the portfolio.</p>
                </div>
                <div className="stage-steps">
                    {stageSummary.map(({ stage, count }) => (
                        <button type="button" className={`stage-step${stageFilter === stage ? " selected" : ""}`} key={stage} onClick={() => setStageFilter(stageFilter === stage ? "ALL" : stage)}>
                            <span>{stage}</span>
                            <strong>{count}</strong>
                            <small>{["Concept", "Pilot", "Test", "Implement", "Scale"][Number(stage.slice(-1)) - 1]}</small>
                        </button>
                    ))}
                </div>
            </section>

            <section className="panel initiative-panel portfolio-panel" aria-labelledby="portfolio-heading">
                <div className="panel-heading inbox-heading">
                    <div>
                        <p className="eyebrow">Initiative register</p>
                        <h3 id="portfolio-heading">DI1–DI5 lifecycle</h3>
                        <p>{stageFilter === "ALL" ? initiatives.length : visibleInitiatives.length} of {initiatives.length} total records</p>
                    </div>
                    <span className="refresh-note" title="Hold state is sourced from Oliver lifecycle authority. This dashboard does not change lifecycle records.">{metrics.held} on hold</span>
                </div>
                {error ? <p className="error-message">{error}</p> : null}
                {!loading && !error && initiatives.length === 0 ? (
                    <p className="empty-state">No initiatives are available yet.</p>
                ) : null}
                {visibleInitiatives.length ? (
                    <div className="portfolio-table">
                        <div className="portfolio-header" aria-hidden="true">
                            <span>Initiative</span>
                            <span>Stage</span>
                            <span>Score</span>
                            <span>Evidence</span>
                            <span>Review</span>
                            <span>Updated</span>
                        </div>
                        {visibleInitiatives.map((initiative) => (
                            <button
                                className="portfolio-row"
                                key={initiative.id}
                                type="button"
                                onClick={() => onOpenInitiative(initiative.id)}
                                title="Open pilot detail">
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
                                    <strong>{initiative.latest_score ?? (initiative.latest_assessment_at ? "Incomplete" : "Not assessed")}</strong>
                                    <small>{initiative.latest_rating || (initiative.latest_assessment_at ? "Evidence required" : "No assessment yet")}</small>
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
                            </button>
                        ))}
                    </div>
                ) : null}
            </section>

            <div className="intelligence-grid">
                <section className="panel intelligence-panel">
                    <div className="panel-heading">
                        <div>
                            <p className="eyebrow">Portfolio insights</p>
                            <h3>Patterns across initiatives</h3>
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
                        <p className="empty-state">No portfolio insights are available for the current data.</p>
                    )}
                </section>

                <section className="panel intelligence-panel">
                    <div className="panel-heading">
                        <div>
                            <p className="eyebrow">Scout</p>
                            <h3>Candidate queue</h3>
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
                        <p className="empty-state">No Scout candidates are waiting for review.</p>
                    )}
                </section>
            </div>
        </section>
    );
}
