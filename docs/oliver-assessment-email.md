# Oliver assessment email: rich stage-gate report

This note documents the change that makes Oliver produce the branded stage-gate
assessment email (score header, colored sections, dimension score-breakdown table,
next steps, resubmission note) instead of a plain HTML fragment.

## Design

The scores are deterministic; the prose is model-generated; the styling is owned by a
template. The split keeps the numbers correct and the brand consistent.

- **Canonical scoring (deterministic)** — `oliver/utils/scoring/` computes the composite
  score, DI stage, gate outcome, rating, and the five per-dimension scores/weights for
  every assessable inbound email. Unchanged by this work.
- **Model prose (structured)** — the model returns an `OliverResponse`. For a detailed
  initiative assessment it fills a typed `report` (`AssessmentReport`) with plain-text
  sections only. It never emits the score numbers, HTML, or styling.
- **Template rendering (deterministic styling)** — a Jinja template renders the branded
  email: the score header and the dimension breakdown table come from the canonical
  assessment; the section bands, badges, and layout wrap the model's prose.

## Response shapes (`OliverResponse`)

`oliver/utils/models/prompts.py` now returns one of three shapes, enforced by a validator:

- `action=SEND_EMAIL, reply_kind=assessment` → `subject` + `report` (rich stage-gate
  email). Used only when a canonical assessment exists and the thread is a detailed
  initiative evaluation.
- `action=SEND_EMAIL, reply_kind=message` → `subject` + `content_html` (conversational
  reply, information request, or lifecycle note, delivered in the existing branded shell).
- `action=NO_REPLY` → everything else null.

`AssessmentReport` fields: `position_note`, `executive_summary`, `working_well[]`,
`coaching_recommendations[]` (`title`, `detail`, optional `example`), `approach_guidance`
(`problem_type`, `recommended_approach`, `what_to_do_first`), `opportunities[]` (`area`,
`priority` High/Medium/Low, `suggestion`), `path_forward` (`timeline`, `milestones[]`),
`next_steps[]` (`action`, `owner`, `timeline`), `closing_note`.

## Files changed

- `oliver/utils/models/prompts.py` — new structured schema (`AssessmentReport` and the
  nested item models) and the three-shape validator.
- `oliver/utils/models/__init__.py` — export the new models.
- `oliver/utils/templates/oliver-assessment.jinja2.html` — new email-safe template
  (table + inline styles) for the stage-gate report.
- `oliver/utils/templates/loader.py` — `render_assessment_email(subject, report,
  assessment)`; prepares stage names, the next gate label, priority badge colors, the
  dimension rows, and the weight-set note.
- `oliver/utils/templates/__init__.py` — export `render_assessment_email`.
- `oliver/utils/prompts/system-prompt.jinja2` — the output-format sections now describe
  the response shapes and the report fields; the message HTML rules are retained for
  `reply_kind=message`. All security, evidence-discipline, and coaching-voice guidance is
  preserved.
- `oliver/routes/email.py` — renders the assessment email when
  `reply_kind=assessment` and a canonical assessment exists; otherwise renders the plain
  shell. The canonical assessment is persisted only for an assessment reply.

Stage display names are a UI label only (`DI1 Concept, DI2 Pilot, DI3 Prototype,
DI4 Deploy, DI5 Operate`); the stage code, scores, and gate outcome remain canonical.

## Verification

- `ruff check` and `ruff format --check`: pass on all changed files. `py_compile`: passes.
- Deterministic render: the template was rendered with a sample report plus a real
  canonical assessment and reviewed in a browser against the reference screenshots in the
  repository root; the layout matches (score header, green/amber bands, badges, breakdown
  table with the violet weighted-total row, next-steps card, resubmission note).
- Live model: one call to the configured `bedrock/us.anthropic.claude-sonnet-4-6` endpoint
  returned `reply_kind=assessment` with a complete, evidence-disciplined report that
  rendered correctly, with the score header and breakdown table taken from the canonical
  engine (composite 48, DI1, Early).
- Not run: `pytest tests/test_scoring.py` (pytest is not installed in the local venv).

## Notes / follow-ups

- `current_stage` determines the assessed DI stage. DI1 is used only when the caller omits
  a stage.
- A conversational `SEND_EMAIL` reply is not scored; only an assessment reply persists a
  canonical assessment.
