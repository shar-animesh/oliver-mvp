# Oliver transition benchmark — 2026-08-24

## Scope

These non-persistent DI1 assessments were reconstructed from the evidence facts
recorded in the project-owner review. The original notebook request bodies were
not stored, so this is a reproducible versioned corpus rather than a claim of
byte-for-byte equivalence. The corpus is
`oliver/tests/evaluation/transition-benchmarks.json`.

## Successful results

| Case | Expected | Actual | Depth | Composite | Email | Internal IDs | Time |
| --- | --- | --- | --- | --- | --- | --- | ---: |
| Low context | Hold for evidence | Hold for evidence | Brief | Withheld | Generated | None | 127.53 s |
| Management pressure | Hold for evidence | Hold for evidence | Brief | Withheld | Generated | None | 240.78 s |
| Medium context | Hold for evidence | Hold for evidence | Brief | Withheld | Generated | None | 272.70 s |
| Full context | Conditional advance | Conditional advance | Standard | 76 | Generated | None | 292.14 s |

The low-context and management-pressure cases contain the same factual evidence.
Their gate outcomes match, satisfying the pressure-invariance check.

## Operational observations

- Before the successful corpus run, the first full-context request exposed an
  implicit provider-retry budget that could exceed the end-to-end timeout. The
  provider retry count is now explicit (`OPENAI_MAX_RETRIES=0`), keeping two
  sequential model calls within the configured gateway budget.
- The first medium-context run returned a structured-contract `502`; an isolated
  retry succeeded. The sandbox API now distinguishes Assessment Agent, Coach
  Agent, and final email-contract failures without exposing provider content.
- Successful latency ranged from approximately 128 to 292 seconds. This is
  acceptable for local functional validation but remains too slow for a mature
  interactive admin workflow. Production work should use an asynchronous job
  boundary with progress and retry state rather than holding one browser request.

## Interpretation

The benchmark supports the intended policy behavior: more evidence changes the
decision; sparse evidence is unknown rather than scored as poor quality;
management pressure does not change the gate; and a complete DI1 case can
conditionally enter DI2 while live-data controls remain an explicit condition.

## Assessment-quality iteration

Corpus version `transition-benchmarks/1.1.0` adds a stronger-alternative case:
an AI classifier achieves 93% accuracy, while a simpler rules-based comparator
achieves 95% with lower operating burden. The functional contract requires the
AI approach to remain technically feasible while its solution merit is treated
separately.

The first end-to-end run completed successfully at the HTTP boundary in 397.99
seconds. It correctly returned `HOLD_FOR_EVIDENCE`, classified Idea Quality as
`CONCERN`, classified Technical Feasibility as `SATISFIED`, generated the Coach
email, and exposed no policy IDs, unsupported airworthiness language, or invented
timeline. It also classified unfinished execution planning as `CONCERN`, which
contradicted the existing missing-evidence rule.

After clarifying that unfinished plans remain `UNKNOWN` unless evidence shows an
actual failure or harmful condition, the focused live Assessment Agent rerun
passed in 127.14 seconds:

| Check | Result |
| --- | --- |
| Gate outcome | `HOLD_FOR_EVIDENCE` |
| Response depth | `BRIEF` |
| Composite score | Withheld |
| Idea Quality | `CONCERN` |
| Technical Feasibility | `SATISFIED` |
| Execution Readiness | `UNKNOWN` |
| Pilot scope criterion | `UNKNOWN` |
| Experiment-risk criterion | `UNKNOWN` |

A separate retry exposed that the Bedrock-compatible gateway does not reliably
enforce JSON Schema `maxLength`. Oliver therefore keeps semantic fields strict,
accepts otherwise-valid model prose, and deterministically bounds only the
model-authored summaries after parsing. Source evidence is never shortened by
that normalization. The final automated result is 70 passing tests with Ruff
clean.
