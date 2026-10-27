// Frameteller backend: one resource group per environment (CLAUDE.md section 7).
// Deploy: az deployment group create -g rg-frameteller-<env> -f infra/main.bicep -p infra/parameters/<env>.bicepparam
// MODEL_API_KEY and CONTAINER_IMAGE come from the deploying shell's environment (the pipeline), never from files.

targetScope = 'resourceGroup'

@allowed(['staging', 'production'])
param environmentName string

@description('Everything in one region: close to the Meta Model API and to US judges.')
param location string = 'eastus2'

@description('Backend image, e.g. ghcr.io/<owner>/frameteller-backend:<commit sha>.')
param containerImage string

@secure()
@description('Meta Model API key, stored only as a Container App secret.')
param modelApiKey string

@description('Comma-separated browser origins allowed for CORS and the live session WebSocket.')
param allowedOrigins string

@description('Delete media blobs older than this many days; 0 keeps them.')
@minValue(0)
param mediaRetentionDays int = 0

var tags = {
  project: 'frameteller'
  env: environmentName
}
var suffix = 'frameteller-${environmentName}'

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    location: location
    tags: tags
    suffix: suffix
  }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    location: location
    tags: tags
    // Globally unique, 3-24 lowercase letters and digits.
    accountName: 'stft${take(environmentName, 4)}${take(uniqueString(resourceGroup().id), 10)}'
    mediaRetentionDays: mediaRetentionDays
  }
}

module app 'modules/containerapp.bicep' = {
  name: 'containerapp'
  params: {
    location: location
    tags: tags
    environmentName: environmentName
    suffix: suffix
    containerImage: containerImage
    modelApiKey: modelApiKey
    allowedOrigins: allowedOrigins
    storageAccountName: storage.outputs.accountName
    logAnalyticsWorkspaceName: monitoring.outputs.workspaceName
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
  }
}

module access 'modules/storage-access.bicep' = {
  name: 'storage-access'
  params: {
    storageAccountName: storage.outputs.accountName
    principalId: app.outputs.principalId
  }
}

output appName string = app.outputs.name
output appUrl string = 'https://${app.outputs.fqdn}'
output storageAccountName string = storage.outputs.accountName
