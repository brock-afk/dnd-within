// Module of main.bicep: content pack releases, one tarball per tag of the content repo, in the
// backup storage account. The content repo publishes them; the VM downloads them to import.
targetScope = 'resourceGroup'

param accountName string

@description('The content repo\'s release identity, which uploads releases.')
param releasePrincipalId string

@description('The VM\'s identity, which downloads releases.')
param vmPrincipalId string

@description('Days a release can\'t be changed or deleted. Releases are what a rollback or a rebuilt VM installs.')
param immutableDays int = 365

var blobDataContributorRole = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var blobDataReaderRole = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'

resource account 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: accountName
}

resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  parent: account
  name: 'default'
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobs
  name: 'content-releases'
  properties: {
    publicAccess: 'None'
  }
}

// Longer than the account's default, which is sized for backups.
resource immutability 'Microsoft.Storage/storageAccounts/blobServices/containers/immutabilityPolicies@2023-05-01' = {
  parent: container
  name: 'default'
  properties: {
    immutabilityPeriodSinceCreationInDays: immutableDays
    allowProtectedAppendWrites: false
  }
}

resource releaseWriter 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(container.id, releasePrincipalId, blobDataContributorRole)
  scope: container
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributorRole)
    principalId: releasePrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource vmReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(container.id, vmPrincipalId, blobDataReaderRole)
  scope: container
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataReaderRole)
    principalId: vmPrincipalId
    principalType: 'ServicePrincipal'
  }
}
