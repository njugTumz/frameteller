using '../main.bicep'

// Not deployed yet: production follows staging (CLAUDE.md section 7).
param environmentName = 'production'
param location = 'eastus2'
param allowedOrigins = ''
param staticWebAppName = 'swa-frameteller-app-prod'
param mediaRetentionDays = 0

param containerImage = readEnvironmentVariable('CONTAINER_IMAGE')
param modelApiKey = readEnvironmentVariable('MODEL_API_KEY')
