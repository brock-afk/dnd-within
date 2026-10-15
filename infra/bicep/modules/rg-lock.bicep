// Blocks deleting the group or anything in it, for everyone including Owner, until the lock
// itself is removed. Locks need Microsoft.Authorization rights, so the pipeline can't remove them.
targetScope = 'resourceGroup'

resource lock 'Microsoft.Authorization/locks@2020-05-01' = {
  name: 'do-not-delete'
  properties: {
    level: 'CanNotDelete'
    notes: 'Remove only to tear the group down on purpose.'
  }
}
