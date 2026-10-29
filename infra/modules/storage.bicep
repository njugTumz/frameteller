// Private blob storage for media and project documents. Only Entra ID (managed identity) can read or write.

param location string
param tags object
param accountName string
@description('Delete media, project documents, share links and quota counters this many days after their last change; 0 keeps them.')
param mediaRetentionDays int

resource account 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false // no account keys or SAS from keys: identity only
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Enabled'
  }
}

resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: account
  name: 'default'
}

resource media 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobs
  name: 'media'
  properties: { publicAccess: 'None' }
}

resource projects 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobs
  name: 'projects'
  properties: { publicAccess: 'None' }
}

resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = if (mediaRetentionDays > 0) {
  parent: account
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'delete-after-retention'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: ['blockBlob']
              prefixMatch: ['media/', 'projects/'] // the privacy page promises deletion after 30 days
            }
            actions: {
              baseBlob: { delete: { daysAfterModificationGreaterThan: mediaRetentionDays } }
            }
          }
        }
      ]
    }
  }
}

output accountName string = account.name
