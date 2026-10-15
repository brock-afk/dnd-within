// Module of main.bicep: VNet, subnet with an NSG, and the VM's public IP, in rg-dndwithin-iaas.
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param project string = 'dndwithin'

@description('Public IP (CIDR) allowed to SSH in, e.g. 203.0.113.7/32. Passed at deploy time.')
param sshSourceAddress string

@description('DNS label: <label>.<region>.cloudapp.azure.com. Must be unique in the region.')
param dnsLabel string = project

param tags object = {
  project: project
  environment: 'prod'
}

resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-${project}-app'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowHttp' // Let's Encrypt challenge and redirect to HTTPS
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '80'
        }
      }
      {
        name: 'AllowHttps'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowSshFromAdmin'
        properties: {
          priority: 120
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: sshSourceAddress
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '22'
        }
      }
    ]
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-${project}-iaas'
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.10.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'snet-app'
        properties: {
          addressPrefix: '10.10.1.0/24'
          networkSecurityGroup: {
            id: nsg.id
          }
        }
      }
    ]
  }
}

resource publicIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: 'pip-${project}-app'
  location: location
  tags: tags
  sku: {
    name: 'Standard' // closed to inbound traffic unless an NSG allows it
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    dnsSettings: {
      domainNameLabel: dnsLabel
    }
  }
}

output subnetId string = vnet.properties.subnets[0].id
output publicIpId string = publicIp.id
output fqdn string = publicIp.properties.dnsSettings.fqdn
