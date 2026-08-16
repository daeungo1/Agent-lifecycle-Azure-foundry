$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = Join-Path $PWD 'src'

New-Item -ItemType Directory -Force artifacts | Out-Null
python -m lifecycle_ops.provisioning.rbac `
    --report-path artifacts/rbac.json
python -m lifecycle_ops.provisioning.continuous_eval |
    Out-File -FilePath artifacts/continuous-evaluation.json -Encoding utf8
