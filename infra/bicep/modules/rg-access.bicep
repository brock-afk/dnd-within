// Role-assignment rights are limited to the listed roles: unlimited, the identity could grant
// itself Owner.
targetScope = 'resourceGroup'

param principalId string

@description('Role definition GUIDs the identity may assign and remove here.')
param assignableRoleIds array

var contributorRole = 'b24988ac-6180-42a0-ab88-20f7382dd24c'
var rbacAdminRole = 'f58310d9-a9f6-439a-9e8d-f62e7b41a168'

var roles = '{${join(assignableRoleIds, ', ')}}'
var condition = '((!(ActionMatches{\'Microsoft.Authorization/roleAssignments/write\'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals ${roles})) AND ((!(ActionMatches{\'Microsoft.Authorization/roleAssignments/delete\'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals ${roles}))'

resource contributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, principalId, contributorRole)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', contributorRole)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource rbacAdmin 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, principalId, rbacAdminRole)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', rbacAdminRole)
    principalId: principalId
    principalType: 'ServicePrincipal'
    condition: condition
    conditionVersion: '2.0'
  }
}
