resource "terraform_data" "oliver_image" {
  triggers_replace = [
    sha256(join("", [
      for file in sort(fileset("${path.module}/../oliver", "**")) : filesha256("${path.module}/../oliver/${file}")
      if !startswith(file, ".venv/") && !startswith(file, ".ruff_cache/") && !startswith(file, "__pycache__/") && !startswith(file, "dist/")
    ])),
    var.oliver_image_tag,
  ]

  provisioner "local-exec" {
    working_dir = path.module
    command     = "az acr build --registry ${azurerm_container_registry.oliver.name} --image oliver:${var.oliver_image_tag} ../oliver"
  }
}

resource "terraform_data" "admin_backend_image" {
  triggers_replace = [
    sha256(join("", [
      for file in sort(fileset("${path.module}/../admin-dashboard/backend", "**")) : filesha256("${path.module}/../admin-dashboard/backend/${file}")
      if file != ".env" && !startswith(file, ".venv/") && !startswith(file, ".ruff_cache/") && !startswith(file, "__pycache__/")
    ])),
    var.admin_backend_image_tag,
  ]

  provisioner "local-exec" {
    working_dir = path.module
    command     = "az acr build --registry ${azurerm_container_registry.oliver.name} --image admin-backend:${var.admin_backend_image_tag} ../admin-dashboard/backend"
  }
}

resource "terraform_data" "admin_frontend_image" {
  triggers_replace = [
    sha256(join("", [
      for file in sort(fileset("${path.module}/../admin-dashboard/frontend", "**")) : filesha256("${path.module}/../admin-dashboard/frontend/${file}")
      if !startswith(file, "node_modules/") && !startswith(file, "dist/")
    ])),
    var.admin_frontend_image_tag,
    data.azurerm_client_config.current.tenant_id,
    azuread_application.admin_dashboard.client_id,
    one(azuread_application.oliver_api.identifier_uris),
  ]

  provisioner "local-exec" {
    working_dir = path.module
    command = join(" ", [
      "az acr build",
      "--registry ${azurerm_container_registry.oliver.name}",
      "--image admin-frontend:${var.admin_frontend_image_tag}",
      "--build-arg VITE_ADMIN_AUTH_MODE=entra",
      "--build-arg VITE_ENTRA_TENANT_ID=${data.azurerm_client_config.current.tenant_id}",
      "--build-arg VITE_ENTRA_SPA_CLIENT_ID=${azuread_application.admin_dashboard.client_id}",
      "--build-arg VITE_ENTRA_API_SCOPE=${one(azuread_application.oliver_api.identifier_uris)}/access_as_user",
      "../admin-dashboard/frontend",
    ])
  }
}
