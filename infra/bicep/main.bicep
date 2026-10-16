// The workload, deployed by infra.yml. Resource groups, identities and roles come from
// bootstrap.bicep, so this deployment can't change who may deploy it.
targetScope = 'subscription'

param location string = 'centralus'

@description('Short project name, used in every resource name.')
param project string = 'dndwithin'

@description('Public IP (CIDR) allowed to SSH in, e.g. 203.0.113.7/32.')
param sshSourceAddress string

@description('SSH public key for the VM admin user.')
param sshPublicKey string

param tags object = {
  project: project
  environment: 'prod'
}

resource sharedRg 'Microsoft.Resources/resourceGroups@2024-03-01' existing = {
  name: 'rg-${project}-shared'
}

resource iaasRg 'Microsoft.Resources/resourceGroups@2024-03-01' existing = {
  name: 'rg-${project}-iaas'
}

resource appIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: 'id-${project}-github'
  scope: sharedRg
}

module acr 'acr.bicep' = {
  name: 'acr'
  scope: sharedRg
  params: {
    location: location
    project: project
    appIdentityId: appIdentity.id
    appPrincipalId: appIdentity.properties.principalId
    tags: tags
  }
}

module network 'network.bicep' = {
  name: 'network'
  scope: iaasRg
  params: {
    location: location
    project: project
    sshSourceAddress: sshSourceAddress
    tags: tags
  }
}

module vm 'vm.bicep' = {
  name: 'vm'
  scope: iaasRg
  params: {
    location: location
    project: project
    sshPublicKey: sshPublicKey
    subnetId: network.outputs.subnetId
    publicIpId: network.outputs.publicIpId
    registryName: acr.outputs.registryName
    sharedResourceGroupName: sharedRg.name
    ciIdentityId: appIdentity.id
    ciPrincipalId: appIdentity.properties.principalId
    vmDeployerRoleId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      guid(subscription().id, project, 'vm-deployer')
    )
    tags: tags
  }
}

module backup 'backup.bicep' = {
  name: 'backup'
  scope: sharedRg
  params: {
    location: location
    project: project
    vmPrincipalId: vm.outputs.principalId
    tags: tags
  }
}

module keyVault 'keyvault.bicep' = {
  name: 'keyvault'
  scope: sharedRg
  params: {
    location: location
    project: project
    vmPrincipalId: vm.outputs.principalId
    tags: tags
  }
}

module vmBackup 'vm-backup.bicep' = {
  name: 'vm-backup'
  scope: sharedRg
  params: {
    location: location
    project: project
    vmId: vm.outputs.vmId
    vmName: vm.outputs.vmName
    vmResourceGroupName: iaasRg.name
    tags: tags
  }
}

output registryLoginServer string = acr.outputs.loginServer
output backupAccountName string = backup.outputs.accountName
output keyVaultName string = keyVault.outputs.vaultName
output fqdn string = network.outputs.fqdn
