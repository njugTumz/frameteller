using '../main.bicep'

// Production: the public studio at https://app.frameteller.com, the API at https://api.frameteller.com.
param environmentName = 'production'
param location = 'eastus2'
param allowedOrigins = 'https://app.frameteller.com'
param publicAppUrl = 'https://app.frameteller.com'
param staticWebAppName = 'swa-frameteller-app-prod'
param mediaRetentionDays = 30 // the privacy page promises deletion after 30 days

// One always-on replica: no cold starts during the demo and judging (ADR 0009 keeps it at most one).
param minReplicas = 1
param terminationGracePeriodSeconds = 120
// Standard mode: public users' stories are never used for training (never the -contributor model).
param directorModel = 'muse-spark-1.3'

// Bound once the DNS records exist (docs/runbook.md, "Custom domains").
param apiDomain = 'api.frameteller.com'
param apiCertificateName = readEnvironmentVariable('API_CERTIFICATE_NAME', '')

param alertEmail = 'izotumzybiz@gmail.com'
param monthlyBudget = 50
param availabilityUrl = readEnvironmentVariable('AVAILABILITY_URL', 'https://api.frameteller.com/healthz')

// Set by the deploy pipeline from its environment; never written in this file.
param containerImage = readEnvironmentVariable('CONTAINER_IMAGE')
param modelApiKey = readEnvironmentVariable('MODEL_API_KEY')
// The continuity supervisor (ADR 0013): REVIEWER is a GitHub environment variable (spark here); the Glimmer
// endpoint is a variable and a secret, both optional.
param reviewer = readEnvironmentVariable('REVIEWER', 'spark')
param glimmerBaseUrl = readEnvironmentVariable('GLIMMER_BASE_URL', '')
param glimmerApiKey = readEnvironmentVariable('GLIMMER_API_KEY', '')
