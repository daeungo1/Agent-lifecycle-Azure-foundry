$ErrorActionPreference = "Stop"

function Write-Status {
    param(
        [string]$Level,
        [string]$Message
    )
    Write-Host "[$Level] $Message"
}

function Test-CommandExists {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

$hasError = $false

if (Test-CommandExists -Name "az") {
    Write-Status -Level "OK" -Message "Azure CLI is installed."
}
else {
    Write-Status -Level "ACTION" -Message "Azure CLI (az) is not installed."
    $hasError = $true
}

if (Test-CommandExists -Name "azd") {
    Write-Status -Level "OK" -Message "Azure Developer CLI is installed."
}
else {
    Write-Status -Level "ACTION" -Message "Azure Developer CLI (azd) is not installed."
    $hasError = $true
}

$requiredFiles = @(
    "azure.yaml",
    "infra/main.bicep",
    "infra/main.bicepparam",
    "scripts/provision_knowledge_bases.py"
)

foreach ($file in $requiredFiles) {
    if (Test-Path -Path $file) {
        Write-Status -Level "OK" -Message "Found $file"
    }
    else {
        Write-Status -Level "ACTION" -Message "Missing required file $file"
        $hasError = $true
    }
}

if (Test-CommandExists -Name "azd") {
    $envOutput = azd env get-values 2>$null
    if ($LASTEXITCODE -eq 0 -and $envOutput) {
        Write-Status -Level "OK" -Message "Active azd environment values are accessible."
    }
    else {
        Write-Status -Level "WARN" -Message "Unable to read azd environment values; verify azd environment selection manually."
    }
}

if ($hasError) {
    exit 1
}

exit 0
