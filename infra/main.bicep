targetScope = 'resourceGroup'

// Local search module is intentionally used because a verifiable current AVM version
// could not be resolved in this execution context without guessing.

@description('Azure region for all Azure AI Search security boundaries.')
param location string = resourceGroup().location

@description('Prefix used for deterministic naming in tags and fallback naming logic.')
@minLength(3)
@maxLength(20)
param namePrefix string

@description('Search boundary definitions. Foundry project/model/agents are intentionally managed only by azure.yaml infra.provider=microsoft.foundry.')
param searchServices array

@description('Optional tags applied to search services.')
param tags object = {}

var mergedTags = union(tags, {
  managedBy: 'bicep'
  workload: 'foundry-iq'
  namePrefix: namePrefix
})

module searchBoundaryModules 'modules/search.bicep' = [for search in searchServices: {
  name: 'search-${search.boundary}'
  params: {
    name: search.name
    location: location
    tags: mergedTags
  }
}]

output searchEndpoints array = [
  for (search, index) in searchServices: {
    boundary: search.boundary
    endpoint: searchBoundaryModules[index].outputs.endpoint
  }
]
