// Container registry for the app image. Deployed into rg-dndwithin-shared.
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param project string = 'dndwithin'

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

output registryName string = registry.name
output loginServer string = registry.properties.loginServer
