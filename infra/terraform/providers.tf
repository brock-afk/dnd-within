# How the azurerm provider connects. Credentials aren't here: locally it uses your `az login`
# session, and in CI the GitHub OIDC identity (step 0.5).
provider "azurerm" {
  features {}

  # azurerm 4.x requires the subscription explicitly. It comes from the ARM_SUBSCRIPTION_ID
  # environment variable (your shell profile locally, a GitHub variable in CI), so the
  # environment stays out of the code.

  # By default the provider registers dozens of resource providers on first use. We register
  # each one ourselves, just in time (as with Bicep, which never registers anything).
  resource_provider_registrations = "none"

  # The state account has account keys disabled, so blob and container operations must use
  # Entra ID (your data-plane role) instead of fetching a key.
  storage_use_azuread = true
}
