// Path: src/pages/thread-detail.tsx
// Description: Read-only detail view for one conversation and its canonical assessment.

import { useState } from "react";

import { api } from "../api";
import type { EmailThreadDetail } from "../lib/models";
import { dimensionLabel, formatDate, formatGate, initials } from "../lib/format";

interface ThreadDetailProps {
    thread: EmailThreadDetail;
    onBack: () => void;
    onOpenRelated: (threadId: string) => void;
    onOpenInitiative: (initiativeId: string) => void;
}

export default function ThreadDetail({ thread, onBack, onOpenRelated, onOpenInitiative }: ThreadDetailProps) {
    const [expandedMessageId, setExpandedMessageId] = useState<string | null>(null);
    const [messageContent, setMessageContent] = useState<Record<string, string | null>>(() =>
        Object.fromEntries(thread.messages.filter((message) => message.content_html !== null).map((message) => [message.id, message.content_html])),
    );
    const [loadingMessageId, setLoadingMessageId] = useState<string | null>(null);
    // A conversation can have follow-up runs that intentionally do not create an
    // assessment (for example, a clarification or a NO_REPLY decision).  The
    // latest processing run is still useful for delivery telemetry, but it must
    // not hide the latest assessment from the assessment panel.
    const runsByCreatedAt = [...thread.runs].sort((left, right) => Date.parse(left.created_at) - Date.parse(right.created_at));
    const latestRun = runsByCreatedAt.at(-1);
    const latestAssessmentRun = [...runsByCreatedAt].reverse().find((run) => run.assessment !== null);
    const assessment = latestAssessmentRun?.assessment ?? null;
    const totalTokens = thread.runs.reduce((total, run) => total + (run.prompt_tokens || 0) + (run.completion_tokens || 0), 0);
    const scoredDimensionCount = assessment?.dimensions.filter((dimension) => dimension.value !== null).length ?? 0;
    const unknownDimensions = assessment?.dimensions.filter((dimension) => dimension.value === null).map((dimension) => dimension.dimension_label) ?? [];
    // Defensive reader-side projection: older API records can still contain the
    // same Oliver response more than once after a connector retry. Keep one
    // copy in the visible history while preserving every distinct inbound reply.
    const visibleMessages = thread.messages.filter((message, index, messages) => {
        if (message.direction !== "OUTBOUND") return true;
        const normalize = (value: string | null) => (value || "").replace(/\s+/g, " ").trim();
        const signature = `${normalize(message.subject)}|${normalize(message.content_html)}`;
        return messages.findIndex((candidate) => candidate.direction === "OUTBOUND" && `${normalize(candidate.subject)}|${normalize(candidate.content_html)}` === signature) === index;
    });

    function messageKindLabel(kind: EmailThreadDetail["messages"][number]["message_kind"]): string {
        return {
            NEW: "New email",
            REPLY: "Reply",
            FORWARDED: "Forwarded email",
            OLIVER_RESPONSE: "Oliver response",
        }[kind];
    }

    function downloadHtml(content: string | null, messageId: string, subject: string | null): void {
        if (!content) return;
        const blob = new Blob([content], { type: "text/html;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${(subject || "oliver-reply").replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").toLowerCase()}-${messageId.slice(0, 8)}.html`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    }

    async function toggleMessage(messageId: string): Promise<void> {
        if (expandedMessageId === messageId) {
            setExpandedMessageId(null);
            return;
        }
        setExpandedMessageId(messageId);
        if (Object.prototype.hasOwnProperty.call(messageContent, messageId)) return;
        setLoadingMessageId(messageId);
        try {
            const content = await api.getEmailMessageContent(thread.id, messageId);
            setMessageContent((current) => ({ ...current, [messageId]: content.content_html }));
        } catch {
            setExpandedMessageId(null);
        } finally {
            setLoadingMessageId((current) => current === messageId ? null : current);
        }
    }
    const stageDisplay = assessment
        ? assessment.recommended_next_stage
            ? `${assessment.current_stage} → ${assessment.recommended_next_stage}`
            : assessment.current_stage
        : "—";

    const stageName = (stage: string | null): string => ({
        DI1: "Concept",
        DI2: "Pilot",
        DI3: "Test",
        DI4: "Implement",
        DI5: "Scale",
    }[stage || ""] || stage || "Not available");
    const firstInbound = thread.messages.find((message) => message.direction === "INBOUND");
    const participantEmail = firstInbound?.sender_email || thread.participant_email;
    const participantName = (participantEmail?.split("@")[0] || "The participant")
        .replace(/[._-]+/g, " ")
        .replace(/(^|\s)\S/g, (letter) => letter.toUpperCase());
    const requestSubject = (thread.subject || "this pilot idea").replace(/^(re|reply|fw|fwd):\s*/i, "");
    const conversationSummary = assessment
        ? participantName + " from Siemens Energy sent this on " + formatDate(firstInbound?.received_at || thread.created_at) + " about “" + requestSubject + "”. Oliver assessed it at " + (assessment.composite_score ?? "an incomplete score") + " and returned “" + formatGate(assessment.gate_outcome) + "”."
        : participantName + " from Siemens Energy sent this on " + formatDate(firstInbound?.received_at || thread.created_at) + " about “" + requestSubject + "”. Oliver has not recorded an assessment for it yet.";

    return (
        <section className="detail-view" aria-labelledby="initiative-title">
            <button className="back-link" onClick={onBack}>
                <span aria-hidden="true">←</span> Conversation inbox
            </button>

            <div className="detail-heading">
                <div>
                    <p className="eyebrow">Conversation record</p>
                    <h2 id="initiative-title">{thread.subject || "Untitled conversation"}</h2>
                    <p>{thread.participant_email || "Unknown participant"}</p>
                </div>
                <div className="detail-heading-actions">
                    <span className={`status-badge ${assessment ? "status-complete" : "status-pending"}`}>
                        <span /> {assessment ? (assessment.composite_score !== null ? "Score complete" : "Assessment recorded") : "Not assessed"}
                    </span>
                    <span className="detail-date">Updated {formatDate(thread.updated_at)}</span>
                </div>
            </div>

            {thread.initiative_id ? (
                <>
                <section className="panel pilot-overview" aria-labelledby="pilot-overview-title">
                    <div className="panel-heading">
                        <div>
                            <p className="eyebrow">Pilot overview</p>
                            <h3 id="pilot-overview-title">{thread.initiative_title || "Linked pilot"}</h3>
                        </div>
                        <button className="insight-action" type="button" onClick={() => onOpenInitiative(thread.initiative_id as string)}>Open Portfolio detail</button>
                    </div>
                    <div className="pilot-overview-grid">
                        <div><small>Current stage</small><strong>{stageName(thread.initiative_current_stage)}</strong><span>{thread.initiative_current_stage || "—"}</span></div>
                        <div><small>Lifecycle state</small><strong>{thread.initiative_lifecycle_state || "Not available"}</strong></div>
                        <div><small>Latest score</small><strong>{assessment?.composite_score ?? (assessment ? "Incomplete" : "—")}</strong><span>{assessment?.rating || "Not assessed"}</span></div>
                        <div><small>Gate outcome</small><strong>{assessment ? formatGate(assessment.gate_outcome) : "Not assessed"}</strong><span>{assessment ? scoredDimensionCount + "/" + assessment.dimensions.length + " dimensions scored" : "No assessment recorded"}</span></div>
                    </div>
                </section>
                <button className="pilot-context" type="button" onClick={() => onOpenInitiative(thread.initiative_id as string)}>
                    <span>
                        <small>Linked pilot</small>
                        <strong>{thread.initiative_title || "Open pilot detail"}</strong>
                    </span>
                    <span>
                        {thread.initiative_current_stage || "Stage unavailable"} · {thread.initiative_lifecycle_state || "State unavailable"} <span aria-hidden="true">→</span>
                    </span>
                </button>
                </>
            ) : (
                <div className="pilot-context pilot-context-unlinked">
                    <span>
                        <small>Pilot linkage</small>
                        <strong>No initiative is linked to this conversation yet.</strong>
                    </span>
                </div>
            )}

            <section className="panel conversation-summary" aria-labelledby="conversation-summary-title">
                <p className="eyebrow">Conversation summary</p>
                <h3 id="conversation-summary-title">What this conversation means</h3>
                <p>{conversationSummary}</p>
            </section>

            <div className="detail-grid">
                <div className="detail-main">
                    {assessment && (
                        <section className="panel dimension-panel">
                            <div className="panel-heading">
                                <div>
                                    <p className="eyebrow">Assessment criteria</p>
                                    <h3>Five-dimension evidence profile</h3>
                                </div>
                                <small>{assessment.weight_set_version}</small>
                            </div>
                            <div className="dimension-list">
                                {assessment.dimensions.map((dimension) => (
                                    <article className="dimension-row" key={dimension.dimension}>
                                        <div className="dimension-heading">
                                            <span>
                                                <strong>{dimension.dimension_label}</strong>
                                                <small>
                                                    {dimension.weight}% weight · {Math.round(dimension.confidence * 100)}% confidence
                                                </small>
                                            </span>
                                            <strong>{dimension.value ?? dimension.state.replaceAll("_", " ")}</strong>
                                        </div>
                                        <div
                                            className="score-track"
                                            aria-label={`${dimension.dimension_label}: ${dimension.value ?? dimension.state}`}>
                                            <span style={{ width: `${dimension.value ?? 0}%` }} />
                                        </div>
                                        <p>{dimension.summary}</p>
                                        {dimension.evidence.length > 0 && (
                                            <details>
                                                <summary>
                                                    {dimension.evidence.length} supporting evidence item{dimension.evidence.length === 1 ? "" : "s"}
                                                </summary>
                                                <ul>
                                                    {dimension.evidence.map((item) => (
                                                        <li key={item}>{item}</li>
                                                    ))}
                                                </ul>
                                            </details>
                                        )}
                                        {dimension.gaps.length > 0 && (
                                            <details>
                                                <summary>
                                                    {dimension.gaps.length} evidence gap{dimension.gaps.length === 1 ? "" : "s"}
                                                </summary>
                                                <ul>
                                                    {dimension.gaps.map((gap) => (
                                                        <li key={gap}>{gap}</li>
                                                    ))}
                                                </ul>
                                            </details>
                                        )}
                                    </article>
                                ))}
                            </div>
                        </section>
                    )}
                    <section className="panel">
                        <div className="panel-heading">
                            <div>
                                <p className="eyebrow">Communication history</p>
                                <h3>{visibleMessages.length} recorded messages</h3>
                            </div>
                            <span className="refresh-note">{thread.runs.length} Oliver processing run{thread.runs.length === 1 ? "" : "s"}</span>
                        </div>
                        <div className="message-list">
                            {visibleMessages.map((message) => (
                                <article className={`message-card message-${message.direction.toLowerCase()}`} key={message.id}>
                                    <div className="message-meta">
                                        <div className="avatar avatar-small">{initials(message.sender_email)}</div>
                                        <div>
                                            <strong>{message.direction === "INBOUND" ? message.sender_email || "Sender" : "Oliver"}</strong>
                                            <small>
                                                {message.direction === "INBOUND" ? "Participant" : "Oliver response"} · {messageKindLabel(message.message_kind)}
                                            </small>
                                        </div>
                                        <div className="message-actions">
                                            <time>{formatDate(message.received_at)}</time>
                                            <button
                                                type="button"
                                                className="message-toggle"
                                                aria-expanded={expandedMessageId === message.id}
                                                onClick={() => void toggleMessage(message.id)}>
                                                {expandedMessageId === message.id ? "Hide message" : loadingMessageId === message.id ? "Loading…" : "View message"}
                                            </button>
                                            {message.direction === "OUTBOUND" && messageContent[message.id] ? (
                                                <button
                                                    type="button"
                                                    className="download-button"
                                                    onClick={() => downloadHtml(messageContent[message.id] || null, message.id, message.subject || thread.subject)}
                                                    title="Download this Oliver reply as HTML">
                                                    Download HTML
                                                </button>
                                            ) : null}
                                        </div>
                                    </div>
                                    {expandedMessageId === message.id && loadingMessageId !== message.id ? (
                                        <iframe
                                            className="message-frame"
                                            loading="lazy"
                                            sandbox=""
                                            srcDoc={messageContent[message.id] || "<p>No content recorded.</p>"}
                                            title={`${message.direction.toLowerCase()} email from ${message.sender_email || "Oliver"}`}
                                        />
                                    ) : expandedMessageId === message.id ? (
                                        <div className="message-collapsed">Loading message content…</div>
                                    ) : (
                                        <div className="message-collapsed">Message content is collapsed for a faster history view.</div>
                                    )}
                                </article>
                            ))}
                        </div>
                    </section>

                    {thread.runs.some((run) => run.related_ideas.length > 0) && (
                        <section className="panel related-panel">
                            <div className="panel-heading">
                                <div>
                                        <p className="eyebrow">Related conversations</p>
                                        <h3>Conversations used as context</h3>
                                </div>
                            </div>
                            {thread.runs.flatMap((run) =>
                                run.related_ideas.map((idea) => (
                                    <button className="related-row" key={`${run.id}-${idea.thread_id}`} onClick={() => onOpenRelated(idea.thread_id)}>
                                        <span>
                                            <strong>{idea.subject || "Untitled related conversation"}</strong>
                                            <small>{idea.participant_email || "Unknown participant"}</small>
                                        </span>
                                        <span className="similarity">{Math.round((1 - idea.cosine_distance) * 100)}% similarity</span>
                                    </button>
                                )),
                            )}
                        </section>
                    )}
                </div>

                <aside className="detail-rail">
                    <section className="panel assessment-card">
                        <p className="eyebrow">Assessment summary</p>
                        <div className="score-summary">
                            <strong>{assessment?.composite_score ?? (assessment ? "Incomplete" : "—")}</strong>
                            <span>
                                <b>{assessment?.rating || "Not scored"}</b>
                            <small>
                                {assessment
                                    ? `${scoredDimensionCount}/${assessment.dimensions.length} dimensions scored · ${stageDisplay} · ${assessment.lifecycle_state}`
                                    : "No assessment recorded for this conversation"}
                            </small>
                            </span>
                        </div>
                        <div className="assessment-readout">
                            <span className="readout-label">Executive readout</span>
                            <p>{assessment ? assessment.score_rationale || assessment.transition_rationale : "Oliver has not recorded an assessment for this conversation yet."}</p>
                        </div>
                        {assessment ? <p className="assessment-copy">{assessment.transition_rationale}</p> : null}
                        {assessment && (
                            <dl className="record-list">
                                <div>
                                    <dt>Pilot stage</dt>
                                    <dd>{thread.initiative_current_stage || "Not linked"}</dd>
                                </div>
                                <div>
                                    <dt>Assessment stage</dt>
                                    <dd>{stageDisplay}</dd>
                                </div>
                                <div>
                                    <dt>Gate outcome</dt>
                                    <dd>{formatGate(assessment.gate_outcome)}</dd>
                                </div>
                                <div>
                                    <dt>Confidence</dt>
                                    <dd>
                                        {assessment.composite_confidence !== null ? `${Math.round(assessment.composite_confidence * 100)}%` : "—"}
                                    </dd>
                                </div>
                                <div>
                                    <dt>Lowest confidence</dt>
                                    <dd>{dimensionLabel(assessment.dimensions, assessment.lowest_confidence_dimension)}</dd>
                                </div>
                                {unknownDimensions.length ? (
                                    <div>
                                        <dt>Score gaps</dt>
                                        <dd>{unknownDimensions.join(", ")}</dd>
                                    </div>
                                ) : null}
                                <div>
                                    <dt>Human review</dt>
                                    <dd>{assessment.requires_human_review ? "Required" : "Not required"}</dd>
                                </div>
                                <div>
                                    <dt>Scoring policy</dt>
                                    <dd>{assessment.model_version}</dd>
                                </div>
                            </dl>
                        )}
                    </section>

                    <section className="panel">
                        <p className="eyebrow">Processing record</p>
                        <dl className="record-list">
                            <div>
                                <dt>Delivery action</dt>
                                <dd>
                                    {latestRun?.action === "SEND_EMAIL"
                                        ? latestRun.delivery_status || "Untracked"
                                        : latestRun?.action || "Not available"}
                                </dd>
                            </div>
                            <div>
                                <dt>Delivery attempts</dt>
                                <dd>{latestRun?.delivery_attempt_count ?? 0}</dd>
                            </div>
                            <div>
                                <dt>Delivered</dt>
                                <dd>{latestRun?.delivered_at ? formatDate(latestRun.delivered_at) : "Not confirmed"}</dd>
                            </div>
                            {latestRun?.delivery_last_error ? (
                                <div>
                                    <dt>Delivery error</dt>
                                    <dd>{latestRun.delivery_last_error}</dd>
                                </div>
                            ) : null}
                            <div>
                                <dt>Model</dt>
                                <dd>{latestRun?.model_name || "Not configured"}</dd>
                            </div>
                            <div>
                                <dt>Total tokens</dt>
                                <dd>{totalTokens ? totalTokens.toLocaleString() : "—"}</dd>
                            </div>
                            <div>
                                <dt>Created</dt>
                                <dd>{formatDate(thread.created_at)}</dd>
                            </div>
                            <div>
                                <dt>Last updated</dt>
                                <dd>{formatDate(thread.updated_at)}</dd>
                            </div>
                            <div>
                                <dt>Semantic index</dt>
                                <dd>{thread.embedded_at ? `${thread.embedding_dimensions || 0} dimensions` : "Not indexed"}</dd>
                            </div>
                        </dl>
                        <details className="technical-details">
                            <summary>Technical diagnostics</summary>
                            <dl className="record-list">
                                <div>
                                    <dt>Conversation reference</dt>
                                    <dd className="truncate" title={thread.conversation_id}>{thread.conversation_id}</dd>
                                </div>
                            </dl>
                        </details>
                    </section>
                </aside>
            </div>
        </section>
    );
}
