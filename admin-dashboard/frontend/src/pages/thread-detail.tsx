// Path: src/pages/thread-detail.tsx
// Description: Read-only detail view for one conversation and its canonical assessment.

import type { EmailThreadDetail } from "../lib/models";
import { dimensionLabel, formatDate, formatGate, initials } from "../lib/format";

interface ThreadDetailProps {
    thread: EmailThreadDetail;
    onBack: () => void;
    onOpenRelated: (threadId: string) => void;
}

export default function ThreadDetail({ thread, onBack, onOpenRelated }: ThreadDetailProps) {
    const latestRun = thread.runs.at(-1);
    const assessment = latestRun?.assessment ?? null;
    const totalTokens = thread.runs.reduce((total, run) => total + (run.prompt_tokens || 0) + (run.completion_tokens || 0), 0);
    const stageDisplay = assessment
        ? assessment.recommended_next_stage
            ? `${assessment.current_stage} → ${assessment.recommended_next_stage}`
            : assessment.current_stage
        : "—";

    return (
        <section className="detail-view" aria-labelledby="initiative-title">
            <button className="back-link" onClick={onBack}>
                <span aria-hidden="true">←</span> Initiative inbox
            </button>

            <div className="detail-heading">
                <div>
                    <p className="eyebrow">Conversation record</p>
                    <h2 id="initiative-title">{thread.subject || "Untitled conversation"}</h2>
                    <p>{thread.participant_email || "Unknown participant"}</p>
                </div>
                <span className={`status-badge ${assessment ? "status-complete" : "status-pending"}`}>
                    <span /> {assessment ? "Canonically assessed" : "Not scored"}
                </span>
            </div>

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
                                <h3>{thread.messages.length} recorded messages</h3>
                            </div>
                        </div>
                        <div className="message-list">
                            {thread.messages.map((message) => (
                                <article className={`message-card message-${message.direction.toLowerCase()}`} key={message.id}>
                                    <div className="message-meta">
                                        <div className="avatar avatar-small">{initials(message.sender_email)}</div>
                                        <div>
                                            <strong>{message.direction === "INBOUND" ? message.sender_email || "Sender" : "Oliver"}</strong>
                                            <small>{message.direction === "INBOUND" ? "Participant" : "Oliver reply"}</small>
                                        </div>
                                        <time>{formatDate(message.received_at)}</time>
                                    </div>
                                    <iframe
                                        className="message-frame"
                                        sandbox=""
                                        srcDoc={message.content_html || "<p>No content recorded.</p>"}
                                        title={`${message.direction.toLowerCase()} email from ${message.sender_email || "Oliver"}`}
                                    />
                                </article>
                            ))}
                        </div>
                    </section>

                    {thread.runs.some((run) => run.related_ideas.length > 0) && (
                        <section className="panel related-panel">
                            <div className="panel-heading">
                                <div>
                                    <p className="eyebrow">Semantic matches</p>
                                    <h3>Related conversations used by Oliver</h3>
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
                        <p className="eyebrow">Canonical assessment</p>
                        <div className="score-summary">
                            <strong>{assessment?.composite_score ?? "—"}</strong>
                            <span>
                                <b>{assessment?.rating || "Not scored"}</b>
                                <small>{assessment ? `${stageDisplay} · ${assessment.lifecycle_state}` : "No canonical score for this thread"}</small>
                            </span>
                        </div>
                        <p className="assessment-copy">
                            {assessment ? assessment.transition_rationale : "Oliver recorded no canonical assessment for this conversation."}
                        </p>
                        {assessment && (
                            <dl className="record-list">
                                <div>
                                    <dt>DI stage</dt>
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
                        <p className="eyebrow">Run record</p>
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
                                <dt>Conversation ID</dt>
                                <dd className="truncate" title={thread.conversation_id}>
                                    {thread.conversation_id}
                                </dd>
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
                    </section>
                </aside>
            </div>
        </section>
    );
}
