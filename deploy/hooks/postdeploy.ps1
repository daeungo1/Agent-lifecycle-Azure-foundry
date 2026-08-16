$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = Join-Path $PWD 'src'

New-Item -ItemType Directory -Force artifacts | Out-Null
python -m lifecycle_ops.provisioning.rbac `
    --report-path artifacts/rbac.json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m lifecycle_ops.provisioning.continuous_eval `
    > artifacts/continuous-evaluation.json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
