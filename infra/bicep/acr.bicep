// Module of main.bicep: container registry for the app image, in rg-dndwithin-shared.
targetScope = 'resourceGroup'

import { identityRef } from 'types.bicep'

param location string = resourceGroup().location
param project string = 'dndwithin'

@description('Identities that push images: the app pipeline builds them, the release pipeline retags them.')
param pushers identityRef[]

param tags object = {
  project: project
  environment: 'prod'
}

// Globally unique, 5-50 letters and digits only.
var registryName = 'cr${project}${take(uniqueString(resourceGroup().id), 6)}'

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false // Entra ID and RBAC only
  }
}

var acrPushRole = '8311e382-0749-4cb8-b61a-304f252e45ec'

resource acrPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for pusher in pushers: {
    name: guid(registry.id, pusher.id, acrPushRole)
    scope: registry
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPushRole)
      principalId: pusher.principalId
      principalType: 'ServicePrincipal'
    }
  }
]

output registryName string = registry.name
output loginServer string = registry.properties.loginServer
