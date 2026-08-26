// Path: src/pages/assessment-lab.tsx
// Description: Non-persistent assessment sandbox for authorized administrators.

import { useState, type FormEvent } from "react";

import { api } from "../api";
import type { AssessmentTestResult, DIStage } from "../lib/models";

const STAGES: Array<{ value: DIStage; label: string }> = [
    { value: "DI1", label: "DI1 · Concept" },
    { value: "DI2", label: "DI2 · Pilot" },
    { value: "DI3", label: "DI3 · Test" },
    { value: "DI4", label: "DI4 · Implement" },
    { value: "DI5", label: "DI5 · Scale" },
];

export default function AssessmentLab() {
    const [subject, setSubject] = useState("");
    const [evidence, setEvidence] = useState("");
    const [stage, setStage] = useState<DIStage>("DI1");
    const [result, setResult] = useState<AssessmentTestResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [running, setRunning] = useState(false);

    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setRunning(true);
        setError(null);
        setResult(null);
        try {
            setResult(await api.runAssessmentTest({ subject, evidence, current_stage: stage }));
        } catch (reason: unknown) {
            setError(reason instanceof Error ? reason.message : "The assessment test could not be completed");
        } finally {
            setRunning(false);
        }
    }

    return (
        <section className="assessment-lab">
            <div className="page-intro">
                <div>
                    <p className="eyebrow">Assessment sandbox</p>
                    <h2>Assessment laboratory</h2>
                    <p>Evaluate draft evidence without creating an initiative, assessment record, or lifecycle decision.</p>
                </div>
                    <span className="lab-safety">No records created</span>
            </div>

            <div className="lab-layout">
                <form className="panel lab-form" onSubmit={submit}>
                    <div className="panel-heading">
                        <div>
                            <p className="eyebrow">Assessment input</p>
                            <h3>Initiative evidence</h3>
                        </div>
                    </div>
                    <label htmlFor="assessment-subject">Working title</label>
                    <input
                        id="assessment-subject"
                        value={subject}
                        onChange={(event) => setSubject(event.target.value)}
                        placeholder="Predictive maintenance for gas turbines"
                        minLength={3}
                        maxLength={200}
                        required
                    />
                    <label htmlFor="assessment-stage">Stage being evaluated</label>
                    <select id="assessment-stage" value={stage} onChange={(event) => setStage(event.target.value as DIStage)}>
                        {STAGES.map((item) => (
                            <option key={item.value} value={item.value}>
                                {item.label}
                            </option>
                        ))}
                    </select>
                    <label htmlFor="assessment-evidence">Accumulated evidence</label>
                    <textarea
                        id="assessment-evidence"
                        value={evidence}
                        onChange={(event) => setEvidence(event.target.value)}
                        placeholder="Describe the problem, users, expected value, data, technical approach, sponsor, delivery capacity, tests and measured results."
                        minLength={20}
                        maxLength={120000}
                        rows={14}
                        required
                    />
                    <div className="lab-form-footer">
                        <small>{evidence.length.toLocaleString()} characters</small>
                        <button type="submit" disabled={running}>
                            {running ? "Assessing evidence…" : "Run test assessment"}
                        </button>
                    </div>
                    {error ? <p className="signin-error">{error}</p> : null}
                </form>

                <section className="panel lab-result" aria-live="polite">
                    <div className="panel-heading">
                        <div>
                            <p className="eyebrow">Policy output</p>
                            <h3>Policy result</h3>
                        </div>
                    </div>
                    {result ? (
                        <>
                            <div className="lab-scoreline">
                                <div>
                                    <span>Overall score</span>
                                    <strong>{result.composite_score ?? "Incomplete"}</strong>
                                </div>
                                <div>
                                    <span>Gate outcome</span>
                                    <strong>{result.gate_outcome.replaceAll("_", " ")}</strong>
                                </div>
                                <div>
                                    <span>Stage</span>
                                    <strong>
                                        {result.current_stage}
                                        {result.recommended_next_stage ? ` → ${result.recommended_next_stage}` : ""}
                                    </strong>
                                </div>
                            </div>
                            <div className="lab-executive">
                                <span className="readout-label">Executive summary</span>
                                <p>{result.score_rationale || result.transition_rationale}</p>
                            </div>
                            <p className="lab-rationale">{result.transition_rationale}</p>
                            <div className="panel-heading">
                                <div>
                                    <p className="eyebrow">Transition readiness</p>
                                    <h3>Policy criteria</h3>
                                </div>
                            </div>
                            <div className="lab-dimensions">
                                {result.criteria
                                    .filter(
                                        (criterion) =>
                                            criterion.role === "ENTRY_CRITERION" ||
                                            criterion.state === "CONCERN" ||
                                            criterion.conditional_if_unresolved,
                                    )
                                    .map((criterion) => (
                                        <article key={criterion.criterion_id}>
                                            <div>
                                                <span>{criterion.title}</span>
                                                <strong>{criterion.state.replaceAll("_", " ")}</strong>
                                            </div>
                                            <p>{criterion.summary}</p>
                                            <small>{criterion.timing.replaceAll("_", " ")}</small>
                                        </article>
                                    ))}
                            </div>
                            <div className="panel-heading">
                                <div>
                                    <p className="eyebrow">Portfolio signal</p>
                                    <h3>Evidence dimensions</h3>
                                </div>
                            </div>
                            <div className="lab-dimensions">
                                {result.dimensions.map((dimension) => (
                                    <article key={dimension.dimension}>
                                        <div>
                                            <span>{dimension.dimension_label}</span>
                                            <strong>{dimension.value ?? dimension.state.replaceAll("_", " ")}</strong>
                                        </div>
                                        <p>{dimension.summary}</p>
                                        {dimension.gaps.length ? <small>Next evidence: {dimension.gaps[0]}</small> : null}
                                    </article>
                                ))}
                            </div>
                            <p className="lab-provenance">
                                Evaluator: {result.model_version} | Weight set: {result.weight_set_version} | Transition policy:{" "}
                                {result.transition_policy_version}
                            </p>
                        </>
                    ) : (
                        <div className="empty-state lab-empty">
                            <div className="empty-icon">01</div>
                            <h4>No result yet</h4>
                            <p>The model interprets evidence. Versioned policy keeps portfolio scoring separate from transition readiness.</p>
                        </div>
                    )}
                </section>
            </div>
        </section>
    );
}
