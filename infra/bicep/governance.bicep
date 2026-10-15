// Module of main.bicep: Azure Policy assignments at the subscription.
targetScope = 'subscription'

@description('The only region policy allows.')
param location string

// Built-in policy definitions have fixed IDs, the same in every tenant.
var allowedLocationsDefinition = '/providers/Microsoft.Authorization/policyDefinitions/e56962a6-4747-49cd-b67b-bf8b01975c4c'
var requireResourceGroupTagDefinition = '/providers/Microsoft.Authorization/policyDefinitions/96670d01-0a4d-4649-9c89-2d3abc0a5025'

// Deny: nothing can be created outside our region. (This built-in skips resource groups and
// "global" resources; there's a separate built-in for resource group locations.)
resource allowedLocations 'Microsoft.Authorization/policyAssignments@2024-04-01' = {
  name: 'allowed-locations'
  properties: {
    displayName: 'Allowed locations: ${location}'
    policyDefinitionId: allowedLocationsDefinition
    parameters: {
      listOfAllowedLocations: {
        value: [
          location
        ]
      }
      // The definition's effect is a parameter (Audit, Deny or Disabled; default Deny). Set it
      // explicitly so this assignment doesn't depend on a default that could change.
      effect: {
        value: 'Deny'
      }
    }
    nonComplianceMessages: [
      {
        message: 'Resources must be created in ${location}.'
      }
    ]
  }
}

// Report resource groups without a project tag, but don't block them: Azure creates some groups
// itself (NetworkWatcherRG), and a hard deny would quietly break that. DoNotEnforce still
// evaluates and reports compliance; it just never denies.
resource requireProjectTag 'Microsoft.Authorization/policyAssignments@2024-04-01' = {
  name: 'require-project-tag-on-rgs'
  properties: {
    displayName: 'Resource groups should have a project tag'
    policyDefinitionId: requireResourceGroupTagDefinition
    enforcementMode: 'DoNotEnforce'
    parameters: {
      tagName: {
        value: 'project'
      }
    }
  }
}
