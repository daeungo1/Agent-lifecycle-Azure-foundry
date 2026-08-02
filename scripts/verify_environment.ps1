$ErrorActionPreference = "Stop"

param(
    [ValidateSet("provision", "deploy")]
    [string]$Phase = "provision"
)

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

function Parse-AzdEnvValues {
    param([string]$RawValues)

    $values = @{}
    foreach ($line in $RawValues -split "`n") {
        $trimmed = $line.Trim()
        if (-not $trimmed -or -not $trimmed.Contains("=")) {
            continue
        }
        $parts = $trimmed.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim().Trim("\"").Trim("'")
        $values[$key] = $value
    }

    return $values
}

function Test-RequiredEnvVars {
    param(
        [hashtable]$Values,
        [string[]]$RequiredNames,
        [string]$Context
    )

    $ok = $true
    foreach ($name in $RequiredNames) {
        if ($Values.ContainsKey($name) -and $Values[$name]) {
            Write-Status -Level "OK" -Message "[$Context] $name is set in azd env."
        }
        else {
            Write-Status -Level "ACTION" -Message "[$Context] Missing required azd env value: $name"
            $ok = $false
        }
    }
    return $ok
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

        $envValues = Parse-AzdEnvValues -RawValues $envOutput
        $searchVars = @(
            "FOUNDRYIQ_SEARCH_ENDPOINT_SHARED",
            "FOUNDRYIQ_SEARCH_ENDPOINT_DEVELOPMENT",
            "FOUNDRYIQ_SEARCH_ENDPOINT_HUMAN_RESOURCES",
            "FOUNDRYIQ_SEARCH_ENDPOINT_MARKETING"
        )
        $toolboxVars = @(
            "TOOLBOX_ENDPOINT_DEVELOPMENT",
            "TOOLBOX_ENDPOINT_HUMAN_RESOURCES",
            "TOOLBOX_ENDPOINT_MARKETING"
        )

        if ($Phase -eq "provision") {
            if (-not (Test-RequiredEnvVars -Values $envValues -RequiredNames $searchVars -Context "provision")) {
                $hasError = $true
            }
        }

        if ($Phase -eq "deploy") {
            if (-not (Test-RequiredEnvVars -Values $envValues -RequiredNames $toolboxVars -Context "deploy")) {
                $hasError = $true
            }
        }
    }
    else {
        Write-Status -Level "WARN" -Message "Unable to read azd environment values; verify azd environment selection manually."
    }
}

if ($hasError) {
    exit 1
}

exit 0
