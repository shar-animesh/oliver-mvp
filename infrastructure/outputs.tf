output "resource_group_name" {
  description = "Resource group containing Oliver."
  value       = azurerm_resource_group.oliver.name
}

output "container_registry_name" {
  description = "Registry used to build and store the Oliver API image."
  value       = azurerm_container_registry.oliver.name
}

output "container_image" {
  description = "Oliver image reference expected by its Container App."
  value       = "${azurerm_container_registry.oliver.login_server}/oliver:${var.oliver_image_tag}"
}

output "oliver_api_url" {
  description = "Email-response endpoint called by the Logic App."
  value       = local.oliver_api_url
}

output "oliver_health_url" {
  description = "Unauthenticated process-health endpoint."
  value       = "https://${azurerm_container_app.oliver.ingress[0].fqdn}/health"
}

output "admin_dashboard_url" {
  description = "Public URL for the admin dashboard frontend."
  value       = "https://${azurerm_container_app.admin_frontend.ingress[0].fqdn}"
}

output "admin_backend_internal_fqdn" {
  description = "Environment-internal admin backend FQDN used by the frontend proxy."
  value       = azurerm_container_app.admin_backend.ingress[0].fqdn
}

output "postgres_server_fqdn" {
  description = "Private Azure Database for PostgreSQL Flexible Server hostname."
  value       = azurerm_postgresql_flexible_server.oliver.fqdn
}

output "postgres_database_name" {
  description = "Oliver PostgreSQL database name."
  value       = azurerm_postgresql_flexible_server_database.oliver.name
}

output "oliver_api_client_id" {
  description = "Microsoft Entra application client ID used as Oliver's token audience."
  value       = azuread_application.oliver_api.client_id
}

output "oliver_api_scope" {
  description = "Delegated scope requested by the admin dashboard SPA."
  value       = "${one(azuread_application.oliver_api.identifier_uris)}/access_as_user"
}

output "admin_dashboard_spa_client_id" {
  description = "Public Entra SPA client ID embedded in the admin frontend build."
  value       = azuread_application.admin_dashboard.client_id
}

output "database_migration_job_name" {
  description = "Container Apps job that applies the Oliver Alembic migration."
  value       = azurerm_container_app_job.database_migrations.name
}

output "database_access_job_name" {
  description = "Container Apps job that provisions the admin dashboard read-only PostgreSQL role."
  value       = azurerm_container_app_job.database_access.name
}

output "logic_app_name" {
  description = "Logic App workflow that receives and replies to Oliver email."
  value       = azapi_resource.email_workflow.name
}

output "office365_connection_resource_id" {
  description = "Office 365 connection that must be authorized once after deployment."
  value       = azurerm_api_connection.office365.id
}

output "key_vault_name" {
  description = "Key Vault containing Oliver runtime secrets."
  value       = azurerm_key_vault.oliver.name
}
