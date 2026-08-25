# Oliver Azure infrastructure

This Terraform is the production target for Oliver. Local development continues to use the local PostgreSQL instance and filesystem attachment store; no Azure resource is required to run the application locally.

## Production topology

Terraform provisions:

- Oliver API, read-only admin API, and admin SPA as independently deployable Azure Container Apps;
- a VNet-integrated Container Apps environment;
- private Azure Database for PostgreSQL Flexible Server, with public access disabled;
- a distinct read-only PostgreSQL role for the admin API;
- private Azure Blob storage for content-addressed attachment files, using workload identity rather than account keys;
- Microsoft Entra API and SPA registrations with role-based authorization;
- a Logic App with a dedicated managed identity and only `Oliver.Service.Email` authority;
- ACR, Key Vault, Log Analytics, Application Insights, migration jobs, and the Office 365 connection.

The API application defines user roles for read access, assessment tests, lifecycle approval, Scout review, and platform administration. It also defines separate application roles for email, scheduler, Scout, and metrics workloads. People are assigned through Entra security groups supplied in `admin_role_group_object_ids`; no employee name or email address belongs in Terraform or application code.

## Security boundaries

- The browser uses the authorization-code flow with PKCE through MSAL. It has no client secret.
- The admin API validates the Oliver API access token and remains database read-only.
- Admin commands are forwarded to the Oliver workflow API, where the same token and role are validated again.
- Logic App obtains a token through its user-assigned managed identity. The shared API key remains a localhost-only compatibility mechanism and is not used by the production workflow.
- PostgreSQL and attachment storage are network-restricted. Credentials that are still required are stored in Key Vault and referenced by Container Apps.
- Attachment payloads are stored once by SHA-256 content hash. PostgreSQL stores metadata, extracted evidence, and the durable blob URI rather than duplicate file bytes.

## Required inputs

Copy `terraform.tfvars.example` to an ignored `terraform.tfvars`, then supply:

- the shared mailbox address;
- the approved OpenAI-compatible provider base URL, response model, and embedding model;
- the model-provider API key through `TF_VAR_model_api_key`;
- Entra security-group object IDs for the roles needed in that environment.

Use separate groups for readers, assessment operators, lifecycle approvers, and platform administrators. A person can belong to more than one group. For the current project phase, assign the initial team only to `Oliver.Admin.Read` and `Oliver.Assessment.Test`; leave `Oliver.Lifecycle.Approve` unassigned until lifecycle decisions are enabled.

## Validate and deploy

```bash
cp backend.tf.example backend.tf
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan -out=oliver.tfplan
terraform apply oliver.tfplan
```

Production Terraform state must use an access-controlled remote Azure Storage backend because generated database credentials and other sensitive values are present in state. The migration job and database-access job are started by Terraform through Azure CLI, so deployment automation must provide Bash, Azure CLI, and permission to start and inspect Container Apps jobs.

## Post-deployment steps

1. Grant tenant-wide admin consent to the admin SPA's delegated `access_as_user` permission.
2. Authorize the Office 365 API connection interactively with an identity that can read and reply from the shared mailbox.
3. Assign approved Entra groups to the Oliver user roles.
4. Confirm the Logic App managed identity has the generated `Oliver.Service.Email` application-role assignment.
5. Run smoke tests for login, email ingestion, attachment extraction, assessment, delivery success/failure callbacks, and audit history before enabling the mailbox trigger for general use.

The Logic App includes attachment content in the inbound contract, calls Oliver with managed identity, replies only for `SEND_EMAIL`, and reports `SENT` or `FAILED` back to Herald using an idempotency key. This gives the dashboard an auditable delivery state rather than assuming that generating an email means it was delivered.
