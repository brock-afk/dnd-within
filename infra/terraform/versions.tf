# Which Terraform and which provider versions this configuration works with. `terraform init`
# picks the newest azurerm 4.x and records the exact version and checksums in
# .terraform.lock.hcl, which is committed so CI and your laptop use identical providers.
terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0" # any 4.x, never 5.0 (a major version can change resource schemas)
    }
  }
}
