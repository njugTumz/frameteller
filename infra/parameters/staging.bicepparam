using '../main.bicep'

param environmentName = 'staging'
param location = 'eastus2'
param allowedOrigins = 'http://localhost:5173' // the Vite dev server; add the staging frontend once it exists
param mediaRetentionDays = 30

// Set by the deploy pipeline from its environment; never written in this file.
param containerImage = readEnvironmentVariable('CONTAINER_IMAGE')
param modelApiKey = readEnvironmentVariable('MODEL_API_KEY')
