using './main.bicep'

param location = readEnvironmentVariable('AZURE_LOCATION', 'eastus2')
param searchLocation = readEnvironmentVariable('AZURE_SEARCH_LOCATION', 'centralus')
param resourceGroupName = readEnvironmentVariable('AZURE_RESOURCE_GROUP', 'provider-managed-rg')
param foundryProjectName = readEnvironmentVariable('AZURE_AI_PROJECT_NAME', 'provider-managed')
param principalId = readEnvironmentVariable('AZURE_PRINCIPAL_ID', '')
param principalType = readEnvironmentVariable('AZURE_PRINCIPAL_TYPE', 'User')
param namePrefix = 'entlifecyc'

param deployments = [
  {
    name: 'gpt-5.4-mini'
    model: {
      format: 'OpenAI'
      name: 'gpt-5.4-mini'
      version: '2026-03-17'
    }
    sku: {
      name: 'GlobalStandard'
      capacity: 10
    }
  }
]

param searchServices = {
  shared: {
    name: 'entlifecyc-shared-srch'
  }
  development: {
    name: 'entlifecyc-dev-srch'
  }
  humanResources: {
    name: 'entlifecyc-hr-srch'
  }
  marketing: {
    name: 'entlifecyc-mkt-srch'
  }
}

param tags = {
  repository: 'enterprise-agent-lifecycle'
  component: 'foundry-iq'
  securityBoundaryCount: '4'
}
