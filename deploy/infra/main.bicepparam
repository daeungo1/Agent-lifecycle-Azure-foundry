using './main.bicep'

param location = 'eastus2'
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
