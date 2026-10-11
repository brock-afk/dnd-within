// The identity GitHub Actions logs in as, through OIDC, and its roles. Deployed into
// rg-dndwithin-shared, after acr.bicep.
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param project string = 'dndwithin'

@description('The repo as it appears in GitHub\'s OIDC subject (owner@id/name@id).')
param githubRepo string

param tags object = {
  project: project
  environment: 'prod'
}

var readerRole = 'acdd72a7-3385-48ef-bd42-f606fba81ae7'
var acrPushRole = '8311e382-0749-4cb8-b61a-304f252e45ec'

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${project}-github'
  location: location
  tags: tags
}

// Only workflow runs on main can log in.
resource githubMain 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: identity
  name: 'github-main'
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    subject: 'repo:${githubRepo}:ref:refs/heads/main'
    audiences: [
      'api://AzureADTokenExchange'
    ]
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: 'cr${project}${take(uniqueString(resourceGroup().id), 6)}'
}

resource reader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, identity.id, readerRole)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', readerRole)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource acrPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, acrPushRole)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPushRole)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// GitHub Actions variables: AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID.
output clientId string = identity.properties.clientId
output tenantId string = tenant().tenantId
output subscriptionId string = subscription().subscriptionId
