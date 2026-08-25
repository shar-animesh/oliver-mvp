# Oliver architecture and runtime responsibilities

This document describes the implementation under `oliver/`. The transition-readiness design decision is recorded in [ADR 0003](adr/0003-transition-readiness-policy.md), and the evidence-quality contract is recorded in [ADR 0004](adr/0004-assessment-evidence-quality-contract.md).

## Architectural rule

Oliver separates model reasoning from authoritative lifecycle control:

```text
Model reasoning                    Deterministic application control
------------------------------     ---------------------------------
Interpret supplied evidence        Persist initiatives and evidence
Classify criterion evidence        Calculate canonical portfolio score
Explain and coach                  Apply versioned transition policy
Find portfolio patterns            Enforce authorization and concurrency
Discover Scout candidates          Record audit and delivery state
```

The model does not assign an official score or move an initiative between DI stages. Numeric score, transition readiness, and lifecycle state are separate outputs.

## Inbound assessment flow

```text
Logic App or assessment sandbox
            |
            v
Authenticated FastAPI route
            |
            v
Registrar: thread, message, initiative, attachments, evidence version
            |
            v
Assessment Agent: structured evidence and criterion findings
            |
            +-----------------------------+
            |                             |
            v                             v
Canonical Scoring Service          Transition Policy Engine
(portfolio comparison signal)      (stage-specific readiness)
            |                             |
            +--------------+--------------+
                           v
                Canonical assessment record
                           |
                           v
               Coach Agent and safe renderer
                           |
                           v
                Herald delivery outbox/audit
```

For each stage transition, the policy engine evaluates explicit criteria as `SATISFIED`, `CONCERN`, `UNKNOWN`, or `NOT_APPLICABLE`. It produces `ADVANCE`, `CONDITIONAL_ADVANCE`, `HOLD_FOR_EVIDENCE`, `DO_NOT_ADVANCE`, or the terminal `CONTINUE_MONITORING` outcome. A weighted score remains useful for portfolio comparison but is not a stage gate.

## Reasoning agents

- **Assessment Agent** interprets the current message, accumulated initiative evidence, attachment text, stage objective, and transition policy. Its response is schema-validated before use. A deterministic rubric implementation remains available through the same interface.
- **Coach Agent** converts canonical assessment and transition results into participant-facing communication. The branded email renderer owns official scores and policy results, strips internal criterion identifiers, and sanitizes free-form model HTML.
- **Portfolio Intelligence Agent** analyzes persisted initiative summaries for cross-portfolio patterns. Reports are stored with an input fingerprint so identical portfolio state is not duplicated.
- **Scout Agent** proposes candidate initiatives from approved source material. Promotion and dismissal are explicit governed workflows; Scout does not silently create lifecycle decisions.

## Deterministic services

- **Registrar** owns initiative/thread association, immutable evidence versions, attachment provenance, and idempotent inbound storage.
- **Canonical Scoring Service** calculates versioned dimension scores as portfolio signals.
- **Transition Policy Engine** owns stage objectives, criterion timing, blocking behavior, gate outcomes, and report depth.
- **Lifecycle Service / StageMaster responsibility** applies authorized hold, resume, proposal, approval, rejection, and transition operations with optimistic concurrency checks.
- **Pacer** calculates stage age and creates follow-up events from configured service-level intervals.
- **Herald** owns the transactional delivery outbox, delivery attempts, retries, and Logic App receipts without duplicating the outbound email body.
- **Auditor** appends actor, subject, correlation, and policy provenance for material lifecycle events.
- **Sentinel and Realizer** ingest governed operational measurements, detect deterministic SLO breaches, and compare realized value with approved targets.

## Persistence and privacy

PostgreSQL is the canonical store. Local PostgreSQL is used for development; Azure Database for PostgreSQL Flexible Server is the production target. Alembic owns schema evolution.

Evidence snapshots reference evidence items within the same initiative through composite foreign keys. Related-idea semantic search excludes participant identity, returns bounded participant-authored context, and only searches initiatives explicitly marked `INTERNAL`; initiatives are `PRIVATE` by default.

## Authentication boundaries

Local username/password sessions and internal API keys exist only for development. Production configuration fails closed unless Microsoft Entra validation is enabled. Entra app roles separate administrative reading, assessment testing, lifecycle approval, insight operation, and Scout review. Logic App and metrics ingestion use service identity rather than dashboard user sessions.

## Deployment boundaries

The backend, admin API, frontend, PostgreSQL, storage, Logic App, and migration/database-access jobs are deployed independently. Containers run as an unprivileged user. Logic App run history protects email and attachment inputs/outputs, and delivery success or failure is reported to Herald.

The administrator dashboard is a read-oriented operational surface. It reads canonical records and sends authorized commands to Oliver; it does not own lifecycle tables or migrations.
