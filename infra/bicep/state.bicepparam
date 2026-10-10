using 'state.bicep'

param project = 'dndwithin'

// Your Entra ID object ID (az ad signed-in-user show --query id). Gets read/write on the state
// blobs. An identifier, not a secret.
param stateWriterPrincipalId = '39ffa7ab-e910-48a0-b358-57c98163d44c'
param stateWriterPrincipalType = 'User'
