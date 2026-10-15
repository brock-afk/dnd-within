// Module of main.bicep: the app's secrets, in rg-dndwithin-shared. The deploy writes .env from
// here, so a rebuilt VM needs no hand-made file. Secret values are set by hand
// (az keyvault secret set), never in a template, so they stay out of git and deployment history.
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param project string = 'dndwithin'

@description('The VM\'s identity, which reads the secrets at deploy.')
param vmPrincipalId string

param tags object = {
  project: project
  environment: 'prod'
}

var secretsUserRole = '4633458b-17de-408a-b874-0445c86b69e6'

// Same suffix as the registry and backup account, so scripts can name it without a lookup.
resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${project}-${take(uniqueString(resourceGroup().id), 6)}'
  location: location
  tags: tags
  properties: {
    tenantId: tenant().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    // Azure RBAC, not access policies: one permission model for everything.
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    // Deleted secrets can't be purged early by anyone. Irreversible once on.
    enablePurgeProtection: true
  }
}

resource vmSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, vmPrincipalId, secretsUserRole)
  scope: vault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsUserRole)
    principalId: vmPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output vaultName string = vault.name
