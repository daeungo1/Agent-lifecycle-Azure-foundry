$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = Join-Path $PWD 'src'

New-Item -ItemType Directory -Force artifacts | Out-Null
python -m lifecycle_ops.provisioning.observability `
    --output artifacts/observability.json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m lifecycle_ops.provisioning.knowledge_bases `
    --output artifacts/knowledge-bases.json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m lifecycle_ops.provisioning.toolboxes
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
