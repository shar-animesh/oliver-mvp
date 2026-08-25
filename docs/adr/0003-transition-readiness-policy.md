# ADR 0003: Transition readiness is not a portfolio score

## Status

Accepted for implementation on 2026-08-24.

## Decision

Oliver will keep numeric dimension and composite scores as secondary portfolio
signals. A composite threshold will no longer decide lifecycle movement.
When the evidence is insufficient to judge a dimension, its state is `UNKNOWN`
and its numeric value is null; missing evidence is not represented as a very low
quality score. A composite is calculated only when all five dimensions have
assessable numeric values.

The authoritative lifecycle recommendation is produced by a versioned stage
transition policy over criterion findings with these evidence states:

- `SATISFIED`
- `CONCERN`
- `UNKNOWN`
- `NOT_APPLICABLE`

Each policy records the current-stage objective and next-stage objective.
Criteria have a functional role (`ENTRY_CRITERION`, `NEXT_STAGE_EXPECTATION`,
or `BLOCKING_CONDITION`) and timing (`REQUIRED_BEFORE_ENTRY`,
`REQUIRED_DURING_STAGE`, or `ADVISORY`). The deterministic policy produces
exactly one forward-transition recommendation:

- `ADVANCE`
- `CONDITIONAL_ADVANCE`
- `HOLD_FOR_EVIDENCE`
- `DO_NOT_ADVANCE`

DI5 is not a forward transition. Its separate terminal assessment outcome is
`CONTINUE_MONITORING`; it cannot create a next stage or silently trigger retire,
rollback, or No-Go.

The Assessment Agent may interpret supplied evidence against approved criteria.
It cannot create criteria, change their timing, decide whether they block, or
move lifecycle state. StageMaster consumes the deterministic transition
evaluation.

## Evidence and policy sources

The initial DI1 to DI2 policy asks whether the idea is sufficiently credible,
bounded, and safe to justify a controlled pilot. Its approved entry criteria
cover a validated problem, plausible solution hypothesis, initial evidence,
bounded pilot scope, accountable owner, and acceptable experimentation risk.
DI2 is expected to produce realistic performance, integration, value, adoption,
monitoring, and scalability evidence; absence of that evidence at DI1 is not an
entry failure.

The initial policy uses only:

- `docs/01-Oliver-Planning(2).html`, sections describing DI1 Concept, DI2 Pilot,
  evidence-mandatory assessment, and human confirmation of No-Go decisions;
- `docs/04-Oliver-Lifecycle-Restructure-Plan.html#s8`, which defines the official
  stage meanings and movement authority;
- the project-owner-approved benchmark decision that incomplete production
  integration, cybersecurity, and data-governance work may be conditions of a
  controlled DI2 pilot rather than automatic evidence against entering DI2.

On 2026-08-24 the project owner authorized implementation of the remaining
document-backed lifecycle policy. Version `transition-policy/1.1.0` adds DI2 to
DI3, DI3 to DI4, DI4 to DI5, and terminal DI5 monitoring. It uses qualitative
evidence states only because numeric score and confidence thresholds remain an
explicitly open governance decision in the approved architecture. DI4 to DI5 is
always routed for human approval.

## Gate semantics

For an available transition policy:

1. A `CONCERN` on a blocking `REQUIRED_BEFORE_ENTRY` criterion produces
   `DO_NOT_ADVANCE` and human review.
2. An `UNKNOWN` blocking entry criterion produces `HOLD_FOR_EVIDENCE`.
3. Once all entry criteria are satisfied, only an unresolved next-stage
   condition explicitly marked `conditional_if_unresolved` produces
   `CONDITIONAL_ADVANCE`. Ordinary evidence that DI2 exists to produce does not
   block or condition DI1 exit.
4. When all applicable required criteria are satisfied, the result is `ADVANCE`.
5. Advisory criteria never block movement.
6. DI5 entry, No-Go, retire, override, and low-confidence exceptions remain
   human decisions.
7. Once in DI5, Oliver evaluates operational health, controls, ownership, drift,
   incidents, and realized value as monitoring evidence. It never produces a
   fictitious path beyond DI5.

## Response policy

Response depth is deterministic:

- any unknown entry criterion: `BRIEF`;
- known entry criteria with unresolved during-stage conditions: `STANDARD`;
- all applicable entry criteria resolved: `DETAILED`, unless an approved
  conditional entry control remains open, in which case `STANDARD` applies.

Model-generated timelines, thresholds, owners, and organizational requirements
are not policy. A mandatory recommendation must reference an approved criterion;
otherwise it is advisory and must be phrased conditionally.

## Consequences

- Evidence quality, transition readiness, and portfolio score become separate
  concepts.
- A sparse submission is held for evidence rather than scored as a bad idea.
- Actual negative evidence can produce a governed Do-Not-Advance recommendation.
- The same evidence must produce the same gate outcome regardless of management
  pressure in the email.
- Adding later-stage criteria is a policy-data change with review and regression
  tests, not a prompt edit.
