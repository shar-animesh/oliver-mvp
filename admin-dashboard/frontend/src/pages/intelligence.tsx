// Path: src/pages/intelligence.tsx
// Description: Dedicated portfolio intelligence and Scout review surfaces.

import { useEffect, useMemo, useState } from "react";

import { api } from "../api";
import { formatDate } from "../lib/format";
import type { InitiativeSummary, IntelligenceOverview, PortfolioPattern } from "../lib/models";

type IntelligenceMode = "patterns" | "scout";
type PatternFilter = "ALL" | "HIGH" | "EVIDENCE" | "EXECUTION" | "DUPLICATE";

interface IntelligenceProps {
    mode: IntelligenceMode;
    onOpenInitiative?: (id: string) => void;
    adminName?: string;
}

function reportPatterns(overview: IntelligenceOverview): PortfolioPattern[] {
    const report = overview.latest_portfolio_insight?.report;
    return report ? [...report.patterns, ...report.recurring_blockers, ...report.possible_duplicates] : [];
}

function outcomeLabel(outcome: string): string {
    if (outcome === "HOLD_FOR_EVIDENCE") return "More evidence";
    if (outcome === "CONDITIONAL_ADVANCE") return "Advance with conditions";
    if (outcome === "ADVANCE") return "Ready to advance";
    if (outcome === "HOLD_FOR_REVIEW") return "Human review";
    return outcome.replaceAll("_", " ").toLowerCase().replace(/(^|\s)\S/g, (letter) => letter.toUpperCase());
}

function patternCategory(pattern: PortfolioPattern): string {
    if (pattern.category === "DUPLICATE") return "Overlap";
    if (pattern.category === "SAFETY") return "Safety";
    if (pattern.category === "GOVERNANCE") return "Governance";
    if (pattern.category === "EXECUTION") return "Execution";
    if (pattern.category === "TECHNICAL") return "Technical";
    if (pattern.category === "EVIDENCE") return "Evidence";
    return "Portfolio";
}

function cleanPatternText(value: string, initiativeNames: Map<string, string>): string {
    let cleaned = value;
    for (const [id, title] of initiativeNames) {
        cleaned = cleaned.replace(new RegExp(id.slice(0, 8), "gi"), title);
        cleaned = cleaned.replace(new RegExp(id, "gi"), title);
    }
    return cleaned
        .replaceAll("HOLD_FOR_EVIDENCE", "more evidence required")
        .replaceAll("CONDITIONAL_ADVANCE", "advance with conditions")
        .replaceAll("HOLD_FOR_REVIEW", "human review");
}

