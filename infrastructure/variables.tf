variable "subscription_id" {
  description = "Azure subscription that hosts Oliver. Set ARM_SUBSCRIPTION_ID instead when preferred."
  type        = string
  default     = null
  nullable    = true
}

variable "location" {
  description = "Azure region for all Oliver resources."
  type        = string
  default     = "westeurope"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "environment must be dev, test, or prod."
  }
}

variable "resource_prefix" {
  description = "Short lowercase prefix used in Azure resource names."
  type        = string
  default     = "oliver"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,15}$", var.resource_prefix))
    error_message = "resource_prefix must start with a letter and contain 2-16 lowercase letters, numbers, or hyphens."
  }
}

variable "mailbox_address" {
  description = "Microsoft 365 shared mailbox monitored and used for replies."
  type        = string
}

variable "model_api_key" {
  description = "OpenAI-compatible model-provider API key stored in Key Vault. Supply it through TF_VAR_model_api_key."
  type        = string
  sensitive   = true
}

variable "model_base_url" {
  description = "HTTPS base URL for the approved OpenAI-compatible model provider."
  type        = string

  validation {
    condition     = can(regex("^https://", var.model_base_url))
    error_message = "model_base_url must be an HTTPS endpoint."
  }
}

variable "model_name" {
  description = "Response model name supplied to Oliver from environment configuration."
  type        = string
}

variable "postgres_administrator_login" {
  description = "Azure Database for PostgreSQL administrator used only by Oliver and migrations."
  type        = string
  default     = "oliverdbadmin"
}

variable "postgres_admin_reader_login" {
  description = "Read-only PostgreSQL role used by the independently deployable admin backend."
  type        = string
  default     = "oliver_admin_reader"

  validation {
    condition     = can(regex("^[A-Za-z][A-Za-z0-9_]{2,62}$", var.postgres_admin_reader_login))
    error_message = "postgres_admin_reader_login must contain 3-63 letters, numbers, or underscores and start with a letter."
  }
}

variable "postgres_database_name" {
  description = "PostgreSQL database owned by Oliver."
  type        = string
  default     = "oliver"
}

variable "postgres_version" {
  description = "Supported PostgreSQL Flexible Server major version."
  type        = string
  default     = "16"
}

variable "postgres_sku_name" {
  description = "PostgreSQL Flexible Server compute SKU."
  type        = string
  default     = "B_Standard_B1ms"
}

variable "postgres_storage_mb" {
  description = "Provisioned PostgreSQL storage in MiB; Azure storage cannot be scaled down."
  type        = number
  default     = 32768
}

variable "postgres_zone_redundant" {
  description = "Enable zone-redundant PostgreSQL high availability where the region and SKU support it."
  type        = bool
  default     = false
}

variable "postgres_geo_redundant_backup_enabled" {
  description = "Enable geo-redundant PostgreSQL backups where supported."
  type        = bool
  default     = false
}

variable "virtual_network_address_space" {
  description = "Address space reserved for Oliver production workloads."
  type        = string
  default     = "10.40.0.0/16"
}

variable "container_apps_subnet_address_prefix" {
  description = "Dedicated Container Apps infrastructure subnet; use /23 or larger."
  type        = string
  default     = "10.40.0.0/23"
}

variable "postgres_subnet_address_prefix" {
  description = "Dedicated delegated subnet for PostgreSQL Flexible Server."
  type        = string
  default     = "10.40.2.0/24"
}

variable "reasoning_effort" {
  description = "Reasoning effort sent to the configured model provider."
  type        = string
  default     = "high"
}

variable "oliver_image_tag" {
  description = "Oliver image tag already pushed to the Terraform-managed registry."
  type        = string
  default     = "latest"
}

variable "admin_backend_image_tag" {
  description = "Admin backend image tag already pushed to the Terraform-managed registry."
  type        = string
  default     = "latest"
}

variable "admin_frontend_image_tag" {
  description = "Admin frontend image tag already pushed to the Terraform-managed registry."
  type        = string
  default     = "latest"
}

variable "container_min_replicas" {
  description = "Minimum number of Oliver API replicas."
  type        = number
  default     = 0
}

variable "container_max_replicas" {
  description = "Maximum number of Oliver API replicas."
  type        = number
  default     = 3
}

variable "admin_backend_min_replicas" {
  description = "Minimum number of admin backend replicas."
  type        = number
  default     = 0
}

variable "admin_backend_max_replicas" {
  description = "Maximum number of admin backend replicas."
  type        = number
  default     = 2
}

variable "admin_frontend_min_replicas" {
  description = "Minimum number of admin frontend replicas."
  type        = number
  default     = 0
}

variable "admin_frontend_max_replicas" {
  description = "Maximum number of admin frontend replicas."
  type        = number
  default     = 2
}

variable "embedding_model_name" {
  description = "Embedding deployment/model name supplied to Oliver; never hard-coded in application code."
  type        = string
}

variable "embedding_dimensions" {
  description = "Vector dimensions returned by the configured embedding model."
  type        = number
  default     = 1536
}

variable "admin_role_group_object_ids" {
  description = "Entra security-group object IDs by Oliver user app-role value. Assign people to groups, not in code."
  type        = map(set(string))
  default     = {}

  validation {
    condition = alltrue([
      for role in keys(var.admin_role_group_object_ids) : contains([
        "Oliver.Admin.Read",
        "Oliver.Assessment.Test",
        "Oliver.Lifecycle.Approve",
        "Oliver.Scout.Review",
        "Oliver.Platform.Admin",
      ], role)
    ])
    error_message = "admin_role_group_object_ids contains an unknown or workload-only Oliver role."
  }
}

variable "admin_additional_redirect_uris" {
  description = "Additional HTTPS SPA redirect URIs, for example a controlled test hostname."
  type        = set(string)
  default     = []
}

variable "log_retention_days" {
  description = "Log Analytics retention period."
  type        = number
  default     = 30
}

variable "container_registry_sku" {
  description = "Azure Container Registry SKU."
  type        = string
  default     = "Basic"
}

variable "tags" {
  description = "Additional Azure resource tags."
  type        = map(string)
  default     = {}
}
