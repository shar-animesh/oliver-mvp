resource "azurerm_virtual_network" "oliver" {
  name                = "vnet-${local.name_prefix}"
  address_space       = [var.virtual_network_address_space]
  location            = azurerm_resource_group.oliver.location
  resource_group_name = azurerm_resource_group.oliver.name
  tags                = local.common_tags
}

resource "azurerm_subnet" "container_apps" {
  name                 = "snet-container-apps"
  resource_group_name  = azurerm_resource_group.oliver.name
  virtual_network_name = azurerm_virtual_network.oliver.name
  address_prefixes     = [var.container_apps_subnet_address_prefix]
  service_endpoints    = ["Microsoft.Storage"]

  delegation {
    name = "Microsoft.App.environments"

    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "postgresql" {
  name                 = "snet-postgresql"
  resource_group_name  = azurerm_resource_group.oliver.name
  virtual_network_name = azurerm_virtual_network.oliver.name
  address_prefixes     = [var.postgres_subnet_address_prefix]

  delegation {
    name = "Microsoft.DBforPostgreSQL.flexibleServers"

    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_private_dns_zone" "postgresql" {
  name                = "${local.unique_name}.private.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.oliver.name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgresql" {
  name                  = "link-${local.name_prefix}-postgresql"
  private_dns_zone_name = azurerm_private_dns_zone.postgresql.name
  virtual_network_id    = azurerm_virtual_network.oliver.id
  resource_group_name   = azurerm_resource_group.oliver.name
  tags                  = local.common_tags
}

resource "random_password" "postgres_administrator" {
  length      = 40
  special     = false
  min_lower   = 1
  min_numeric = 1
  min_upper   = 1
}

resource "random_password" "postgres_admin_reader" {
  length      = 40
  special     = false
  min_lower   = 1
  min_numeric = 1
  min_upper   = 1
}

resource "azurerm_postgresql_flexible_server" "oliver" {
  name                          = "psql-${local.unique_name}"
  resource_group_name           = azurerm_resource_group.oliver.name
  location                      = azurerm_resource_group.oliver.location
  version                       = var.postgres_version
  delegated_subnet_id           = azurerm_subnet.postgresql.id
  private_dns_zone_id           = azurerm_private_dns_zone.postgresql.id
  public_network_access_enabled = false
  administrator_login           = var.postgres_administrator_login
  administrator_password        = random_password.postgres_administrator.result
  sku_name                      = var.postgres_sku_name
  storage_mb                    = var.postgres_storage_mb
  backup_retention_days         = var.environment == "prod" ? 35 : 7
  geo_redundant_backup_enabled  = var.postgres_geo_redundant_backup_enabled
  tags                          = local.common_tags

  authentication {
    password_auth_enabled         = true
    active_directory_auth_enabled = false
  }

  dynamic "high_availability" {
    for_each = var.postgres_zone_redundant ? [1] : []

    content {
      mode = "ZoneRedundant"
    }
  }

  lifecycle {
    precondition {
      condition     = !var.postgres_zone_redundant || !startswith(var.postgres_sku_name, "B_")
      error_message = "Azure PostgreSQL zone-redundant high availability requires a General Purpose or Memory Optimized SKU; Burstable B_* SKUs are unsupported."
    }
  }

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgresql]
}

resource "azurerm_postgresql_flexible_server_database" "oliver" {
  name      = var.postgres_database_name
  server_id = azurerm_postgresql_flexible_server.oliver.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

locals {
  oliver_database_url = format(
    "postgresql+psycopg://%s:%s@%s:5432/%s?sslmode=require",
    var.postgres_administrator_login,
    urlencode(random_password.postgres_administrator.result),
    azurerm_postgresql_flexible_server.oliver.fqdn,
    azurerm_postgresql_flexible_server_database.oliver.name,
  )

  admin_database_url = format(
    "postgresql+psycopg://%s:%s@%s:5432/%s?sslmode=require",
    var.postgres_admin_reader_login,
    urlencode(random_password.postgres_admin_reader.result),
    azurerm_postgresql_flexible_server.oliver.fqdn,
    azurerm_postgresql_flexible_server_database.oliver.name,
  )
}
