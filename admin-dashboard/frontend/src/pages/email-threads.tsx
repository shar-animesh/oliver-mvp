// Path: src/pages/email-threads.tsx
// Description: Read-only inbox of Oliver conversations and their canonical assessments.

import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import MetricCard from "../components/metric-card";
import { formatDate, formatGate, initials } from "../lib/format";
import type { EmailThreadDetail, EmailThreadSummary } from "../lib/models";
import ThreadDetail from "./thread-detail";

interface EmailThreadsProps {
    initialThreadId: string | null;
    onOpenInitiative: (initiativeId: string) => void;
    onOpenThread?: (threadId: string) => void;
}

type StatusFilter = "all" | "assessed" | "complete" | "needs-evidence" | "unassessed";

export default function EmailThreads({ initialThreadId, onOpenInitiative, onOpenThread }: EmailThreadsProps) {
    const [threads, setThreads] = useState<EmailThreadSummary[]>([]);
    const [selectedThread, setSelectedThread] = useState<EmailThreadDetail | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [detailLoading, setDetailLoading] = useState(false);
    const [query, setQuery] = useState("");
    const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
    const detailRequestId = useRef(0);

    useEffect(() => {
        void api
            .listEmailThreads()
            .then(setThreads)
            .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load conversations"))
            .finally(() => setLoading(false));
    }, []);

    const assessedCount = threads.filter((thread) => thread.assessment_count > 0).length;
    const completeScoreCount = threads.filter((thread) => thread.canonical_score !== null).length;
    const needsEvidenceCount = threads.filter((thread) => thread.assessment_count > 0 && thread.canonical_score === null).length;
    const unassessedCount = threads.filter((thread) => thread.assessment_count === 0).length;

    const filteredThreads = useMemo(() => {
        const normalizedQuery = query.trim().toLowerCase();
        return threads.filter((thread) => {
            const matchesStatus =
                statusFilter === "all" ||
                (statusFilter === "assessed" && thread.assessment_count > 0) ||
                (statusFilter === "complete" && thread.canonical_score !== null) ||
                (statusFilter === "needs-evidence" && thread.assessment_count > 0 && thread.canonical_score === null) ||
                (statusFilter === "unassessed" && thread.assessment_count === 0);
            const matchesQuery =
                !normalizedQuery ||
                [thread.subject, thread.participant_email, thread.conversation_id].some((value) => value?.toLowerCase().includes(normalizedQuery));
            return matchesStatus && matchesQuery;
        });
    }, [query, statusFilter, threads]);

    const messageCount = threads.reduce((total, thread) => total + thread.message_count, 0);
    const gatePasses = threads.filter((thread) => ["ADVANCE", "CONDITIONAL_ADVANCE"].includes(thread.gate_outcome || "")).length;
    const scoredThreads = threads.filter((thread) => thread.canonical_score !== null);
    const averageScore =
        scoredThreads.length === 0
            ? null
            : Math.round(scoredThreads.reduce((total, thread) => total + (thread.canonical_score ?? 0), 0) / scoredThreads.length);

    async function openThread(threadId: string): Promise<void> {
        const requestId = ++detailRequestId.current;
        setError(null);
        setDetailLoading(true);
        try {
            const thread = await api.getEmailThread(threadId);
            if (requestId === detailRequestId.current) setSelectedThread(thread);
        } catch (reason: unknown) {
            if (requestId === detailRequestId.current) {
                setError(reason instanceof Error ? reason.message : "Could not load the conversation record");
            }
        } finally {
            if (requestId === detailRequestId.current) setDetailLoading(false);
        }
    }

    useEffect(() => {
        if (initialThreadId) window.setTimeout(() => void openThread(initialThreadId), 0);
    }, [initialThreadId]);

    function closeThread(): void {
        setSelectedThread(null);
        window.history.replaceState(null, "", "/conversations");
    }

    if (selectedThread) {
        return (
            <>
                {detailLoading ? <p className="empty-state">Loading related conversation...</p> : null}
                {error ? <p className="error-message">{error}</p> : null}
                <ThreadDetail
                    thread={selectedThread}
                    onBack={closeThread}
                    onOpenRelated={(id) => {
                        if (onOpenThread) onOpenThread(id);
                        else void openThread(id);
                    }}
                    onOpenInitiative={onOpenInitiative}
                />
            </>
        );
    }

    return (
        <div id="overview">
            <section className="page-intro">
                <div>
                    <p className="eyebrow">Conversations</p>
                    <h2>Conversation review</h2>
                    <p>Review incoming ideas, Oliver&apos;s assessments, and the full message history.</p>
                </div>
                <div className="refresh-note">
                    <span className={`status-dot${error ? " status-dot-error" : loading ? " status-dot-loading" : ""}`} />
                    {loading ? "Refreshing…" : error ? "Data connection needs attention" : "Connected to live data"}
                </div>
            </section>

            <section className="metric-grid" aria-label="Assessment summary">
                <MetricCard label="Conversations" value={threads.length} note={`${messageCount} messages recorded`} loading={loading} tone="accent" />
                <MetricCard label="Assessed conversations" value={assessedCount} note={`${completeScoreCount} complete score${completeScoreCount === 1 ? "" : "s"}`} loading={loading} />
                <MetricCard label="Needs evidence" value={needsEvidenceCount} note="Assessment is incomplete" loading={loading} />
                <MetricCard
                    label="Average overall score"
                    value={averageScore ?? "—"}
                    note={averageScore === null ? "No complete scores" : `Across ${completeScoreCount} complete score${completeScoreCount === 1 ? "" : "s"}`}
                    loading={loading}
                />
                <MetricCard label="Recommended advances" value={gatePasses} note="Ready for the next stage" loading={loading} tone="operational" />
            </section>

            <section className="panel initiative-panel" id="initiative-inbox">
                <div className="panel-heading inbox-heading">
                    <div>
                        <p className="eyebrow">Inbox</p>
                        <h3>Conversation queue</h3>
                        <p>{threads.length} total records</p>
                    </div>
                    <label className="search-field">
                        <span className="sr-only">Search conversations</span>
                        <svg aria-hidden="true" viewBox="0 0 20 20">
                            <path d="m14.2 13.14 3.33 3.33-1.06 1.06-3.33-3.33a6.5 6.5 0 1 1 1.06-1.06ZM9 14a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z" />
                        </svg>
                        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by subject or participant" />
                    </label>
                </div>

                <div className="queue-tabs" role="tablist" aria-label="Assessment status">
                    <button
                        className={statusFilter === "all" ? "active" : ""}
                        onClick={() => setStatusFilter("all")}
                        role="tab"
                        aria-selected={statusFilter === "all"}>
                        All <span>{threads.length}</span>
                    </button>
                    <button
                        className={statusFilter === "assessed" ? "active" : ""}
                        onClick={() => setStatusFilter("assessed")}
                        role="tab"
                        aria-selected={statusFilter === "assessed"}>
                        Assessed <span>{assessedCount}</span>
                    </button>
                    <button
                        className={statusFilter === "complete" ? "active" : ""}
                        onClick={() => setStatusFilter("complete")}
                        role="tab"
                        aria-selected={statusFilter === "complete"}>
                        Complete score <span>{completeScoreCount}</span>
                    </button>
                    <button
                        className={statusFilter === "needs-evidence" ? "active" : ""}
                        onClick={() => setStatusFilter("needs-evidence")}
                        role="tab"
                        aria-selected={statusFilter === "needs-evidence"}>
                        Needs evidence <span>{needsEvidenceCount}</span>
                    </button>
                    <button
                        className={statusFilter === "unassessed" ? "active" : ""}
                        onClick={() => setStatusFilter("unassessed")}
                        role="tab"
                        aria-selected={statusFilter === "unassessed"}>
                        Not assessed <span>{unassessedCount}</span>
                    </button>
                </div>

                {error && <p className="error-message">{error}</p>}
                {detailLoading && <div className="loading-bar" />}

                {loading ? (
                    <div className="empty-state">
                        <div className="empty-icon">•••</div>
                        <h4>Loading conversation records</h4>
                        <p>Connecting to the Oliver admin service.</p>
                    </div>
                ) : filteredThreads.length === 0 && !error ? (
                    <div className="empty-state">
                        <div className="empty-icon">0</div>
                        <h4>{threads.length === 0 ? "No conversations recorded" : "No matching conversations"}</h4>
                        <p>
                            {threads.length === 0
                                ? "New conversations will appear here after Oliver receives them."
                                : "Adjust your search and try again."}
                        </p>
                    </div>
                ) : (
                    <div className="data-table" role="table" aria-label="Conversation queue">
                        <div className="data-header" role="row">
                            <span role="columnheader">Conversation</span>
                            <span role="columnheader">Participant</span>
                            <span role="columnheader">Score</span>
                            <span role="columnheader">Pilot stage</span>
                            <span role="columnheader">Gate outcome</span>
                            <span role="columnheader">Last activity</span>
                            <span aria-hidden="true" />
                        </div>
                        {filteredThreads.map((thread) => (
                            <button className="data-row" role="row" key={thread.id} onClick={() => {
                                if (onOpenThread) onOpenThread(thread.id);
                                else void openThread(thread.id);
                            }}>
                                <span className="initiative-cell" role="cell">
                                    <span className="initiative-mark" />
                                    <span>
                                        <strong>{thread.subject || "Untitled conversation"}</strong>
                                        <small>{thread.initiative_title || "No linked pilot"}</small>
                                    </span>
                                </span>
                                <span className="owner-cell" role="cell">
                                    <span className="avatar">{initials(thread.participant_email)}</span>
                                    <span>{thread.participant_email || "Unknown participant"}</span>
                                </span>
                                <span role="cell">
                                    <strong className="table-score">{thread.canonical_score ?? (thread.assessment_count > 0 ? "Incomplete" : "—")}</strong>
                                    <small className="score-status">
                                        {thread.canonical_score !== null ? thread.rating || "Complete" : thread.assessment_count > 0 ? "Evidence required" : "Not assessed"}
                                    </small>
                                </span>
                                <span className="numeric-cell" role="cell">
                                    {thread.di_stage || "—"}
                                </span>
                                <span role="cell">
                                    <span className={`status-badge ${thread.canonical_score !== null ? "status-complete" : "status-pending"}`}>
                                        <span /> {formatGate(thread.gate_outcome)}
                                    </span>
                                </span>
                                <time role="cell">{formatDate(thread.last_activity_at)}</time>
                                <span className="row-arrow" aria-hidden="true">
                                    →
                                </span>
                            </button>
                        ))}
                    </div>
                )}
            </section>
        </div>
    );
}
