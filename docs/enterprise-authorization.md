# Oliver enterprise authorization model

Oliver authorizes capabilities, not named people. Personal names and email addresses must never be embedded in application code, Terraform role checks, or production environment variables.

## Identity boundaries

| Caller | Authentication | Authorization |
|---|---|---|
| Admin dashboard user | Microsoft Entra access token | App roles assigned to Entra security groups |
| Email Logic App | User-assigned managed identity | `Oliver.Service.Email` app role |
| Scheduled Pacer job | Managed identity | `Oliver.Service.Scheduler` app role |
| Local developer | Signed local session or internal API key | Local `.env` allowlist only; prohibited in production |

Managed identity does not authenticate a human dashboard user. It identifies an Azure workload. Interactive users authenticate through Entra and receive role claims in an access token issued for the Oliver API.

## Application roles

| App role | Capability |
|---|---|
| `Oliver.Admin.Read` | View initiatives, assessments, evidence metadata, delivery status and audit history |
| `Oliver.Assessment.Test` | Run non-persistent or explicitly sandboxed assessments |
| `Oliver.Lifecycle.Approve` | Hold/resume and approve or reject governed lifecycle proposals |
| `Oliver.Scout.Review` | Promote or dismiss candidates found by Scout |
| `Oliver.Platform.Admin` | Administrative break-glass role; includes all Oliver administrative capabilities |
| `Oliver.Service.Email` | Submit inbound mail, poll the delivery outbox and report delivery outcomes |
| `Oliver.Service.Scheduler` | Run Pacer and other approved scheduled evaluations |
| `Oliver.Service.Scout` | Submit records from an explicitly approved discovery connector |
| `Oliver.Service.Metrics` | Submit idempotent operational and realized-value measurements |

Create Entra security groups for the human roles and assign groups to the enterprise application's app roles. Add or remove people in Entra. Oliver consumes only the resulting `roles` claim and immutable Entra object ID (`oid`).

## Production controls

1. Register one API application for the Oliver resource audience and expose a delegated SPA scope.
2. Register the dashboard SPA with authorization-code flow and PKCE; do not create a browser client secret.
3. Define the roles above on the Oliver API application.
4. Assign Entra groups to human roles and managed identities/service principals to workload roles.
5. Configure both APIs with tenant ID and Oliver API audience/client ID.
6. Set `ADMIN_AUTH_MODE=entra` and `SERVICE_AUTH_MODE=entra` in Azure.
7. Keep local password hashes, local identity allowlists and shared API keys out of production settings.
8. Verify issuer, audience, signature, expiry and role claims on every protected API request. CORS remains a browser control, never an authorization mechanism.

## Scaling beyond the initial team

Adding a reviewer, business unit or operations team requires only group membership or a new role-to-group assignment. It does not require a code change, deployment or database update. Audit records store the immutable Entra object ID and display identity that made the decision, preserving traceability if a person's email or display name later changes.
