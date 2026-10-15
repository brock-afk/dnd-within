// Module of main.bicep: offsite database backups, in rg-dndwithin-shared. Backups on the VM's
// own disk die with the VM.
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param project string = 'dndwithin'

@description('The VM\'s identity, which uploads backups and downloads them for restores.')
param vmPrincipalId string

@description('Days a backup can\'t be changed or deleted, by anyone.')
param immutableDays int = 14

@description('Days until a backup is deleted. Must be longer than immutableDays.')
param keepDays int = 35

param tags object = {
  project: project
  environment: 'prod'
}

var blobDataContributorRole = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

// Same suffix as the registry, so scripts can name it without a lookup.
resource account 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'st${project}${take(uniqueString(resourceGroup().id), 6)}'
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_GRS' // a second copy in the paired region
  }
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    // Entra ID only: no account keys or SAS tokens to leak.
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    // A compromised VM (which can write here) still can't delete or overwrite a recent backup.
    // Unlocked so it can be tuned; locking is permanent.
    immutableStorageWithVersioning: {
      enabled: true
      immutabilityPolicy: {
        immutabilityPeriodSinceCreationInDays: immutableDays
        state: 'Unlocked'
        allowProtectedAppendWrites: false
      }
    }
  }
}

resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: account
  name: 'default'
  properties: {
    isVersioningEnabled: true // required by version-level immutability
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobs
  name: 'db-backups'
  properties: {
    publicAccess: 'None'
  }
}

resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: account
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'expire-backups'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: ['blockBlob']
              prefixMatch: ['db-backups/']
            }
            actions: {
              baseBlob: {
                delete: {
                  daysAfterCreationGreaterThan: keepDays
                }
              }
              version: {
                delete: {
                  daysAfterCreationGreaterThan: keepDays
                }
              }
            }
          }
        }
      ]
    }
  }
}

resource vmBackupWriter 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(container.id, vmPrincipalId, blobDataContributorRole)
  scope: container
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributorRole)
    principalId: vmPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output accountName string = account.name
