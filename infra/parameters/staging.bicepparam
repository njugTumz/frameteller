using '../main.bicep'

param environmentName = 'staging'
param location = 'eastus2'
// The staging studio (its Static Web App) and the Vite dev server.
param allowedOrigins = 'https://wonderful-field-0efc7e10f.3.azurestaticapps.net,http://localhost:5173'
param publicAppUrl = 'https://wonderful-field-0efc7e10f.3.azurestaticapps.net'
param staticWebAppName = 'swa-frameteller-app-staging'
param mediaRetentionDays = 30

// Set by the deploy pipeline from its environment; never written in this file.
param containerImage = readEnvironmentVariable('CONTAINER_IMAGE')
param modelApiKey = readEnvironmentVariable('MODEL_API_KEY')
// The continuity supervisor's Glimmer endpoint: a GitHub environment variable and secret, both optional.
param glimmerBaseUrl = readEnvironmentVariable('GLIMMER_BASE_URL', '')
param glimmerApiKey = readEnvironmentVariable('GLIMMER_API_KEY', '')