export default function Intelligence({ mode, onOpenInitiative, adminName }: IntelligenceProps) {
    const [overview, setOverview] = useState<IntelligenceOverview | null>(null);
    const [initiatives, setInitiatives] = useState<InitiativeSummary[]>([]);
    const [loading, setLoading] = useState(true);
    const [generating, setGenerating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [patternFilter, setPatternFilter] = useState<PatternFilter>("ALL");

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
    const patterns = useMemo(() => (overview ? reportPatterns(overview) : []), [overview]);
    const candidates = overview?.scout_candidates ?? [];
    const initiativeNames = new Map(initiatives.map((initiative) => [initiative.id, initiative.title]));
    const highPriorityCount = patterns.filter((pattern) => pattern.priority === "HIGH").length;
    const duplicateCount = patterns.filter((pattern) => pattern.category === "DUPLICATE").length;
    const assessed = initiatives.filter((initiative) => initiative.latest_assessment_at);
    const stalledCount = initiatives.filter((initiative) => initiative.lifecycle_state.toLowerCase() === "stalled").length;
    const evidenceCount = initiatives.filter((initiative) => initiative.latest_gate_outcome === "HOLD_FOR_EVIDENCE").length;
    const incompleteCount = initiatives.filter((initiative) => initiative.latest_assessment_at && initiative.latest_score === null).length;
    const outcomeCounts = initiatives.reduce<Record<string, number>>((counts, initiative) => {
        if (initiative.latest_gate_outcome) counts[initiative.latest_gate_outcome] = (counts[initiative.latest_gate_outcome] ?? 0) + 1;
        return counts;
    }, {});
    const filteredPatterns = useMemo(
        () => patterns
            .filter((pattern) => patternFilter === "ALL" || (patternFilter === "HIGH" ? pattern.priority === "HIGH" : pattern.category === patternFilter))
            .sort((a, b) => Number(b.priority === "HIGH") - Number(a.priority === "HIGH")),
        [patterns, patternFilter],
    );
    const adminFirstName = (adminName || "administrator").split(/[.@_ -]/)[0];

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
                                <div className="portfolio-pulse">
                                    <div className="pulse-heading"><div><p className="eyebrow">Current portfolio picture</p><h4>Hi {adminFirstName} — what is happening now</h4><p className="pulse-intro">Oliver currently has {initiatives.length} registered pilot{initiatives.length === 1 ? "" : "s"} and {assessed.length} with an assessment.</p></div><span>Updated from live portfolio data</span></div>
                                    <div className="intelligence-kpis" aria-label="Current portfolio picture">
                                        <div><strong>{initiatives.length}</strong><span>Pilots in portfolio</span></div>
                                        <div><strong>{stalledCount}</strong><span>Currently stalled</span></div>
                                        <div><strong>{evidenceCount}</strong><span>Need more evidence</span></div>
                                        <div><strong>{highPriorityCount}</strong><span>High-priority findings</span></div>
                                    </div>
                                    <div className="assessment-outcomes">
                                        <p className="eyebrow">Latest assessment outcomes</p>
                                        <div>{Object.entries(outcomeCounts).map(([outcome, count]) => <span key={outcome}><strong>{count}</strong>{outcomeLabel(outcome)}</span>)}</div>
                                        {incompleteCount ? <small>{incompleteCount} assessed pilot{incompleteCount === 1 ? "" : "s"} still have an incomplete overall score.</small> : null}
                                    </div>
                                </div>
                                <div className="pattern-toolbar">
                                    <div><p className="eyebrow">Portfolio patterns</p><h4>Priority findings <span className="toolbar-count">{duplicateCount} overlap</span></h4></div>
                                    <div className="pattern-filters" role="group" aria-label="Filter findings">
                                        {(["ALL", "HIGH", "EVIDENCE", "EXECUTION", "DUPLICATE"] as PatternFilter[]).map((filter) => <button type="button" className={patternFilter === filter ? "selected" : ""} key={filter} onClick={() => setPatternFilter(filter)}>{filter === "ALL" ? "All" : filter === "HIGH" ? "High priority" : filter === "DUPLICATE" ? "Overlap" : filter[0] + filter.slice(1).toLowerCase()}</button>)}
                                    </div>
                                </div>
                                <div className="pattern-list">
                                    {filteredPatterns.map((pattern) => (
                                        <article className="pattern-card" key={`${pattern.title}-${pattern.evidence_count}`}>
                                            <div className="pattern-card-heading">
                                                <div className="pattern-card-title"><span className={"signal-priority signal-" + (pattern.priority ?? "MEDIUM").toLowerCase()}>{pattern.priority ?? "SIGNAL"}</span><span className="signal-category">{patternCategory(pattern)}</span><strong>{cleanPatternText(pattern.title, initiativeNames)}</strong></div>
                                                <span>{pattern.evidence_count} linked pilot{pattern.evidence_count === 1 ? "" : "s"}</span>
                                            </div>
                                            <div className="pattern-card-grid">
                                                <div><small>Impact</small><p>{cleanPatternText(pattern.why_it_matters || "Refresh insights to generate the operational consequence.", initiativeNames)}</p></div>
                                                <div><small>Suggested admin action</small><p>{cleanPatternText(pattern.recommended_action || "Refresh insights to generate a specific administrator action.", initiativeNames)}</p></div>
                                            </div>
                                            <details>
                                                <summary>View evidence and affected pilots</summary>
                                                <p>{cleanPatternText(pattern.finding, initiativeNames)}</p>
                                                <div className="linked-pilots">{pattern.supporting_initiative_ids.map((id) => initiativeNames.has(id) ? (
                                                    <button type="button" key={id} onClick={() => onOpenInitiative?.(id)}>{initiativeNames.get(id)}</button>
                                                ) : <span key={id}>Linked pilot</span>)}</div>
                                            </details>
                                        </article>
                                    ))}
                                </div>
                                {!filteredPatterns.length ? <p className="empty-state">No findings match this filter.</p> : null}
                            </div>
                        ) : (
                            <div className="empty-state intelligence-empty">
                                <strong>No portfolio insight is available.</strong>
                                <p>The Patterns agent will populate this surface after a portfolio analysis run.</p>
                            </div>
                        )}
                    </section>
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
