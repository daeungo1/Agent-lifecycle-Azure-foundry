@description('Azure AI Search service name.')
@minLength(2)
@maxLength(60)
param name string

@description('Deployment location.')
param location string

@description('Tags applied to the service.')
param tags object = {}

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

output name string = searchService.name
output endpoint string = 'https://${searchService.name}.search.windows.net'
output principalId string = searchService.identity.principalId
