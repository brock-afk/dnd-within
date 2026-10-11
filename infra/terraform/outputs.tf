# Add these as Actions variables in the GitHub repo (Settings > Secrets and variables > Actions).
output "AZURE_CLIENT_ID" {
  value = azurerm_user_assigned_identity.github.client_id
}

output "AZURE_TENANT_ID" {
  value = data.azurerm_client_config.current.tenant_id
}

output "AZURE_SUBSCRIPTION_ID" {
  value = data.azurerm_client_config.current.subscription_id
}
