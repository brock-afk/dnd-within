# The identity GitHub Actions logs in as, through OIDC. No secrets: Azure trusts GitHub's
# token when its subject matches the federated credential.

data "azurerm_client_config" "current" {}

data "azurerm_resource_group" "shared" {
  name = "rg-${var.project}-shared"
}

resource "azurerm_user_assigned_identity" "github" {
  name                = "id-${var.project}-github"
  resource_group_name = data.azurerm_resource_group.shared.name
  location            = var.location
  tags = {
    project      = var.project
    environment  = "prod"
    "managed-by" = "terraform"
  }
}

# Only workflow runs on main can log in.
resource "azurerm_federated_identity_credential" "github_main" {
  name                      = "github-main"
  user_assigned_identity_id = azurerm_user_assigned_identity.github.id
  issuer                    = "https://token.actions.githubusercontent.com"
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = "repo:${var.github_repo}:ref:refs/heads/main"
}

# Enough to prove the login works; later steps add only what they need.
resource "azurerm_role_assignment" "github_reader" {
  scope                = data.azurerm_resource_group.shared.id
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.github.principal_id
  principal_type       = "ServicePrincipal"
}
