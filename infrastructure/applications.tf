locals {
  oliver_name         = "ca-${local.name_prefix}-oliver"
  admin_backend_name  = "ca-${local.name_prefix}-admin-api"
  admin_frontend_name = "ca-${local.name_prefix}-admin-web"

  admin_frontend_origin = "https://${local.admin_frontend_name}.${azurerm_container_app_environment.oliver.default_domain}"
}

resource "azurerm_container_app" "oliver" {
  name                         = local.oliver_name
  resource_group_name          = azurerm_resource_group.oliver.name
  container_app_environment_id = azurerm_container_app_environment.oliver.id
  revision_mode                = "Single"
  tags                         = local.common_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.workloads.id]
  }

  registry {
    server   = azurerm_container_registry.oliver.login_server
    identity = azurerm_user_assigned_identity.workloads.id
  }

  secret {
    name                = "model-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.model_api_key.versionless_id
    identity            = azurerm_user_assigned_identity.workloads.id
  }

  secret {
    name                = "internal-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.internal_api_key.versionless_id
    identity            = azurerm_user_assigned_identity.workloads.id
  }

  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.oliver_database_url.versionless_id
    identity            = azurerm_user_assigned_identity.workloads.id
  }

  template {
    min_replicas = var.container_min_replicas
    max_replicas = var.container_max_replicas

    container {
      name   = "oliver"
      image  = "${azurerm_container_registry.oliver.login_server}/oliver:${var.oliver_image_tag}"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "ENV"
        value = var.environment == "prod" ? "production" : var.environment
      }

      env {
        name        = "OPENAI_API_KEY"
        secret_name = "model-api-key"
      }

      env {
        name  = "OPENAI_BASE_URL"
        value = var.model_base_url
      }

      env {
        name  = "OPENAI_MODEL"
        value = var.model_name
      }

      env {
        name  = "OPENAI_REASONING_EFFORT"
        value = var.reasoning_effort
      }

      env {
        name  = "OPENAI_EMBEDDING_MODEL"
        value = var.embedding_model_name
      }

      env {
        name  = "OPENAI_EMBEDDING_DIMENSIONS"
        value = tostring(var.embedding_dimensions)
      }

      env {
        name  = "ASSESSMENT_EVALUATOR_MODE"
        value = "llm"
      }

      env {
        name  = "ATTACHMENT_STORE"
        value = "azure_blob"
      }

      env {
        name  = "AZURE_STORAGE_ACCOUNT_URL"
        value = azurerm_storage_account.oliver.primary_blob_endpoint
      }

      env {
        name  = "AZURE_STORAGE_CONTAINER"
        value = azurerm_storage_container.attachments.name
      }

      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.workloads.client_id
      }

      env {
        name  = "ADMIN_AUTH_MODE"
        value = "entra"
      }

      env {
        name  = "SERVICE_AUTH_MODE"
        value = "entra"
      }

      env {
        name  = "ENTRA_TENANT_ID"
        value = data.azurerm_client_config.current.tenant_id
      }

      env {
        name  = "ENTRA_API_CLIENT_ID"
        value = azuread_application.oliver_api.client_id
      }

      env {
        name        = "INTERNAL_API_KEY"
        secret_name = "internal-api-key"
      }

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.oliver.connection_string
      }
    }
  }

  ingress {
    external_enabled           = true
    allow_insecure_connections = false
    target_port                = 8000
    transport                  = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  depends_on = [
    azurerm_key_vault.oliver,
    azurerm_role_assignment.workloads_acr_pull,
    azurerm_role_assignment.workloads_attachment_contributor,
    terraform_data.oliver_image,
    terraform_data.run_database_migrations,
  ]
}

resource "azurerm_container_app" "admin_backend" {
  name                         = local.admin_backend_name
  resource_group_name          = azurerm_resource_group.oliver.name
  container_app_environment_id = azurerm_container_app_environment.oliver.id
  revision_mode                = "Single"
  tags                         = local.common_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.workloads.id]
  }

  registry {
    server   = azurerm_container_registry.oliver.login_server
    identity = azurerm_user_assigned_identity.workloads.id
  }

  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.admin_database_url.versionless_id
    identity            = azurerm_user_assigned_identity.workloads.id
  }

  secret {
    name                = "admin-session-secret"
    key_vault_secret_id = azurerm_key_vault_secret.admin_session_secret.versionless_id
    identity            = azurerm_user_assigned_identity.workloads.id
  }

  template {
    min_replicas = var.admin_backend_min_replicas
    max_replicas = var.admin_backend_max_replicas

    container {
      name   = "admin-backend"
      image  = "${azurerm_container_registry.oliver.login_server}/admin-backend:${var.admin_backend_image_tag}"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "ENV"
        value = var.environment == "prod" ? "production" : var.environment
      }

      env {
        name  = "OLIVER_CORS_ORIGINS"
        value = local.admin_frontend_origin
      }

      env {
        name  = "ADMIN_AUTH_MODE"
        value = "entra"
      }

      env {
        name        = "ADMIN_SESSION_SECRET"
        secret_name = "admin-session-secret"
      }

      env {
        name  = "ENTRA_TENANT_ID"
        value = data.azurerm_client_config.current.tenant_id
      }

      env {
        name  = "ENTRA_CLIENT_ID"
        value = azuread_application.oliver_api.client_id
      }

      env {
        name  = "OLIVER_API_URL"
        value = "https://${azurerm_container_app.oliver.ingress[0].fqdn}"
      }

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.oliver.connection_string
      }
    }
  }

  ingress {
    external_enabled           = false
    allow_insecure_connections = false
    target_port                = 8000
    transport                  = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  depends_on = [
    azurerm_key_vault.oliver,
    azurerm_role_assignment.workloads_acr_pull,
    terraform_data.admin_backend_image,
    terraform_data.configure_database_access,
  ]
}

