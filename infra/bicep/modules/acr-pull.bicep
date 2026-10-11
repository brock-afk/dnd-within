// AcrPull on the shared registry. A module so it can be deployed into rg-dndwithin-shared from
// templates in other resource groups.
targetScope = 'resourceGroup'

param project string
param principalId string

var acrPullRole = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: 'cr${project}${take(uniqueString(resourceGroup().id), 6)}'
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, principalId, acrPullRole)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRole)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}
