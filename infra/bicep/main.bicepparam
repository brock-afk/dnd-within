using 'main.bicep'

param location = 'centralus'
param project = 'dndwithin'
param githubRepo = 'brock-afk@53913816/dnd-within@1413773531'
param sshSourceAddress = '' // set on the command line: -p sshSourceAddress=<ip>/32
param sshPublicKey = '' // set on the command line: -p sshPublicKey="$(cat ~/.ssh/dndwithin-vm.pub)"
