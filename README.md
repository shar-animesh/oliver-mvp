# Oliver MVP

Oliver is a single-agent email assistant for Siemens Energy AI initiatives. It receives shared-mailbox messages through an Azure Logic App, stores full conversations in PostgreSQL, retrieves related initiatives across internal teams, and returns either a branded HTML reply or a no-reply instruction.

## Repository

- `oliver/`: independently deployable FastAPI API, system prompt, email shell, SQLAlchemy schema, and Alembic migrations.
- `admin-dashboard/backend/`: read-only FastAPI API for stored Oliver conversations and semantic matches.
- `admin-dashboard/frontend/`: React and Vite interface for browsing conversations.
- `infrastructure/`: production Azure deployment Terraform for Container Apps, PostgreSQL, Blob Storage, Key Vault, Entra authentication, and the Logic App workflow.
- `docs/`: historical planning and delivery records.

## Run locally on a Windows workstation

### Prerequisites

Install the following approved tools before cloning the repository:

- Git;
- Python 3.12;
- [uv](https://docs.astral.sh/uv/getting-started/installation/);
- Node.js 22 with npm;
- PostgreSQL 16, including either `psql`/`createdb` or pgAdmin.

Docker and Terraform are not required for the local manual workflow below.

### 1. Clone the repository

```powershell
git clone https://github.com/shar-animesh/oliver-mvp.git
Set-Location oliver-mvp
```

### 2. Create the local database

Create an empty PostgreSQL database named `oliver`. With the PostgreSQL command-line tools:

```powershell
createdb --username postgres oliver
```

You can create the same database through pgAdmin if `createdb` is unavailable. The application stores embeddings in native PostgreSQL arrays, so pgvector is not required.

### 3. Configure and migrate the Oliver API

```powershell
Set-Location oliver
Copy-Item .env.example .env
uv sync --frozen
```

Open `oliver/.env` and replace every required placeholder. For the simplest local setup, the database value is:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/oliver
ADMIN_AUTH_MODE=local
SERVICE_AUTH_MODE=local_key
ADMIN_IDENTITIES=local-admin
```

Set `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, and the embedding settings for the approved model provider. Generate two different long random values for `INTERNAL_API_KEY` and `ADMIN_GATEWAY_API_KEY`. Do not commit `.env`.

Apply all database migrations:

```powershell
uv run alembic upgrade head
Set-Location ..
```

### 4. Configure the admin API

```powershell
Set-Location admin-dashboard\backend
Copy-Item .env.template .env
uv sync --frozen
```

Set these local values in `admin-dashboard/backend/.env`:

```dotenv
ENV=development
ADMIN_AUTH_MODE=local
OLIVER_API_URL=http://localhost:8001
OLIVER_CORS_ORIGINS=http://localhost:5173
DATABASE_URL=postgresql+psycopg://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/oliver
```

Set `OLIVER_INTERNAL_API_KEY` to exactly the same value as `ADMIN_GATEWAY_API_KEY` in `oliver/.env`. The shared value authenticates only the local admin API when it forwards a command to Oliver.

Generate a local password hash for the `local-admin` login:

```powershell
@'
import base64
import getpass
import hashlib
import secrets

password = getpass.getpass("Local admin password: ")
salt = secrets.token_bytes(16)
iterations = 600_000
encoded_salt = base64.urlsafe_b64encode(salt).decode().rstrip("=")
encoded_hash = base64.urlsafe_b64encode(
    hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
).decode().rstrip("=")
print(f"local-admin:pbkdf2_sha256${iterations}${encoded_salt}${encoded_hash}")
'@ | uv run python -
```

Copy the printed value into `ADMIN_LOCAL_USER_HASHES`. Also replace `ADMIN_SESSION_SECRET` with a separate random value of at least 32 characters.

```powershell
Set-Location ..\..
```

### 5. Install the frontend

```powershell
Set-Location admin-dashboard\frontend
Copy-Item .env.template .env
npm ci
Set-Location ..\..
```

For local development, the frontend environment should retain `VITE_ADMIN_API_URL=/api` and `VITE_ADMIN_AUTH_MODE=local`.

### 6. Start all three services

Open three PowerShell terminals in the cloned repository.

Terminal 1 — Oliver API on port 8001:

```powershell
Set-Location oliver
uv run uvicorn main:app --reload --host 127.0.0.1 --port 8001
```

Terminal 2 — admin API on port 8000:

```powershell
Set-Location admin-dashboard\backend
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 3 — frontend on port 5173:

```powershell
Set-Location admin-dashboard\frontend
npm run dev
```

Open <http://localhost:5173> and sign in as `local-admin` with the password used to generate the hash. Health endpoints are available at <http://localhost:8001/health> and <http://localhost:8000/health>.

### 7. Run the verification suite

```powershell
Push-Location oliver
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
Pop-Location

Push-Location admin-dashboard\backend
uv run ruff check app
uv run ruff format --check app
Pop-Location

npm --prefix admin-dashboard/frontend run lint
npm --prefix admin-dashboard/frontend run typecheck
npm --prefix admin-dashboard/frontend run build
```

If startup reports an unknown environment setting, recreate the affected `.env` from its current template and reapply only the required local values. If admin commands return `403`, verify that `OLIVER_INTERNAL_API_KEY` and Oliver's `ADMIN_GATEWAY_API_KEY` are identical.

## Runtime flow

```text
Microsoft 365 shared mailbox
    -> Azure Logic App
    -> POST /api/v1/email/respond with the Logic App managed identity
    -> PostgreSQL conversation storage and vector retrieval
    -> OpenAI embedding and response models
    -> Logic App replies in the same email conversation
```

Oliver stores every inbound and outbound message. Each thread also stores a readable transcript and a 1,536-dimensional embedding. Before responding, Oliver ranks other internal threads using cosine distance. Relevant complete transcripts and contact details are supplied to Oliver, which may suggest a useful internal introduction without treating similarity as proof that two initiatives are duplicates.

## Local checks

```bash
cd oliver
uv sync
uv run ruff check .

cd ../admin-dashboard/backend
uv sync
uv run ruff check app

cd ../frontend
npm install
npm run typecheck
npm run build

cd ../../infrastructure
terraform init
terraform validate
```

See `infrastructure/README.md` for Azure prerequisites and deployment steps.
