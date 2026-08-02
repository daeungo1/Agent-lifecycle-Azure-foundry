targetScope = 'resourceGroup'

// Local search module is intentionally used because a verifiable current AVM version
// could not be resolved in this execution context without guessing.

@description('Azure region for all Azure AI Search security boundaries.')
param location string = resourceGroup().location

@description('Prefix used for deterministic naming in tags and fallback naming logic.')
@minLength(3)
@maxLength(20)
param namePrefix string

type SearchBoundaryConfig = {
  name: string
}

@description('Search boundary definitions keyed by security boundary. Foundry project/model/agents are intentionally managed only by azure.yaml infra.provider=microsoft.foundry.')
param searchServices {
  shared: SearchBoundaryConfig
  development: SearchBoundaryConfig
  humanResources: SearchBoundaryConfig
  marketing: SearchBoundaryConfig
}

@description('Optional tags applied to search services.')
param tags object = {}

var mergedTags = union(tags, {
  managedBy: 'bicep'
  workload: 'foundry-iq'
  namePrefix: namePrefix
})

module searchShared 'modules/search.bicep' = {
  name: 'search-shared'
  params: {
    name: searchServices.shared.name
    location: location
    tags: mergedTags
  }
}

module searchDevelopment 'modules/search.bicep' = {
  name: 'search-development'
  params: {
    name: searchServices.development.name
    location: location
    tags: mergedTags
  }
}

module searchHumanResources 'modules/search.bicep' = {
  name: 'search-human-resources'
  params: {
    name: searchServices.humanResources.name
    location: location
    tags: mergedTags
  }
}

module searchMarketing 'modules/search.bicep' = {
  name: 'search-marketing'
  params: {
    name: searchServices.marketing.name
    location: location
    tags: mergedTags
  }
}

output searchEndpoints object = {
  shared: searchShared.outputs.endpoint
  development: searchDevelopment.outputs.endpoint
  humanResources: searchHumanResources.outputs.endpoint
  marketing: searchMarketing.outputs.endpoint
}

output FOUNDRYIQ_SEARCH_ENDPOINT_SHARED string = searchShared.outputs.endpoint
output FOUNDRYIQ_SEARCH_ENDPOINT_DEVELOPMENT string = searchDevelopment.outputs.endpoint
output FOUNDRYIQ_SEARCH_ENDPOINT_HUMAN_RESOURCES string = searchHumanResources.outputs.endpoint
output FOUNDRYIQ_SEARCH_ENDPOINT_MARKETING string = searchMarketing.outputs.endpoint

output SEARCH_RESOURCE_ID_SHARED string = searchShared.outputs.resourceId
output SEARCH_RESOURCE_ID_DEVELOPMENT string = searchDevelopment.outputs.resourceId
output SEARCH_RESOURCE_ID_HUMAN_RESOURCES string = searchHumanResources.outputs.resourceId
output SEARCH_RESOURCE_ID_MARKETING string = searchMarketing.outputs.resourceId
