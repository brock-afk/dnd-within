# Bicep

Two deployments at subscription scope. `bootstrap.bicep` decides what the pipelines may do, so it's run by hand. `main.bicep` is the workload, deployed by `.github/workflows/infra.yml`.

| File | Deployed by | Holds |
|---|---|---|
| `bootstrap.bicep` | you | resource groups, custom roles, CI identities and their access, your blob and secret access, delete locks |
| `governance.bicep` | bootstrap | policy assignments |
| `identities.bicep` | bootstrap | the `github` (app), `infra` and `whatif` identities, in `rg-dndwithin-shared` |
| `modules/rg-access.bicep` | bootstrap | Contributor, plus role assignment limited to named roles, for the infra identity |
| `modules/vm-deployer-role.bicep` | bootstrap | custom role: read a VM and run commands on it |
| `modules/user-role.bicep` | bootstrap | Storage Blob Data Contributor and Key Vault Secrets Officer on `rg-dndwithin-shared` for whoever runs bootstrap |
| `modules/rg-lock.bicep` | bootstrap | CanNotDelete lock on each resource group; remove it before tearing a group down |
| `main.bicep` | infra.yml | wires the workload modules together |
| `acr.bicep` | main | container registry; AcrPush for the app identity |
| `network.bicep` | main | VNet, subnet + NSG, public IP |
| `vm.bicep` | main | VM, NIC, disks, cloud-init; AcrPull for the VM; the VM Deployer role for the app identity |
| `keyvault.bicep` | main | Key Vault (RBAC, purge protection) for the app's secrets; read access for the VM |
| `vm-backup.bicep` | main | Recovery Services vault (GRS, soft delete) and an Enhanced daily policy protecting the VM, 14 days |
| `backup.bicep` | main | GRS storage for database backups: Entra-only, 14-day immutability, deleted after 35 days; write access for the VM |

Bootstrap:

    az deployment sub what-if -n bootstrap -l centralus -f bootstrap.bicep -p bootstrap.bicepparam
    az deployment sub create -n bootstrap -l centralus -f bootstrap.bicep -p bootstrap.bicepparam

Its outputs are the GitHub repository variables. `main.bicepparam` reads `SSH_SOURCE_ADDRESS` and `SSH_PUBLIC_KEY` from the environment (repository variables in CI), so a local what-if needs them exported:

    export SSH_SOURCE_ADDRESS=$(curl -s https://api.ipify.org)/32 SSH_PUBLIC_KEY="$(cat ~/.ssh/dndwithin-vm.pub)"
    az deployment sub what-if -n main -l centralus -f main.bicep -p main.bicepparam

`what-if` lists defaults Azure filled in, and values it can't resolve until deploy (role assignment principal IDs, the NIC's subnet), as changes. Look for Create, Delete, or changes to values set in the templates.
