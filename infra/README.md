# Infrastructure as code

DnD Within's Azure infrastructure, written twice on purpose (an AZ-104 study exercise):

- `bicep/`: Bicep, Microsoft's language for ARM templates. `az bicep build` compiles a file to
  the ARM JSON Azure actually receives. Deployed with `az deployment group what-if` (preview)
  and `az deployment group create`.
- `terraform/`: the same resources in Terraform. Each layer is first deployed with Bicep, then
  written here and imported (`terraform import`) until `terraform plan` shows no changes. From
  then on Terraform is the source of truth.

Region: Central US. The subscription is a Free Trial, where only ARM (Ampere) B-series VM sizes
are offered, so the Stage 1 VM is ARM64 and the app image is built for both arm64 and amd64.
