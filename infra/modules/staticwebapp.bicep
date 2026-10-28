// The studio frontend: a Static Web App on the Free plan. The frontend workflow uploads the built files with the
// app's deployment token, read at deploy time through Azure RBAC; the token is never stored.

param location string
param tags object
param name string

resource site 'Microsoft.Web/staticSites@2024-04-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    allowConfigFileUpdates: true // routes and headers come from frontend/public/staticwebapp.config.json
    stagingEnvironmentPolicy: 'Enabled'
  }
}

output name string = site.name
output hostname string = site.properties.defaultHostname
