using 'main.bicep'

param location = 'centralus'
param project = 'dndwithin'
// From the environment, so CI (repository variables) and a local shell deploy the same values.
param sshSourceAddress = readEnvironmentVariable('SSH_SOURCE_ADDRESS')
param sshPublicKey = readEnvironmentVariable('SSH_PUBLIC_KEY')
