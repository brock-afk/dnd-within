// Types shared by main.bicep's modules.

@export()
@description('An identity to grant a role: `id` keeps the role assignment\'s name stable, `principalId` is who gets it.')
type identityRef = {
  id: string
  principalId: string
}
