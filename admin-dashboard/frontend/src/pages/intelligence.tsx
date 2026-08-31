// Path: src/pages/intelligence.tsx
// Description: Dedicated portfolio intelligence and Scout review surfaces.

import { useEffect, useState } from "react";

import { api } from "../api";
import { formatDate } from "../lib/format";
import type { InitiativeSummary, IntelligenceOverview, PortfolioPattern } from "../lib/models";

type IntelligenceMode = "patterns" | "scout";

interface IntelligenceProps {
    mode: IntelligenceMode;
    onOpenInitiative?: (id: string) => void;
}

function reportPatterns(overview: IntelligenceOverview): PortfolioPattern[] {
    const report = overview.latest_portfolio_insight?.report;
    return report ? [...report.patterns, ...report.recurring_blockers, ...report.possible_duplicates] : [];
}

export default function Intelligence({ mode, onOpenInitiative }: IntelligenceProps) {
    const [overview, setOverview] = useState<IntelligenceOverview | null>(null);
    const [initiatives, setInitiatives] = useState<InitiativeSummary[]>([]);
    const [loading, setLoading] = useState(true);
    const [generating, setGenerating] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let active = true;
        void Promise.all([api.getIntelligence(), api.listInitiatives()])
            .then(([value, portfolio]) => {
                if (active) {
                    setOverview(value);
                    setInitiatives(portfolio);
                }
            })
            .catch((reason: unknown) => {
                if (active) setError(reason instanceof Error ? reason.message : "Could not load intelligence");
            })
            .finally(() => {
                if (active) setLoading(false);
            });
        return () => {
            active = false;
        };
    }, []);

    async function generateInsights(): Promise<void> {
        setGenerating(true);
        setError(null);
        try {
            await api.generatePortfolioInsights();
            const [nextOverview, portfolio] = await Promise.all([api.getIntelligence(), api.listInitiatives()]);
            setOverview(nextOverview);
            setInitiatives(portfolio);
        } catch (reason: unknown) {
            setError(reason instanceof Error ? reason.message : "Could not generate portfolio insights");
        } finally {
            setGenerating(false);
        }
    }

    const isPatterns = mode === "patterns";
    const patterns = overview ? reportPatterns(overview) : [];
    const candidates = overview?.scout_candidates ?? [];
    const initiativeNames = new Map(initiatives.map((initiative) => [initiative.id, initiative.title]));
    const highPriorityCount = patterns.filter((pattern) => pattern.priority === "HIGH").length;
    const duplicateCount = patterns.filter((pattern) => pattern.category === "DUPLICATE").length;

    return (
        <section className="intelligence-desk" aria-labelledby="intelligence-title">
            <div className="page-intro">
                <div>
                    <p className="eyebrow">{isPatterns ? "Portfolio intelligence" : "Candidate discovery"}</p>
                    <h2 id="intelligence-title">{isPatterns ? "Patterns across initiatives" : "Scout candidate queue"}</h2>
                    <p>
                        {isPatterns
                            ? "Find recurring evidence gaps, adoption barriers, and lifecycle blockers across the portfolio."
                            : "Review potential pilots discovered from approved sources before they enter the portfolio."}
                    </p>
                </div>
                <div className="refresh-note">
                    <span className={`status-dot${error ? " status-dot-error" : loading ? " status-dot-loading" : ""}`} />
                    {loading ? "Refreshing..." : error ? "Data connection needs attention" : "Connected to live data"}
                </div>
            </div>

            {error ? <p className="error-message">{error}</p> : null}

            {isPatterns ? (
                <div className="intelligence-desk-grid">
                    <section className="panel intelligence-report">
                        <div className="panel-heading">
                            <div>
                                <p className="eyebrow">Latest report</p>
                                <h3>Portfolio signal</h3>
                            </div>
                            <div className="intelligence-actions">
                                {overview?.latest_portfolio_insight ? <time>{formatDate(overview.latest_portfolio_insight.created_at)}</time> : null}
                                <button className="insight-action" type="button" onClick={() => void generateInsights()} disabled={generating || loading}>
                                    {generating ? "Generating..." : overview?.latest_portfolio_insight ? "Refresh insights" : "Generate insights"}
                                </button>
                            </div>
                        </div>
                        {overview?.latest_portfolio_insight ? (
                            <div className="intelligence-body">
                                <div className="intelligence-kpis" aria-label="Portfolio insight summary">
                                    <div><strong>{initiatives.length}</strong><span>Pilots analysed</span></div>
                                    <div><strong>{patterns.length}</strong><span>Key signals</span></div>
                                    <div><strong>{highPriorityCount}</strong><span>High priority</span></div>
                                    <div><strong>{duplicateCount}</strong><span>Overlap signals</span></div>
                                </div>
                                <div className="intelligence-summary-block">
                                    <p className="eyebrow">Executive readout</p>
                                    <p className="intelligence-summary">{overview.latest_portfolio_insight.report.executive_summary}</p>
                                </div>
                                {overview.latest_portfolio_insight.report.recommendations.length ? (
                                    <div className="intelligence-next-actions">
                                        <p className="eyebrow">Recommended next actions</p>
                                        <div>{overview.latest_portfolio_insight.report.recommendations.slice(0, 4).map((recommendation) => <span key={recommendation}>{recommendation}</span>)}</div>
                                    </div>
                                ) : null}
                                <div className="pattern-list">
                                    {patterns.map((pattern) => (
                                        <article className="pattern-card" key={`${pattern.title}-${pattern.evidence_count}`}>
                                            <div className="pattern-card-heading">
                                                <div className="pattern-card-title"><span className={"signal-priority signal-" + (pattern.priority ?? "MEDIUM").toLowerCase()}>{pattern.priority ?? "SIGNAL"}</span><strong>{pattern.title}</strong></div>
                                                <span>{pattern.evidence_count} linked pilot{pattern.evidence_count === 1 ? "" : "s"}</span>
                                            </div>
                                            <div className="pattern-card-grid">
                                                <div><small>Why it matters</small><p>{pattern.why_it_matters || "This report predates structured rationale. Refresh insights to generate the operational consequence."}</p></div>
                                                <div><small>Next move</small><p>{pattern.recommended_action || "Refresh insights to generate a specific administrator action."}</p></div>
                                            </div>
                                            <details>
                                                <summary>Show evidence and linked pilots</summary>
                                                <p>{pattern.finding}</p>
                                                <div className="linked-pilots">{pattern.supporting_initiative_ids.map((id) => initiativeNames.has(id) ? (
                                                    <button type="button" key={id} onClick={() => onOpenInitiative?.(id)}>{initiativeNames.get(id)}</button>
                                                ) : <span key={id}>{id.slice(0, 8)}</span>)}</div>
                                            </details>
                                        </article>
                                    ))}
                                </div>
                                {!patterns.length ? <p className="empty-state">The latest report contains no patterns yet.</p> : null}
                            </div>
                        ) : (
                            <div className="empty-state intelligence-empty">
                                <strong>No portfolio insight is available.</strong>
                                <p>The Patterns agent will populate this surface after a portfolio analysis run.</p>
                            </div>
                        )}
                    </section>
                    <aside className="panel intelligence-method">
                        <p className="eyebrow">How this works</p>
                        <h3>Evidence-linked signals</h3>
                        <p>Oliver groups repeated themes across canonical pilots and links every finding back to the initiatives that support it.</p>
                        <dl>
                            <div><dt>Source</dt><dd>Canonical portfolio</dd></div>
                            <div><dt>Output</dt><dd>Patterns and blockers</dd></div>
                            <div><dt>Decision</dt><dd>Admin review required</dd></div>
                        </dl>
                    </aside>
                </div>
            ) : (
                <section className="panel scout-desk">
                    <div className="panel-heading">
                        <div>
                            <p className="eyebrow">Human review queue</p>
                            <h3>Potential pilots awaiting review</h3>
                            <p>{candidates.length} open candidate{candidates.length === 1 ? "" : "s"}</p>
                        </div>
                    </div>
                    {candidates.length ? (
                        <div className="scout-desk-list">
                            {candidates.map((candidate) => (
                                <article className="scout-desk-row" key={candidate.id}>
                                    <div className="scout-desk-title">
                                        <span className="initiative-mark" />
                                        <div><strong>{candidate.title}</strong><small>{candidate.source_system} - {candidate.source_reference}</small></div>
                                    </div>
                                    <p>{candidate.summary}</p>
                                    <div className="scout-desk-meta"><span>{Math.round(candidate.confidence * 100)}% confidence</span><time>{formatDate(candidate.discovered_at)}</time></div>
                                </article>
                            ))}
                        </div>
                    ) : (
                        <div className="empty-state intelligence-empty">
                            <strong>No Scout candidates are waiting for review.</strong>
                            <p>Approved source integrations will appear here when Scout discovers a potential pilot.</p>
                        </div>
                    )}
                </section>
            )}
        </section>
    );
}
