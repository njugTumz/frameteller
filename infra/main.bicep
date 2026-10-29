// Frameteller backend and studio frontend: one resource group per environment (CLAUDE.md section 7).
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

@description('The studio URL that share links send browsers to. Empty: the first https origin in allowedOrigins.')
param publicAppUrl string = ''

@description('The studio frontend Static Web App.')
param staticWebAppName string

@description('Always-on replicas: 1 in production, 0 (scale to zero) in staging. At most 1 (ADR 0009).')
@minValue(0)
@maxValue(1)
param minReplicas int = 0

@description('Seconds a deploy lets the old revision finish a live session or export before stopping it.')
param terminationGracePeriodSeconds int = 120

@description('Director model: always the standard (paid) model outside local runs, never a -contributor one.')
param directorModel string = 'muse-spark-1.3'

@description('API custom domain, e.g. api.frameteller.com, and its managed certificate in the environment.')
param apiDomain string = ''
param apiCertificateName string = ''

@description('Continuity supervisor reviewer (ADR 0012, 0013): spark, glimmer, fallback or screen (Glimmer, Spark confirms).')
@allowed(['spark', 'glimmer', 'fallback', 'screen'])
param reviewer string = 'spark'

@description('Our Muse Glimmer endpoint on Modal (OpenAI-compatible, ending in /v1). Empty: no Glimmer.')
param glimmerBaseUrl string = ''

@secure()
@description('Bearer token of our Glimmer endpoint (not a Meta key), stored only as a Container App secret.')
param glimmerApiKey string = ''

@secure()
@description('Azure AI Speech key for "Read it to me" (ADR 0015), stored only as a Container App secret. Empty: not offered.')
param azureSpeechKey string = ''

@secure()
@description('The judge pass token (the private judge link), stored only as a Container App secret. Empty: no judge pass.')
param judgeToken string = ''

@secure()
@description('The admin page token (gallery moderation, budgets), stored only as a Container App secret. Empty: no admin API.')
param adminToken string = ''

@description('vCPU and memory of the backend replica (ADR 0016).')
param backendCpu string = '0.5'
param backendMemory string = '1Gi'

@description('Guardrail settings for a public demo, as name/value pairs (see the backend settings).')
param guardrailEnv array = []

@description('Email for budget and availability alerts. Empty: no alerts.')
param alertEmail string = ''
param monthlyBudget int = 0
param budgetStartDate string = '2026-10-01'
@description('URL the availability test probes. Empty: no test.')
param availabilityUrl string = ''

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
    reviewer: reviewer
    glimmerBaseUrl: glimmerBaseUrl
    glimmerApiKey: glimmerApiKey
    azureSpeechKey: azureSpeechKey
    judgeToken: judgeToken
    adminToken: adminToken
    cpu: backendCpu
    memory: backendMemory
    allowedOrigins: allowedOrigins
    publicAppUrl: publicAppUrl
    storageAccountName: storage.outputs.accountName
    logAnalyticsWorkspaceName: monitoring.outputs.workspaceName
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    minReplicas: minReplicas
    terminationGracePeriodSeconds: terminationGracePeriodSeconds
    directorModel: directorModel
    customDomain: apiDomain
    customDomainCertificateName: apiCertificateName
    extraEnv: guardrailEnv
  }
}

module alerts 'modules/alerts.bicep' = if (!empty(alertEmail)) {
  name: 'alerts'
  params: {
    location: location
    tags: tags
    suffix: suffix
    alertEmail: alertEmail
    monthlyBudget: monthlyBudget
    budgetStartDate: budgetStartDate
    availabilityUrl: availabilityUrl
    appInsightsId: monitoring.outputs.appInsightsId
  }
}

module access 'modules/storage-access.bicep' = {
  name: 'storage-access'
  params: {
    storageAccountName: storage.outputs.accountName
    principalId: app.outputs.principalId
  }
}

module frontend 'modules/staticwebapp.bicep' = {
  name: 'staticwebapp'
  params: {
    location: location
    tags: tags
    name: staticWebAppName
  }
}

output appName string = app.outputs.name
output appUrl string = 'https://${app.outputs.fqdn}'
output appFqdn string = app.outputs.fqdn
output containerEnvironmentName string = app.outputs.environmentName
output customDomainVerificationId string = app.outputs.customDomainVerificationId
output storageAccountName string = storage.outputs.accountName
output frontendName string = frontend.outputs.name
output frontendUrl string = 'https://${frontend.outputs.hostname}'
