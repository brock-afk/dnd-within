// Module of bootstrap.bicep: the identities GitHub Actions logs in as, through OIDC, in
// rg-dndwithin-shared. One per job so each holds only its own rights.
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param project string = 'dndwithin'

@description('The repo as it appears in GitHub\'s OIDC subject (owner@id/name@id).')
param githubRepo string

param tags object = {
  project: project
  environment: 'prod'
}

var issuer = 'https://token.actions.githubusercontent.com'
var audiences = ['api://AzureADTokenExchange']
var readerRole = 'acdd72a7-3385-48ef-bd42-f606fba81ae7'

resource app 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${project}-github'
  location: location
  tags: tags
}

resource appMain 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: app
  name: 'github-main'
  properties: {
    issuer: issuer
    subject: 'repo:${githubRepo}:ref:refs/heads/main'
    audiences: audiences
  }
}

// `az acr login` looks the registry up through ARM.
resource appReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, app.id, readerRole)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', readerRole)
    principalId: app.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource infra 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${project}-infra'
  location: location
  tags: tags
}

resource infraMain 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: infra
  name: 'github-main'
  properties: {
    issuer: issuer
    subject: 'repo:${githubRepo}:ref:refs/heads/main'
    audiences: audiences
  }
}

// Runs what-if for pull requests. A PR runs the PR's own copy of the workflow, so this one is
// read-only.
resource whatIf 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${project}-whatif'
  location: location
  tags: tags
}

resource whatIfPr 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: whatIf
  name: 'github-pr'
  properties: {
    issuer: issuer
    subject: 'repo:${githubRepo}:pull_request'
    audiences: audiences
  }
}

output appPrincipalId string = app.properties.principalId
output appClientId string = app.properties.clientId
output infraPrincipalId string = infra.properties.principalId
output infraClientId string = infra.properties.clientId
output whatIfPrincipalId string = whatIf.properties.principalId
output whatIfClientId string = whatIf.properties.clientId