resource "azurerm_container_app" "admin_frontend" {
  name                         = local.admin_frontend_name
  resource_group_name          = azurerm_resource_group.oliver.name
  container_app_environment_id = azurerm_container_app_environment.oliver.id
  revision_mode                = "Single"
  tags                         = local.common_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.admin_frontend.id]
  }

  registry {
    server   = azurerm_container_registry.oliver.login_server
    identity = azurerm_user_assigned_identity.admin_frontend.id
  }

  template {
    min_replicas = var.admin_frontend_min_replicas
    max_replicas = var.admin_frontend_max_replicas

    container {
      name   = "admin-frontend"
      image  = "${azurerm_container_registry.oliver.login_server}/admin-frontend:${var.admin_frontend_image_tag}"
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "ADMIN_BACKEND_URL"
        value = "https://${azurerm_container_app.admin_backend.ingress[0].fqdn}"
      }
    }
  }

  ingress {
    external_enabled           = true
    allow_insecure_connections = false
    target_port                = 80
    transport                  = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  depends_on = [
    azurerm_container_app.admin_backend,
    azurerm_role_assignment.admin_frontend_acr_pull,
    terraform_data.admin_frontend_image,
  ]
}

resource "azurerm_container_app_job" "database_migrations" {
  name                         = "job-${local.name_prefix}-migrations"
  location                     = azurerm_resource_group.oliver.location
  resource_group_name          = azurerm_resource_group.oliver.name
  container_app_environment_id = azurerm_container_app_environment.oliver.id
  replica_timeout_in_seconds   = 900
  replica_retry_limit          = 1
  tags                         = local.common_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.workloads.id]
  }

  registry {
    server   = azurerm_container_registry.oliver.login_server
    identity = azurerm_user_assigned_identity.workloads.id
  }

  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.oliver_database_url.versionless_id
    identity            = azurerm_user_assigned_identity.workloads.id
  }

  secret {
    name                = "model-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.model_api_key.versionless_id
    identity            = azurerm_user_assigned_identity.workloads.id
  }

  secret {
    name                = "internal-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.internal_api_key.versionless_id
    identity            = azurerm_user_assigned_identity.workloads.id
  }

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  template {
    container {
      name    = "migrations"
      image   = "${azurerm_container_registry.oliver.login_server}/oliver:${var.oliver_image_tag}"
      cpu     = 0.5
      memory  = "1Gi"
      command = ["/bin/sh"]
      args    = ["-c", "uv run --no-sync alembic upgrade head"]

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }

      env {
        name        = "OPENAI_API_KEY"
        secret_name = "model-api-key"
      }

      env {
        name  = "OPENAI_MODEL"
        value = var.model_name
      }

      env {
        name  = "OPENAI_BASE_URL"
        value = var.model_base_url
      }

      env {
        name  = "OPENAI_EMBEDDING_MODEL"
        value = var.embedding_model_name
      }

      env {
        name  = "OPENAI_EMBEDDING_DIMENSIONS"
        value = tostring(var.embedding_dimensions)
      }

      env {
        name        = "INTERNAL_API_KEY"
        secret_name = "internal-api-key"
      }
    }
  }

  depends_on = [
    azurerm_key_vault.oliver,
    azurerm_role_assignment.workloads_acr_pull,
    terraform_data.oliver_image,
  ]
}

