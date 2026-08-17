// Provisioning template for a Foundry project service.
//
// Inputs are derived from the host: azure.ai.project service body in
// azure.yaml by internal/synthesis. Greenfield only (no endpoint:); a
// brownfield path is handled by the provider before synthesis.
//
// Subscription-scoped so the resource group is part of the deployment. This
// keeps `azd provision --preview` side-effect free: the resource group shows
// up as a previewed Create instead of being created up front to satisfy a
// resource-group-scoped what-if.

targetScope = 'subscription'

// User-defined types

@description('Shape of one model deployment entry in azure.yaml.')
type deploymentsType = deploymentType[]

@description('Shape of a single model deployment.')
type deploymentType = {
  name: string
  model: {
    name: string
    format: string
    version: string
  }
  sku: {
    name: string
    capacity: int
  }
}

@description('Shape of a list of Foundry project connections.')
type connectionsType = connectionType[]

@description('Shape of one Foundry project connection (a host: azure.ai.connection service).')
type connectionType = {
  name: string
  category: string
  target: string
  authType: string
  metadata: object?
}

type SearchBoundaryConfig = {
  name: string
}

// Parameters

@description('Azure region for all resources.')
param location string

@description('Azure region for the department-isolated Search services.')
param searchLocation string = location

@description('Name of the resource group to create and deploy resources into.')
@minLength(1)
@maxLength(90)
param resourceGroupName string = 'provider-managed-rg'

@description('Tags applied to all resources.')
param tags object = {}

@description('Optional salt to vary resource names across re-provisions.')
param resourceTokenSalt string = ''

@description('Foundry project name. 3-32 alphanumeric/hyphen chars.')
@minLength(3)
@maxLength(32)
param foundryProjectName string = 'provider-managed'

@description('Model deployments to provision on the Foundry account.')
param deployments deploymentsType = []

@description('Container registry is disabled because every Hosted Agent uses direct code deployment.')
@allowed([false])
param includeAcr bool = false

@description('Foundry project connections to create (host: azure.ai.connection services).')
param connections connectionsType = []

@description('Credentials keyed by Foundry project connection name.')
@secure()
param connectionCredentials object = {}

@description('Object id of the developer running azd. When set, grants Cognitive Services User on the project. Empty disables the role assignment so headless / CI runs do not fail.')
param principalId string = ''

@description('Principal type used in the developer role assignment.')
param principalType string = 'User'

@description('Prefix used for deterministic naming and resource tags.')
@minLength(3)
@maxLength(20)
param namePrefix string

@description('Azure AI Search service definitions keyed by security boundary.')
param searchServices {
  shared: SearchBoundaryConfig
  development: SearchBoundaryConfig
  humanResources: SearchBoundaryConfig
  marketing: SearchBoundaryConfig
}

// Network isolation parameters (see modules/resources.bicep for semantics).
// All default off so an absent network: block yields a public account.

@description('Master switch: when true the account is VNet-bound (private).')
param enableNetworkIsolation bool = false

@description('When true (and isolation on), the agent runtime uses the Microsoft-managed network instead of injecting into a customer subnet.')
param useManagedEgress bool = false

@description('ARM id of the existing customer VNet (byo mode).')
param vnetId string = ''

@description('Agent (delegated) subnet name.')
param agentSubnetName string = 'agent-subnet'

@description('Agent subnet CIDR. Empty derives a /24 from the VNet space.')
param agentSubnetPrefix string = ''

@description('When true, create the agent subnet; when false, reference it.')
param createAgentSubnet bool = false

@description('Private-endpoint subnet name.')
param peSubnetName string = 'pe-subnet'

@description('Private-endpoint subnet CIDR. Empty derives a /24 from the VNet space.')
param peSubnetPrefix string = ''

@description('When true, create the PE subnet; when false, reference it.')
param createPESubnet bool = false

@description('Managed-network isolation mode (managed mode).')
param managedIsolationMode string = ''

@description('Resource group holding existing private DNS zones. Empty creates new zones.')
param dnsZonesResourceGroup string = ''

@description('Subscription holding existing private DNS zones. Empty defaults to this subscription.')
param dnsZonesSubscription string = ''

