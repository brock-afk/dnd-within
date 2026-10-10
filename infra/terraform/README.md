# Terraform

The same infrastructure as `../bicep/`, kept in a remote state file in Azure Storage (set up in
step 0.4). Resource providers are registered explicitly, never automatically.

    terraform init       # download providers, connect to the state backend
    terraform plan       # what would change (the Bicep what-if equivalent)
    terraform apply      # make the changes
    terraform import ... # adopt a resource that already exists (one Bicep created)
