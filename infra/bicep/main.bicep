// Everything, in one subscription deployment; dependencies come from the outputs passed between
// modules. Resource groups are one per lifecycle: "shared" lasts, "iaas" holds the VM.
targetScope = 'subscription'

@description('Region for every resource, and the only one policy allows.')
param location string = 'centralus'

@description('Short project name, used in every resource name.')
param project string = 'dndwithin'

@description('The repo as it appears in GitHub\'s OIDC subject (owner@id/name@id).')
param githubRepo string

@description('Public IP (CIDR) allowed to SSH in, e.g. 203.0.113.7/32.')
param sshSourceAddress string

@description('SSH public key for the VM admin user.')
param sshPublicKey string

param tags object = {
  project: project
  environment: 'prod'
}

resource sharedRg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${project}-shared'
  location: location
  tags: tags
}

resource iaasRg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${project}-iaas'
  location: location
  tags: tags
}

module governance 'governance.bicep' = {
  name: 'governance'
  params: {
    location: location
  }
}

module acr 'acr.bicep' = {
  name: 'acr'
  scope: sharedRg
  params: {
    project: project
    tags: tags
  }
}

module ciIdentity 'ci-identity.bicep' = {
  name: 'ci-identity'
  scope: sharedRg
  params: {
    project: project
    githubRepo: githubRepo
    registryName: acr.outputs.registryName
    tags: tags
  }
}

module network 'network.bicep' = {
  name: 'network'
  scope: iaasRg
  params: {
    project: project
    sshSourceAddress: sshSourceAddress
    tags: tags
  }
}

module vm 'vm.bicep' = {
  name: 'vm'
  scope: iaasRg
  params: {
    project: project
    sshPublicKey: sshPublicKey
    subnetId: network.outputs.subnetId
    publicIpId: network.outputs.publicIpId
    registryName: acr.outputs.registryName
    sharedResourceGroupName: sharedRg.name
    ciIdentityId: ciIdentity.outputs.identityId
    ciPrincipalId: ciIdentity.outputs.principalId
    tags: tags
  }
}

// GitHub Actions variables: AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID.
output clientId string = ciIdentity.outputs.clientId
output tenantId string = tenant().tenantId
output subscriptionId string = subscription().subscriptionId
output registryLoginServer string = acr.outputs.loginServer
output fqdn string = network.outputs.fqdn