var searchTags = union(tags, {
  managedBy: 'bicep'
  workload: 'foundry-iq'
  namePrefix: namePrefix
})
var searchNameSuffix = uniqueString(subscription().id, resourceGroupName, searchLocation)

// Resources

resource resourceGroup 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module resources 'modules/resources.bicep' = {
  name: 'foundry-resources'
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    resourceTokenSalt: resourceTokenSalt
    foundryProjectName: foundryProjectName
    deployments: deployments
    includeAcr: includeAcr
    connections: connections
    connectionCredentials: connectionCredentials
    principalId: principalId
    principalType: principalType
    enableNetworkIsolation: enableNetworkIsolation
    useManagedEgress: useManagedEgress
    vnetId: vnetId
    agentSubnetName: agentSubnetName
    agentSubnetPrefix: agentSubnetPrefix
    createAgentSubnet: createAgentSubnet
    peSubnetName: peSubnetName
    peSubnetPrefix: peSubnetPrefix
    createPESubnet: createPESubnet
    managedIsolationMode: managedIsolationMode
    dnsZonesResourceGroup: dnsZonesResourceGroup
    dnsZonesSubscription: dnsZonesSubscription
  }
}

module searchShared 'modules/search.bicep' = {
  name: 'search-shared'
  scope: resourceGroup
  params: {
    name: '${searchServices.shared.name}-${searchNameSuffix}'
    location: searchLocation
    tags: searchTags
    provisionerPrincipalId: principalId
    provisionerPrincipalType: principalType
  }
}

module searchDevelopment 'modules/search.bicep' = {
  name: 'search-development'
  scope: resourceGroup
  params: {
    name: '${searchServices.development.name}-${searchNameSuffix}'
    location: searchLocation
    tags: searchTags
    provisionerPrincipalId: principalId
    provisionerPrincipalType: principalType
  }
}

module searchHumanResources 'modules/search.bicep' = {
  name: 'search-human-resources'
  scope: resourceGroup
  params: {
    name: '${searchServices.humanResources.name}-${searchNameSuffix}'
    location: searchLocation
    tags: searchTags
    provisionerPrincipalId: principalId
    provisionerPrincipalType: principalType
  }
}

module searchMarketing 'modules/search.bicep' = {
  name: 'search-marketing'
  scope: resourceGroup
  params: {
    name: '${searchServices.marketing.name}-${searchNameSuffix}'
    location: searchLocation
    tags: searchTags
    provisionerPrincipalId: principalId
    provisionerPrincipalType: principalType
  }
}

// Outputs

output AZURE_RESOURCE_GROUP string = resourceGroup.name
output AZURE_AI_PROJECT_ID string = resources.outputs.AZURE_AI_PROJECT_ID
output AZURE_AI_ACCOUNT_NAME string = resources.outputs.AZURE_AI_ACCOUNT_NAME
output AZURE_AI_PROJECT_NAME string = resources.outputs.AZURE_AI_PROJECT_NAME
output AZURE_OPENAI_ENDPOINT string = resources.outputs.AZURE_OPENAI_ENDPOINT
output FOUNDRY_PROJECT_ENDPOINT string = resources.outputs.FOUNDRY_PROJECT_ENDPOINT
output AZURE_AI_PROJECT_ENDPOINT string = resources.outputs.FOUNDRY_PROJECT_ENDPOINT
output AZURE_AI_MODEL_DEPLOYMENT_NAME string = length(deployments) > 0 ? deployments[0].name : ''
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.AZURE_CONTAINER_REGISTRY_ENDPOINT
output AZURE_CONTAINER_REGISTRY_RESOURCE_ID string = resources.outputs.AZURE_CONTAINER_REGISTRY_RESOURCE_ID
output AZURE_AI_PROJECT_ACR_CONNECTION_NAME string = resources.outputs.AZURE_AI_PROJECT_ACR_CONNECTION_NAME
output AZURE_AI_PROJECT_CONNECTION_NAMES string = resources.outputs.AZURE_AI_PROJECT_CONNECTION_NAMES
output AZURE_FOUNDRY_NETWORK_MODE string = resources.outputs.AZURE_FOUNDRY_NETWORK_MODE
output AZURE_FOUNDRY_MANAGED_ISOLATION_MODE string = resources.outputs.AZURE_FOUNDRY_MANAGED_ISOLATION_MODE

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
