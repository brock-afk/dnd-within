# Where Terraform keeps its state: the blob created by ../bicep/state.bicep (step 0.4a), not a
# local terraform.tfstate. Blob leases lock the state, so two applies can't run at once.
# Backend blocks can't use variables; these values are fixed.
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-dndwithin-shared"
    storage_account_name = "stdndwithintfcsiqzeuv"
    container_name       = "tfstate"
    key                  = "dndwithin.tfstate" # the blob name

    # Authenticate with Entra ID (Storage Blob Data Contributor), not an account key. Required
    # here: the account rejects keys (allowSharedKeyAccess = false).
    use_azuread_auth = true
  }
}