resource "azurerm_container_app_job" "database_access" {
  name                         = "job-${local.name_prefix}-database-access"
  location                     = azurerm_resource_group.oliver.location
  resource_group_name          = azurerm_resource_group.oliver.name
  container_app_environment_id = azurerm_container_app_environment.oliver.id
  replica_timeout_in_seconds   = 300
  replica_retry_limit          = 1
  tags                         = local.common_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.workloads.id]
  }

  secret {
    name                = "postgres-administrator-password"
    key_vault_secret_id = azurerm_key_vault_secret.postgres_administrator_password.versionless_id
    identity            = azurerm_user_assigned_identity.workloads.id
  }

  secret {
    name                = "postgres-admin-reader-password"
    key_vault_secret_id = azurerm_key_vault_secret.postgres_admin_reader_password.versionless_id
    identity            = azurerm_user_assigned_identity.workloads.id
  }

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  template {
    container {
      name    = "database-access"
      image   = "postgres:16-alpine"
      cpu     = 0.25
      memory  = "0.5Gi"
      command = ["/bin/sh"]
      args = [
        "-c",
        <<-EOT
                    PGPASSWORD="$POSTGRES_ADMIN_PASSWORD" psql \
                        --host "$POSTGRES_HOST" \
                        --dbname "$POSTGRES_DATABASE" \
                        --username "$POSTGRES_ADMIN_LOGIN" \
                        --set ON_ERROR_STOP=1 \
                        --command "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${var.postgres_admin_reader_login}') THEN CREATE ROLE ${var.postgres_admin_reader_login} LOGIN; END IF; END \$\$; ALTER ROLE ${var.postgres_admin_reader_login} PASSWORD '$POSTGRES_ADMIN_READER_PASSWORD'; REVOKE ALL ON DATABASE ${var.postgres_database_name} FROM ${var.postgres_admin_reader_login}; GRANT CONNECT ON DATABASE ${var.postgres_database_name} TO ${var.postgres_admin_reader_login}; GRANT USAGE ON SCHEMA public TO ${var.postgres_admin_reader_login}; GRANT SELECT ON ALL TABLES IN SCHEMA public TO ${var.postgres_admin_reader_login}; ALTER DEFAULT PRIVILEGES FOR ROLE ${var.postgres_administrator_login} IN SCHEMA public GRANT SELECT ON TABLES TO ${var.postgres_admin_reader_login};"
                EOT
      ]

      env {
        name  = "POSTGRES_HOST"
        value = azurerm_postgresql_flexible_server.oliver.fqdn
      }

      env {
        name  = "POSTGRES_DATABASE"
        value = azurerm_postgresql_flexible_server_database.oliver.name
      }

      env {
        name  = "POSTGRES_ADMIN_LOGIN"
        value = var.postgres_administrator_login
      }

      env {
        name        = "POSTGRES_ADMIN_PASSWORD"
        secret_name = "postgres-administrator-password"
      }

      env {
        name        = "POSTGRES_ADMIN_READER_PASSWORD"
        secret_name = "postgres-admin-reader-password"
      }
    }
  }

  depends_on = [
    azurerm_key_vault.oliver,
    terraform_data.run_database_migrations,
  ]
}

resource "terraform_data" "configure_database_access" {
  triggers_replace = [
    azurerm_container_app_job.database_access.id,
    azurerm_postgresql_flexible_server_database.oliver.id,
    terraform_data.run_database_migrations.id,
    var.postgres_admin_reader_login,
    nonsensitive(sha256(random_password.postgres_administrator.result)),
    nonsensitive(sha256(random_password.postgres_admin_reader.result)),
  ]

  provisioner "local-exec" {
    command = <<-EOT
            execution_name=$(az containerapp job start --name ${azurerm_container_app_job.database_access.name} --resource-group ${azurerm_resource_group.oliver.name} --query name --output tsv)
            for attempt in $(seq 1 30); do
                status=$(az containerapp job execution show --name ${azurerm_container_app_job.database_access.name} --job-execution-name "$execution_name" --resource-group ${azurerm_resource_group.oliver.name} --query properties.status --output tsv)
                if [ "$status" = "Succeeded" ]; then
                    exit 0
                fi
                if [ "$status" = "Failed" ]; then
                    exit 1
                fi
                sleep 10
            done
            exit 1
        EOT
  }
}

resource "terraform_data" "run_database_migrations" {
  triggers_replace = [
    terraform_data.oliver_image.id,
    azurerm_container_app_job.database_migrations.id,
    azurerm_postgresql_flexible_server_database.oliver.id,
  ]

  provisioner "local-exec" {
    command = <<-EOT
            execution_name=$(az containerapp job start --name ${azurerm_container_app_job.database_migrations.name} --resource-group ${azurerm_resource_group.oliver.name} --query name --output tsv)
            for attempt in $(seq 1 90); do
                status=$(az containerapp job execution show --name ${azurerm_container_app_job.database_migrations.name} --job-execution-name "$execution_name" --resource-group ${azurerm_resource_group.oliver.name} --query properties.status --output tsv)
                if [ "$status" = "Succeeded" ]; then
                    exit 0
                fi
                if [ "$status" = "Failed" ]; then
                    exit 1
                fi
                sleep 10
            done
            exit 1
        EOT
  }
}
