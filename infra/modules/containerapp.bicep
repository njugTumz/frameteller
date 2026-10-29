// The backend: one Container App on a consumption environment (ADR 0009: at most one replica).

param location string
param tags object
param environmentName string
param suffix string
param containerImage string
@secure()
param modelApiKey string
param reviewer string
param glimmerBaseUrl string
@secure()
param glimmerApiKey string
param allowedOrigins string
param publicAppUrl string
param storageAccountName string
param logAnalyticsWorkspaceName string
param appInsightsConnectionString string
@description('Always-on replicas: 1 in production (no cold starts during judging), 0 in staging. Never above 1 (ADR 0009).')
@minValue(0)
@maxValue(1)
param minReplicas int
@description('Seconds a replacing revision waits before stopping the old one: a live session or export can finish.')
param terminationGracePeriodSeconds int
@description('Director model. Never a -contributor model outside local runs (the settings refuse it).')
param directorModel string
@description('Custom domain for the API, e.g. api.frameteller.com. Empty: only the default hostname.')
param customDomain string
@description('Managed certificate for customDomain in the environment, created once by `az containerapp hostname bind`.')
param customDomainCertificateName string
@description('Extra settings as name/value pairs, e.g. guardrail limits.')
param extraEnv array = []

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsWorkspaceName
}

resource managedEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${suffix}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

resource certificate 'Microsoft.App/managedEnvironments/managedCertificates@2024-03-01' existing = if (!empty(customDomainCertificateName)) {
  parent: managedEnv
  name: customDomainCertificateName
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${suffix}'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: managedEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto' // HTTP/1.1 with Upgrade, so the live session WebSocket works
        allowInsecure: false
        customDomains: empty(customDomain) || empty(customDomainCertificateName) ? [] : [
          {
            name: customDomain
            bindingType: 'SniEnabled'
            certificateId: certificate.id
          }
        ]
      }
      secrets: concat([
        {
          name: 'model-api-key'
          value: modelApiKey
        }
      ], empty(glimmerApiKey) ? [] : [
        {
          name: 'glimmer-api-key'
          value: glimmerApiKey
        }
      ])
    }
    template: {
      terminationGracePeriodSeconds: terminationGracePeriodSeconds
      containers: [
        {
          name: 'backend'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat([
            { name: 'APP_ENV', value: environmentName }
            { name: 'DIRECTOR_MODEL', value: directorModel }
            { name: 'MODEL_API_KEY', secretRef: 'model-api-key' }
            { name: 'STORAGE_BACKEND', value: 'blob' }
            { name: 'AZURE_STORAGE_ACCOUNT', value: storageAccountName }
            { name: 'ALLOWED_ORIGINS', value: allowedOrigins }
            { name: 'PUBLIC_APP_URL', value: publicAppUrl }
            { name: 'LOG_LEVEL', value: 'INFO' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'REVIEWER', value: reviewer }
            { name: 'GLIMMER_BASE_URL', value: glimmerBaseUrl }
          ], empty(glimmerApiKey) ? [] : [
            { name: 'GLIMMER_API_KEY', secretRef: 'glimmer-api-key' }
          ], extraEnv)
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/healthz', port: 8000 }
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/readyz', port: 8000 } // writes a tiny blob: checks the identity and storage
              initialDelaySeconds: 5
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Startup'
              httpGet: { path: '/healthz', port: 8000 }
              periodSeconds: 3
              failureThreshold: 20
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: 1 // in-process job queue and live sessions (ADR 0009)
      }
    }
  }
}

output name string = app.name
output fqdn string = app.properties.configuration.ingress.fqdn
output principalId string = app.identity.principalId
output environmentName string = managedEnv.name
output customDomainVerificationId string = managedEnv.properties.customDomainConfiguration.customDomainVerificationId
