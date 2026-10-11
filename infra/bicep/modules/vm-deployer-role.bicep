// Custom role: read a VM and run commands on it, nothing else. Role definitions live at
// subscription scope; this one can only be assigned inside the given resource group.
targetScope = 'subscription'

param project string
param resourceGroupName string

resource role 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(subscription().id, project, 'vm-deployer')
  properties: {
    roleName: 'VM Deployer (${project})'
    description: 'Read virtual machines and run commands on them.'
    type: 'CustomRole'
    permissions: [
      {
        actions: [
          'Microsoft.Compute/virtualMachines/read'
          'Microsoft.Compute/virtualMachines/runCommand/action'
        ]
      }
    ]
    assignableScopes: [
      '${subscription().id}/resourceGroups/${resourceGroupName}'
    ]
  }
}

output roleDefinitionId string = role.id
