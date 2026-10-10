# Terraform

The subscription comes from the environment, not the code: set `ARM_SUBSCRIPTION_ID` in your
shell profile (CI sets it from a GitHub variable).

    terraform init       # download providers, connect to the state backend
    terraform plan       # what would change (the Bicep what-if equivalent)
    terraform apply      # make the changes
    terraform import ... # adopt a resource that already exists (one Bicep created)
