using '../main.bicep'

// Production: the public studio at https://app.frameteller.com, the API at https://api.frameteller.com.
param environmentName = 'production'
param location = 'eastus2'
// The marketing page at frameteller.com reads the public gallery (its newest and featured stories).
param allowedOrigins = 'https://app.frameteller.com,https://frameteller.com'
param publicAppUrl = 'https://app.frameteller.com'
param staticWebAppName = 'swa-frameteller-app-prod'
param mediaRetentionDays = 30 // the privacy page promises deletion after 30 days

// One always-on replica: no cold starts during the demo and judging (ADR 0009 keeps it at most one).
param minReplicas = 1
param terminationGracePeriodSeconds = 120
// 2 vCPU and 4 GiB (ADR 0016): two exports render at once beside the live sessions; measured in docs/load-test.md.
param backendCpu = '2'
param backendMemory = '4Gi'
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
// "Read it to me" (ADR 0015): optional; without it the studio offers narration and the teleprompter only.
param azureSpeechKey = readEnvironmentVariable('AZURE_SPEECH_KEY', '')
// The judge pass and the admin page (ADR 0016, 0017): our own random tokens, GitHub environment secrets.
param judgeToken = readEnvironmentVariable('JUDGE_TOKEN', '')
param adminToken = readEnvironmentVariable('ADMIN_TOKEN', '')
