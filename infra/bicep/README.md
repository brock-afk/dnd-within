# Bicep

| File | Scope | Holds |
|---|---|---|
| `governance.bicep` | subscription | resource groups, policy assignments |
| `acr.bicep` | `rg-dndwithin-shared` | container registry |
| `ci-identity.bicep` | `rg-dndwithin-shared` | GitHub Actions identity and its roles (after `acr.bicep`) |
| `network.bicep` | `rg-dndwithin-iaas` | VNet, subnet + NSG, public IP (pass `-p sshSourceAddress=<ip>/32`) |
| `vm.bicep` | `rg-dndwithin-iaas` | VM, NIC, disks, cloud-init; AcrPull for the VM; the CI deploy role (`modules/`) (pass `-p sshPublicKey=...`) |

    az deployment sub create   -n governance -l centralus -f governance.bicep -p governance.bicepparam
    az deployment group what-if -g <resource group> -f <file>.bicep -p <file>.bicepparam
    az deployment group create  -n <file> -g <resource group> -f <file>.bicep -p <file>.bicepparam
    az bicep build -f <file>.bicep   # writes <file>.json, the compiled ARM template
