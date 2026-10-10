// Step 0.4a: the storage account holding Terraform's state. Bootstrapped with Bicep because
// Terraform can't keep its state in an account that doesn't exist yet; Terraform imports it
// afterwards. Deployed into the shared resource group:
//   az deployment group what-if -g rg-dndwithin-shared -f state.bicep -p state.bicepparam
targetScope = 'resourceGroup'

@description('Region; the allowed-locations policy only permits centralus.')
param location string = resourceGroup().location

@description('Short project name, used in resource names.')
param project string = 'dndwithin'

@description('Object ID of the user (or, later, the CI identity) that reads and writes state.')
param stateWriterPrincipalId string

@description('Whether stateWriterPrincipalId is a user or a service principal.')
@allowed([
  'User'
  'ServicePrincipal'
])
param stateWriterPrincipalType string = 'User'

param tags object = {
  project: project
  environment: 'prod'
  'managed-by': 'bicep'
}

// Globally unique, 3-24 lowercase letters and digits: a fixed prefix plus a stable hash of this
// resource group's ID (the same every deployment, different in every subscription).
var storageAccountName = 'st${project}tf${take(uniqueString(resourceGroup().id), 8)}'

// Built-in role: Storage Blob Data Contributor (read, write and delete blobs: the data plane).
var storageBlobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

resource state 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS' // 3 copies in one datacenter; ZRS/GZRS for production state
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false // no anonymous reads, whatever a container says
    allowSharedKeyAccess: false // account keys disabled: Entra ID (RBAC) only
    publicNetworkAccess: 'Enabled' // your laptop and GitHub runners reach it over the internet
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: state
  name: 'default' // a storage account has exactly one blob service, always named "default"
  properties: {
    isVersioningEnabled: true // every earlier state file is kept: recovery from a bad apply
    deleteRetentionPolicy: {
      enabled: true
      days: 14
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days: 14
    }
  }
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'tfstate'
  properties: {
    publicAccess: 'None'
  }
}

// An extension resource: it attaches to the storage account through `scope` instead of being a
// child of it. Its name must be a GUID that's stable across deployments, hence guid(...).
resource stateWriter 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(state.id, stateWriterPrincipalId, storageBlobDataContributor)
  scope: state
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributor)
    principalId: stateWriterPrincipalId
    principalType: stateWriterPrincipalType
  }
}

// Also an extension resource: nobody, Owners included, can delete the account (and with it
// every state file) until this lock is removed.
resource noDelete 'Microsoft.Authorization/locks@2020-05-01' = {
  name: 'no-delete-terraform-state'
  scope: state
  properties: {
    level: 'CanNotDelete'
    notes: 'Holds Terraform state for every environment. Remove the lock only to retire it.'
  }
}

output storageAccountName string = state.name
output containerName string = container.name
