// Observability resources for hosted agent tracing.
//
// Deployed by the postprovision hook rather than by `azd provision`: the
// microsoft.foundry provider synthesises its own ARM template containing only the
// Foundry account, project and model deployment, so resources declared in
// main.bicep are never sent to ARM. See docs/operations.md.

@description('Azure region for the observability resources.')
param location string

@description('Application Insights component name.')
@minLength(1)
param applicationInsightsName string

@description('Log Analytics workspace name backing Application Insights.')
@minLength(4)
param logAnalyticsWorkspaceName string

@description('Tags applied to both resources.')
param tags object = {}

@description('Workspace retention in days.')
@minValue(30)
@maxValue(730)
param retentionInDays int = 30

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsWorkspaceName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionInDays
  }
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: applicationInsightsName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspace.id
  }
}

output connectionString string = applicationInsights.properties.ConnectionString
output resourceId string = applicationInsights.id
output name string = applicationInsights.name
output workspaceResourceId string = logAnalyticsWorkspace.id
