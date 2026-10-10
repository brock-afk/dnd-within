// Step 0.3: governance at the subscription. Resource groups (one per lifecycle) with tags, and
// two built-in Azure Policy assignments. Deployed at subscription scope:
//   az deployment sub what-if -l centralus -f governance.bicep -p governance.bicepparam
targetScope = 'subscription'

@description('Region for every resource, and the only one policy allows.')
param location string = 'centralus'

@description('Short project name, used in every resource name.')
param project string = 'dndwithin'

@description('Tags for the resource groups: what it is, which environment, what manages it.')
param tags object = {
  project: project
  environment: 'prod'
  'managed-by': 'bicep'
}

// One group per lifecycle: "shared" lasts (Terraform state, registry, Key Vault); "iaas" holds
// the Stage 1 VM and is deleted after the move to PaaS. A "paas" group comes in Stage 2.
var resourceGroupNames = [
  'rg-${project}-shared'
  'rg-${project}-iaas'
]

resource groups 'Microsoft.Resources/resourceGroups@2024-03-01' = [for name in resourceGroupNames: {
  name: name
  location: location
  tags: tags
}]

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

output resourceGroupNames array = resourceGroupNames
