// Module of main.bicep: Ubuntu arm64 VM running the app with Docker Compose, in rg-dndwithin-iaas.
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param project string = 'dndwithin'

@description('SSH public key for azureuser. Passed at deploy time.')
param sshPublicKey string

param vmSize string = 'Standard_B2pts_v2'

@description('Admin user; cloud-init.yaml adds it to the docker group.')
param adminUsername string = 'azureuser'

param subnetId string
param publicIpId string
param registryName string
param sharedResourceGroupName string

@description('The app pipeline\'s identity, which gets the deploy role on this VM.')
param ciIdentityId string
param ciPrincipalId string

@description('The VM Deployer custom role, from bootstrap.bicep.')
param vmDeployerRoleId string

param tags object = {
  project: project
  environment: 'prod'
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
            id: subnetId
          }
          privateIPAllocationMethod: 'Dynamic'
          publicIPAddress: {
            id: publicIpId
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
  scope: resourceGroup(sharedResourceGroupName)
  params: {
    registryName: registryName
    principalId: vm.identity.principalId
  }
}

// GitHub Actions deploys by running a script on the VM (az vm run-command); the custom role
// allows only that.
resource ciDeployer 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vm.id, ciIdentityId, 'vm-deployer')
  scope: vm
  properties: {
    roleDefinitionId: vmDeployerRoleId
    principalId: ciPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output vmId string = vm.id
output vmName string = vm.name
output principalId string = vm.identity.principalId
