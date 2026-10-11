// Stage 1 VM: Ubuntu arm64 running the app with Docker Compose. Deployed into rg-dndwithin-iaas,
// after network.bicep.
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param project string = 'dndwithin'

@description('SSH public key for azureuser. Passed at deploy time.')
param sshPublicKey string

param vmSize string = 'Standard_B2pts_v2'

@description('Admin user; cloud-init.yaml adds it to the docker group.')
param adminUsername string = 'azureuser'

param tags object = {
  project: project
  environment: 'prod'
}

resource subnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' existing = {
  name: 'vnet-${project}-iaas/snet-app'
}

resource publicIp 'Microsoft.Network/publicIPAddresses@2024-05-01' existing = {
  name: 'pip-${project}-app'
}

resource nic 'Microsoft.Network/networkInterfaces@2024-05-01' = {
  name: 'nic-${project}-app'
  location: location
  tags: tags
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: {
            id: subnet.id
          }
          privateIPAllocationMethod: 'Dynamic'
          publicIPAddress: {
            id: publicIp.id
          }
        }
      }
    ]
  }
}

resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' = {
  name: 'vm-${project}-app'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server-arm64'
        version: 'latest'
      }
      osDisk: {
        name: 'osdisk-${project}-app'
        createOption: 'FromImage'
        diskSizeGB: 64
        managedDisk: {
          storageAccountType: 'Premium_LRS'
        }
        deleteOption: 'Delete'
      }
      dataDisks: [
        {
          name: 'datadisk-${project}-mysql'
          lun: 0
          createOption: 'Empty'
          diskSizeGB: 64
          managedDisk: {
            storageAccountType: 'Premium_LRS'
          }
          deleteOption: 'Detach' // the database outlives the VM
        }
      ]
    }
    osProfile: {
      computerName: 'vm-${project}-app'
      adminUsername: adminUsername
      customData: base64(loadTextContent('cloud-init.yaml'))
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: sshPublicKey
            }
          ]
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: nic.id
          properties: {
            deleteOption: 'Delete'
          }
        }
      ]
    }
    diagnosticsProfile: {
      bootDiagnostics: {
        enabled: true // managed storage; enables the serial console
      }
    }
  }
}

module acrPull 'modules/acr-pull.bicep' = {
  name: 'acr-pull-${project}-vm'
  scope: resourceGroup('rg-${project}-shared')
  params: {
    project: project
    principalId: vm.identity.principalId
  }
}

// GitHub Actions deploys by running a script on the VM (az vm run-command), with a custom role
// that allows only that.
resource ciIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: 'id-${project}-github'
  scope: resourceGroup('rg-${project}-shared')
}

module deployerRole 'modules/vm-deployer-role.bicep' = {
  name: 'vm-deployer-role-${project}'
  scope: subscription()
  params: {
    project: project
    resourceGroupName: resourceGroup().name
  }
}

resource ciDeployer 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vm.id, ciIdentity.id, 'vm-deployer')
  scope: vm
  properties: {
    roleDefinitionId: deployerRole.outputs.roleDefinitionId
    principalId: ciIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

output vmName string = vm.name
output principalId string = vm.identity.principalId
