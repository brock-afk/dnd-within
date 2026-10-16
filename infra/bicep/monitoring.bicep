// Module of main.bicep: alerting, in rg-dndwithin-shared. Three signals, each emailed through
// one action group: the site is down, a VM backup job failed, or no database backup was uploaded
// in a day.
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param project string = 'dndwithin'

@description('Where alerts are emailed. Comes from a repository variable, so it stays out of git.')
param alertEmail string

@description('Public hostname the uptime test checks.')
param siteHost string

@description('Standard tests are billed per run (about $8/month at 5 locations every 15 minutes); off costs nothing.')
param uptimeTestEnabled bool = true

param backupAccountName string

param tags object = {
  project: project
  environment: 'prod'
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${project}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    // A runaway log source can't run up a bill; normal volume is a few MB a day.
    workspaceCapping: {
      dailyQuotaGb: json('0.5')
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${project}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
  }
}

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-${project}'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: project
    enabled: true
    emailReceivers: [
      {
        name: 'admin'
        emailAddress: alertEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

// --- Site down ------------------------------------------------------------------------------

// From outside Azure's network path to the VM, so it covers DNS, the NSG, Caddy, the certificate,
// the app and the database in one check.
resource uptimeTest 'Microsoft.Insights/webtests@2022-06-15' = {
  name: 'webtest-${project}-healthz'
  location: location
  // Links the test to App Insights; deployment fails without it.
  tags: union(tags, {
    'hidden-link:${appInsights.id}': 'Resource'
  })
  kind: 'standard'
  properties: {
    SyntheticMonitorId: 'webtest-${project}-healthz'
    Name: 'healthz'
    Enabled: uptimeTestEnabled
    Kind: 'standard'
    Frequency: 900
    Timeout: 30
    // A failure only counts after three attempts in a row, so one dropped request doesn't alert.
    RetryEnabled: true
    // Five, so the alert can require three: one location's network trouble isn't an outage. All in
    // the US, where the players are.
    Locations: [
      { Id: 'us-fl-mia-edge' }
      { Id: 'us-va-ash-azr' }
      { Id: 'us-tx-sn1-azr' }
      { Id: 'us-il-ch1-azr' }
      { Id: 'us-ca-sjc-azr' }
    ]
    Request: {
      RequestUrl: 'https://${siteHost}/healthz'
      HttpVerb: 'GET'
      ParseDependentRequests: false
    }
    ValidationRules: {
      ExpectedHttpStatusCode: 200
      ContentValidation: {
        ContentMatch: 'ok'
        PassIfTextFound: true
        IgnoreCase: false
      }
      // Caddy renews automatically; this catches it failing to, a week before browsers would.
      SSLCheck: true
      SSLCertRemainingLifetimeCheck: 7
    }
  }
}

resource siteDown 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alert-${project}-site-down'
  location: 'global'
  tags: union(tags, {
    'hidden-link:${appInsights.id}': 'Resource'
    'hidden-link:${uptimeTest.id}': 'Resource'
  })
  properties: {
    description: 'The site failed its health check from at least 3 of 5 locations.'
    severity: 1
    enabled: uptimeTestEnabled
    scopes: [
      uptimeTest.id
      appInsights.id
    ]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria'
      webTestId: uptimeTest.id
      componentId: appInsights.id
      failedLocationCount: 3
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
}

// --- VM backup failed -----------------------------------------------------------------------

// The vault raises these alerts itself (vm-backup.bicep); this only decides who hears about them.
resource backupAlertRouting 'Microsoft.AlertsManagement/actionRules@2021-08-08' = {
  name: 'apr-${project}-backup'
  location: 'global'
  tags: tags
  properties: {
    description: 'Email Azure Backup alerts from the vaults in this group.'
    enabled: true
    scopes: [
      resourceGroup().id
    ]
    conditions: [
      {
        field: 'TargetResourceType'
        operator: 'Equals'
        values: ['Microsoft.RecoveryServices/vaults']
      }
    ]
    actions: [
      {
        actionType: 'AddActionGroups'
        actionGroupIds: [actionGroup.id]
      }
    ]
  }
}

// --- No database backup uploaded ------------------------------------------------------------

resource backupAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: backupAccountName
}

resource backupBlobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  parent: backupAccount
  name: 'default'
}

// Writes only: the upload is the event the alert looks for, and reads would just add volume.
resource backupBlobLogs 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-${workspace.name}'
  scope: backupBlobs
  properties: {
    workspaceId: workspace.id
    logs: [
      {
        category: 'StorageWrite'
        enabled: true
      }
    ]
  }
}

// Catches every way the daily backup can silently stop: the timer, the dump, or the upload.
resource noBackup 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = {
  name: 'alert-${project}-no-db-backup'
  location: location
  tags: tags
  kind: 'LogAlert'
  properties: {
    displayName: 'No database backup in 24 hours'
    description: 'Nothing was uploaded to the db-backups container in the last day.'
    severity: 2
    enabled: true
    scopes: [
      workspace.id
    ]
    evaluationFrequency: 'PT1H'
    windowSize: 'P1D'
    criteria: {
      allOf: [
        {
          query: 'StorageBlobLogs | where OperationName in ("PutBlob", "PutBlockList") and StatusText == "Success" and Uri has "/db-backups/"'
          timeAggregation: 'Count'
          operator: 'LessThan'
          threshold: 1
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    // The table only exists once the first log arrives, so validating it at deploy would fail.
    skipQueryValidation: true
    autoMitigate: true
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
  dependsOn: [backupBlobLogs]
}
