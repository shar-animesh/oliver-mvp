# Oliver

Oliver is one tool-using agent governed by one system prompt. The FastAPI email endpoint stores complete conversations, retrieves related internal initiatives from PostgreSQL, and returns either a branded email response or a no-reply instruction.

## Runtime flow

1. `POST /api/v1/email/respond` persists the inbound message and reconstructs its complete thread.
2. Oliver creates a 1,536-dimensional `openai/text-embedding-3-small` vector by default and stores it in a native PostgreSQL array.
3. Oliver calculates cosine distance and retrieves a bounded set of similar conversations belonging to other internal participants.
4. Oliver receives the current thread plus bounded, de-identified context from related conversations and may identify a relevant internal pattern.
5. The model returns parsed `OliverResponse` JSON. The endpoint wraps `SEND_EMAIL` content in the branded shell, records the run and semantic matches, and returns it to the Logic App. `NO_REPLY` records the decision without sending mail.

```python
from utils.models import OliverResponse
from utils.prompts import build_system_prompt
from utils.templates import render_oliver_email

messages = [
    {
        "role": "system",
        "content": build_system_prompt(email_thread),
    }
]

raw_response = model.complete(messages, tools=runtime_tools)
response = OliverResponse.model_validate_json(raw_response)

if response.action == "SEND_EMAIL":
    email_html = render_oliver_email(
        subject=response.subject,
        content_html=response.content_html,
    )
```

## Final response

Oliver always returns one valid JSON object:

```json
{
    "action": "SEND_EMAIL",
    "subject": "Re: AI initiative proposal",
    "content_html": "<h1>Initiative Name: Initiative Assessment</h1><p>...</p>"
}
```

Allowed actions are:

- `SEND_EMAIL`: the host may render and send the generated subject and content.
- `NO_REPLY`: no email is needed; subject and content are null.

The response model defines only the structured fields and allowed actions. The system prompt is responsible for the generated HTML rules. The branded shell applies all typography, colors, spacing, list styling, and table styling.

## Behavior

Oliver handles the latest inbound message according to its actual intent rather than forcing every email through an assessment:

- ordinary and follow-up questions receive concise conversational answers;
- missing material information produces a focused information request;
- sufficiently detailed AI initiatives receive a holistic, evidence-led assessment;
- existing initiatives receive lifecycle, monitoring, value, risk, or next-step guidance as appropriate;
- consequential or insufficiently authorized actions are not performed; Oliver sends an email identifying the decision or authorization needed.

The system prompt defines proactive tool use, source and instruction boundaries, prompt-injection resistance, authorization requirements, inline web citations, assessment considerations, report composition, and Outlook/Gmail-safe fragment requirements.

## Rendering

`build_system_prompt` accepts one plain Python string and inserts it into a delimited `<email_thread>` element. The email thread is treated as untrusted content.

```python
from utils.prompts import build_system_prompt

system_prompt = build_system_prompt(email_thread)
```

`render_oliver_email` sanitizes the model-generated fragment with a strict Bleach tag, attribute, and protocol allowlist before inserting it into an autoescaped `.jinja2.html` shell. The subject and preheader remain escaped. The official white Siemens Energy logo is packaged locally and embedded into each rendered email as a base64 PNG data URI, so rendering does not request an external image.

All model prompts live in `utils/prompts`. The loader exposes named functions for the Coach, Assessment, Portfolio, and Scout instructions, so prompt changes do not require editing agent code.

```python
from utils.templates import render_oliver_email

email_html = render_oliver_email(
    subject=response.subject,
    content_html=response.content_html,
)
```

The shell fixes only the brand frame: the official logo, dark-purple/violet color treatment, header, footer, 660px email container, and Gmail/Outlook-safe outer tables. Oliver owns every useful content section inside it.

## Development

The application uses uv for dependency management and local commands:

```bash
uv lock
uv sync
uv run ruff check .
uv run ruff format --check .
```

## Local PostgreSQL

Create a PostgreSQL database named `oliver`, copy `.env.example` to `.env`, and set `DATABASE_URL` with your local credentials:

```text
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/oliver
```

Apply the schema from this directory:

```bash
uv sync
uv run alembic upgrade head
```

The schema uses native PostgreSQL `double precision[]` values for embeddings, so a local `pgvector` extension is not required. Cosine similarity is calculated in the Oliver process, which keeps local setup simple and is appropriate for the MVP dataset size.

New conversations are indexed as Oliver processes them, and cross-team contact discovery is limited to Siemens Energy email addresses.
