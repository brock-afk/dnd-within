// Run by hand, not by CI: everything that decides what the pipelines may do. If the pipeline
// deployed this, it could widen its own rights.
targetScope = 'subscription'

@description('Region for every resource, and the only one policy allows.')
param location string = 'centralus'

@description('Short project name, used in every resource name.')
param project string = 'dndwithin'

@description('The repo as it appears in GitHub\'s OIDC subject (owner@id/name@id).')
param githubRepo string

param tags object = {
  project: project
  environment: 'prod'
}

var readerRole = 'acdd72a7-3385-48ef-bd42-f606fba81ae7'
var acrPushRole = '8311e382-0749-4cb8-b61a-304f252e45ec'
var acrPullRole = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var blobDataContributorRole = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var vmDeployerRole = guid(subscription().id, project, 'vm-deployer')

// Resource groups are one per lifecycle: "shared" lasts, "iaas" holds the VM.
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

module vmDeployer 'modules/vm-deployer-role.bicep' = {
  name: 'vm-deployer-role-${project}'
  params: {
    project: project
    resourceGroupName: iaasRg.name
  }
}

module identities 'identities.bicep' = {
  name: 'identities'
  scope: sharedRg
  params: {
    project: project
    githubRepo: githubRepo
    tags: tags
  }
}

// A subscription-scope deployment needs rights at the subscription, but ARM still checks every
// resource it creates against the caller's own roles, so this grants nothing else.
resource deploymentRunner 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(subscription().id, project, 'deployment-runner')
  properties: {
    roleName: 'Deployment Runner (${project})'
    description: 'Create subscription-scope deployments.'
    type: 'CustomRole'
    permissions: [
      {
        actions: [
          'Microsoft.Resources/deployments/*'
          'Microsoft.Resources/subscriptions/resourceGroups/read'
        ]
      }
    ]
    assignableScopes: [
      subscription().id
    ]
  }
}

// Reader can see everything what-if compares against, but can't start one.
resource whatIfRunner 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(subscription().id, project, 'what-if-runner')
  properties: {
    roleName: 'What-If Runner (${project})'
    description: 'Preview deployments without changing anything.'
    type: 'CustomRole'
    permissions: [
      {
        actions: [
          'Microsoft.Resources/deployments/whatIf/action'
          'Microsoft.Resources/deployments/validate/action'
        ]
      }
    ]
    assignableScopes: [
      subscription().id
    ]
  }
}

resource infraRunner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, 'infra', deploymentRunner.id)
  properties: {
    roleDefinitionId: deploymentRunner.id
    principalId: identities.outputs.infraPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource whatIfReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, 'whatif', readerRole)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', readerRole)
    principalId: identities.outputs.whatIfPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource whatIfRunnerAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, 'whatif', whatIfRunner.id)
  properties: {
    roleDefinitionId: whatIfRunner.id
    principalId: identities.outputs.whatIfPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Only the roles main.bicep assigns.
module sharedAccess 'modules/rg-access.bicep' = {
  name: 'infra-access-shared'
  scope: sharedRg
  params: {
    principalId: identities.outputs.infraPrincipalId
    assignableRoleIds: [acrPushRole, acrPullRole, blobDataContributorRole]
  }
}

module iaasAccess 'modules/rg-access.bicep' = {
  name: 'infra-access-iaas'
  scope: iaasRg
  params: {
    principalId: identities.outputs.infraPrincipalId
    assignableRoleIds: [vmDeployerRole]
  }
  dependsOn: [vmDeployer]
}

// Owner manages resources but can't read blob data. Whoever runs bootstrap gets it, to upload
// dumps for restores and download backups.
module adminBlobData 'modules/user-role.bicep' = {
  name: 'admin-blob-data'
  scope: sharedRg
  params: {
    principalId: deployer().objectId
    roleId: blobDataContributorRole
  }
}

module sharedLock 'modules/rg-lock.bicep' = {
  name: 'lock-shared'
  scope: sharedRg
}

module iaasLock 'modules/rg-lock.bicep' = {
  name: 'lock-iaas'
  scope: iaasRg
}

// GitHub Actions variables.
output AZURE_CLIENT_ID string = identities.outputs.appClientId
output AZURE_INFRA_CLIENT_ID string = identities.outputs.infraClientId
output AZURE_WHATIF_CLIENT_ID string = identities.outputs.whatIfClientId
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_SUBSCRIPTION_ID string = subscription().subscriptionId
