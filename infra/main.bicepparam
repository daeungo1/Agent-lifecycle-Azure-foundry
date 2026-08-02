using './main.bicep'

param location = 'eastus2'
param namePrefix = 'entlifecyc'

param searchServices = [
  {
    boundary: 'shared'
    name: 'entlifecyc-shared-srch'
  }
  {
    boundary: 'development'
    name: 'entlifecyc-dev-srch'
  }
  {
    boundary: 'human-resources'
    name: 'entlifecyc-hr-srch'
  }
  {
    boundary: 'marketing'
    name: 'entlifecyc-mkt-srch'
  }
]

param tags = {
  repository: 'enterprise-agent-lifecycle'
  component: 'foundry-iq'
  securityBoundaryCount: '4'
}
