# Bicep

`main.bicep` deploys everything at subscription scope; the other files are its modules.

| File | Scope | Holds |
|---|---|---|
| `main.bicep` | subscription | resource groups; wires the modules together |
| `governance.bicep` | subscription | policy assignments |
| `acr.bicep` | `rg-dndwithin-shared` | container registry |
| `ci-identity.bicep` | `rg-dndwithin-shared` | GitHub Actions identity and its roles |
| `network.bicep` | `rg-dndwithin-iaas` | VNet, subnet + NSG, public IP |
| `vm.bicep` | `rg-dndwithin-iaas` | VM, NIC, disks, cloud-init; AcrPull for the VM; the CI deploy role (`modules/`) |

    az deployment sub what-if -l centralus -f main.bicep -p main.bicepparam -p sshSourceAddress=<ip>/32 -p sshPublicKey="$(cat ~/.ssh/dndwithin-vm.pub)"
    az deployment sub create -n main -l centralus -f main.bicep -p main.bicepparam -p sshSourceAddress=<ip>/32 -p sshPublicKey="$(cat ~/.ssh/dndwithin-vm.pub)"
    az bicep build -f main.bicep   # writes main.json, the compiled ARM template
