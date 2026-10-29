// Production watch: a monthly budget on the resource group, and an availability test on the API's /healthz
// that emails when two of three locations fail. Created only when alertEmail is set.

param location string
param tags object
param suffix string
param alertEmail string
@description('Monthly budget in USD for this resource group; 0 skips it.')
param monthlyBudget int
@description('First day of the budget period, e.g. 2026-10-01.')
param budgetStartDate string
@description('URL to probe every 5 minutes, e.g. https://api.frameteller.com/healthz. Empty: no availability test.')
param availabilityUrl string
param appInsightsId string

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = if (monthlyBudget > 0) {
  name: 'budget-${suffix}'
  properties: {
    category: 'Cost'
    amount: monthlyBudget
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStartDate }
    notifications: {
      actual80: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: [alertEmail]
      }
      actual100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Actual'
        contactEmails: [alertEmail]
      }
    }
  }
}

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = if (!empty(availabilityUrl)) {
  name: 'ag-${suffix}'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'frameteller'
    enabled: true
    emailReceivers: [
      { name: 'owner', emailAddress: alertEmail, useCommonAlertSchema: true }
    ]
  }
}

resource webTest 'Microsoft.Insights/webtests@2022-06-15' = if (!empty(availabilityUrl)) {
  name: 'avail-${suffix}'
  location: location
  // Availability tests must name the Application Insights resource they report to.
  tags: union(tags, { 'hidden-link:${appInsightsId}': 'Resource' })
  kind: 'standard'
  properties: {
    SyntheticMonitorId: 'avail-${suffix}'
    Name: 'API health'
    Enabled: true
    Frequency: 300
    Timeout: 30
    Kind: 'standard'
    RetryEnabled: true
    Locations: [
      { Id: 'us-va-ash-azr' } // East US
      { Id: 'us-tx-sn1-azr' } // South Central US
      { Id: 'us-ca-sjc-azr' } // West US
    ]
    Request: {
      RequestUrl: availabilityUrl
      HttpVerb: 'GET'
      ParseDependentRequests: false
    }
    ValidationRules: {
      ExpectedHttpStatusCode: 200
      SSLCheck: true
      SSLCertRemainingLifetimeCheck: 7
    }
  }
}

resource availabilityAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = if (!empty(availabilityUrl)) {
  name: 'alert-avail-${suffix}'
  location: 'global'
  tags: tags
  properties: {
    description: 'The API health check failed from at least 2 of 3 locations.'
    severity: 1
    enabled: true
    scopes: [webTest.id, appInsightsId]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria'
      webTestId: webTest.id
      componentId: appInsightsId
      failedLocationCount: 2
    }
    actions: [
      { actionGroupId: actionGroup.id }
    ]
  }
}
