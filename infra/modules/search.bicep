@description('Azure AI Search service name.')
@minLength(2)
@maxLength(60)
param name string

@description('Deployment location.')
param location string

@description('Tags applied to the service.')
param tags object = {}

@description('Object ID that provisions Search objects and index content after deployment.')
param provisionerPrincipalId string = ''

@description('Principal type used for provisioning role assignments.')
@allowed([
  'User'
  'Group'
  'ServicePrincipal'
])
param provisionerPrincipalType string = 'User'

var searchServiceContributorRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
)
var searchIndexDataContributorRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
)

resource searchService 'Microsoft.Search/searchServices@2023-11-01' = {
  name: name
  location: location
  sku: {
    name: 'basic'
  }
  identity: {
    type: 'SystemAssigned'
  }
  tags: tags
  properties: {
    replicaCount: 1
    partitionCount: 1
    semanticSearch: 'free'
    disableLocalAuth: true
    publicNetworkAccess: 'enabled'
  }
}

resource provisionerSearchServiceContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(provisionerPrincipalId)) {
  name: guid(searchService.id, provisionerPrincipalId, searchServiceContributorRoleId)
  scope: searchService
  properties: {
    principalId: provisionerPrincipalId
    principalType: provisionerPrincipalType
    roleDefinitionId: searchServiceContributorRoleId
  }
}

resource provisionerSearchIndexDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(provisionerPrincipalId)) {
  name: guid(searchService.id, provisionerPrincipalId, searchIndexDataContributorRoleId)
  scope: searchService
  properties: {
    principalId: provisionerPrincipalId
    principalType: provisionerPrincipalType
    roleDefinitionId: searchIndexDataContributorRoleId
  }
}

output name string = searchService.name
output endpoint string = 'https://${searchService.name}.search.windows.net'
output principalId string = searchService.identity.principalId
output resourceId string = searchService.id
