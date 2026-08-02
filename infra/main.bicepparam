using './main.bicep'

param location = 'eastus2'
param namePrefix = 'entlifecyc'

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
