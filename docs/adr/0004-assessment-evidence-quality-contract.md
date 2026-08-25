# ADR 0004: Assessment dimensions preserve evidence meaning

## Status

Accepted for implementation on 2026-08-24.

## Context

Oliver already separates model interpretation from deterministic score weighting
and stage-transition policy. Functional testing identified one remaining semantic
risk: the same comparative fact could be treated as adverse evidence in several
dimensions without distinguishing what it actually proves.

For example, an AI classifier can be technically feasible while still being a
weaker solution choice than a more accurate, cheaper rules-based comparator.
Treating comparator superiority as technical infeasibility confuses three
different questions:

- Can the proposed approach technically operate?
- Is it the most coherent solution to the problem?
- Does it create enough incremental value to justify its operating burden?

The model contract also described `UNKNOWN` as having no numeric value, but that
relationship was not enforced by schema validation.

## Decision

Oliver will apply the following evidence boundaries:

| Dimension | Primary question | Stronger alternative affects it when |
| --- | --- | --- |
| Idea Quality | Is the problem-solution choice coherent and differentiated? | The alternative weakens solution fit or makes the stated rationale incoherent. |
| Strategic / Business Value | Is there evidenced incremental value relative to cost and burden? | The alternative delivers more value or materially lower operating burden. |
| Technical Feasibility | Can the proposed method operate at the required technical level? | Evidence shows inadequate technical performance, unsuitable data, infeasible integration, or another actual technical constraint. |

A stronger alternative does not, by itself, prove technical infeasibility.
Missing integration, deployment, ownership, cost, or validation information is
a gap. It becomes `UNKNOWN` where there is not enough evidence to judge; it does
not become `CONCERN` without affirmative adverse evidence.

Mixed evidence is not reduced to an artificial benchmark verdict. For example,
a quantified operational problem can support strategic value while comparative
operating burden weakens the AI-specific value case. The benchmark asserts only
the unambiguous functional boundaries and leaves the exact mixed-evidence state
to the documented interpretation and its supporting rationale.

The structured Assessment Agent contract will reject these invalid pairs:

- `UNKNOWN` or `NOT_APPLICABLE` with a numeric value;
- `SATISFIED` or `CONCERN` without a numeric value.

The existing deterministic policy remains authoritative for lifecycle outcomes.
No dimension score, including technical feasibility, directly moves a stage.

## Evaluation policy

The versioned non-persistent benchmark corpus contains:

- full, medium, and sparse evidence;
- equivalent sparse evidence with management pressure;
- a technically working AI approach that is inferior to a simpler comparator.

Benchmark assertions cover gate outcome, response depth, composite availability,
selected dimension and criterion states, policy-ID leakage, unsupported domain
language, unsupported timelines, and evidence-equivalent pressure invariance.
Exact prose and exact numeric scores are intentionally not asserted because they
are not stable functional contracts.

## Non-goals

This decision does not change stage policy, scoring weights, database schemas,
stored assessments, authentication, or lifecycle authority. It does not attempt
to solve model latency; an asynchronous production assessment boundary remains
a separate architectural concern.
