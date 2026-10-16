// Module of main.bicep: Azure Backup for the VM, in rg-dndwithin-shared so the backups outlive
// rg-dndwithin-iaas. Covers the whole machine, including what only exists on it (.env,
// content-private); the logical dumps in backup.bicep remain the portable, per-table copy.
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param project string = 'dndwithin'

param vmId string
param vmName string
param vmResourceGroupName string

@description('Daily restore points kept.')
param retentionDays int = 14

param tags object = {
  project: project
  environment: 'prod'
}

// The same instant every day; Azure only uses the time of day.
var backupTime = '2026-01-01T03:30:00Z'

resource vault 'Microsoft.RecoveryServices/vaults@2024-04-01' = {
  name: 'rsv-${project}'
  location: location
  tags: tags
  sku: {
    name: 'RS0'
    tier: 'Standard'
  }
  properties: {
    publicNetworkAccess: 'Enabled'
    securitySettings: {
      softDeleteSettings: {
        softDeleteState: 'Enabled'
        softDeleteRetentionPeriodInDays: 14
      }
    }
    // Job failures raise Azure Monitor alerts (routed by monitoring.bicep); the older vault-only
    // email alerts would only duplicate them.
    monitoringSettings: {
      azureMonitorAlertSettings: {
        alertsForAllJobFailures: 'Enabled'
      }
      classicAlertSettings: {
        alertsForCriticalOperations: 'Disabled'
      }
    }
    // Can't be changed once anything is protected, so it's set before the first backup. Only
    // through the vault itself: once set here, the backupstorageconfig API refuses changes.
    redundancySettings: {
      standardTierStorageRedundancy: 'GeoRedundant'
      crossRegionRestore: 'Disabled'
    }
  }
}

// Enhanced (V2): the only kind that supports Trusted Launch VMs, and Azure's current default.
resource policy 'Microsoft.RecoveryServices/vaults/backupPolicies@2024-04-01' = {
  parent: vault
  name: 'daily-vm'
  properties: {
    backupManagementType: 'AzureIaasVM'
    policyType: 'V2'
    timeZone: 'UTC'
    // Snapshots kept next to the disks for fast restores; older restore points come from the vault.
    instantRpRetentionRangeInDays: 2
    // Azure Backup creates this group itself for the snapshots. It has to stay unlocked, or old
    // snapshots can't be cleaned up and backups start failing.
    instantRPDetails: {
      azureBackupRGNamePrefix: 'rg-${project}-backup-snapshots-'
    }
    schedulePolicy: {
      schedulePolicyType: 'SimpleSchedulePolicyV2'
      scheduleRunFrequency: 'Daily'
      dailySchedule: {
        scheduleRunTimes: [backupTime]
      }
    }
    retentionPolicy: {
      retentionPolicyType: 'LongTermRetentionPolicy'
      dailySchedule: {
        retentionTimes: [backupTime]
        retentionDuration: {
          count: retentionDays
          durationType: 'Days'
        }
      }
    }
  }
}

var container = 'iaasvmcontainer;iaasvmcontainerv2;${vmResourceGroupName};${vmName}'

resource protectedVm 'Microsoft.RecoveryServices/vaults/backupFabrics/protectionContainers/protectedItems@2024-04-01' = {
  name: '${vault.name}/Azure/${container}/vm;iaasvmcontainerv2;${vmResourceGroupName};${vmName}'
  properties: {
    protectedItemType: 'Microsoft.Compute/virtualMachines'
    policyId: policy.id
    sourceResourceId: vmId
  }
}

output vaultName string = vault.name
