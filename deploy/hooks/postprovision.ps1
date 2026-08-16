$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = Join-Path $PWD 'src'

New-Item -ItemType Directory -Force artifacts | Out-Null
python -m lifecycle_ops.provisioning.knowledge_bases `
    --output artifacts/knowledge-bases.json
python -m lifecycle_ops.provisioning.toolboxes
