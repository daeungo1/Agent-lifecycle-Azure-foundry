$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = Join-Path $PWD 'src'

function Invoke-Python {
    param(
        [Parameter(ValueFromRemainingArguments)]
        [string[]]$PythonArguments
    )

    if ($env:PYTHON) {
        & $env:PYTHON @PythonArguments
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python @PythonArguments
    } elseif (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv run --no-project --python 3.13 --prerelease=allow `
            --with-requirements requirements-ops.txt python @PythonArguments
    } elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
        & python3 @PythonArguments
    } else {
        throw 'Python 3.13 or uv is required to run the postdeploy hook.'
    }
}

New-Item -ItemType Directory -Force artifacts | Out-Null
Invoke-Python '-m' 'lifecycle_ops.provisioning.rbac' `
    '--report-path' 'artifacts/rbac.json'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
