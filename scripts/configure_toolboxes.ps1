$ErrorActionPreference = "Stop"

param(
    [switch]$WhatIfOnly
)

function Write-Status {
    param(
        [string]$Level,
        [string]$Message
    )
    Write-Host "[$Level] $Message"
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

function Invoke-AzdRaw {
    param([string[]]$Args)

    $output = & azd @Args
    if ($LASTEXITCODE -ne 0) {
        throw "azd command failed: azd $($Args -join ' ')"
    }

    return $output
}

function Invoke-AzdJson {
    param([string[]]$Args)

    $raw = Invoke-AzdRaw -Args $Args
    if (-not $raw) {
        return $null
    }

    return ($raw | ConvertFrom-Json)
}

function Ensure-AzdAiToolboxSupport {
    & azd ai toolbox --help --no-prompt *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "The current azd installation does not support 'azd ai toolbox'. Install/upgrade azd AI extensions before running this script."
    }

    & azd ai agent connection --help --no-prompt *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "The current azd installation does not support 'azd ai agent connection'. Install/upgrade azd AI extensions before running this script."
    }
}

function Resolve-ToolboxEndpoint {
    param([object]$ToolboxShow)

    if ($null -eq $ToolboxShow) {
        return ""
    }

    foreach ($field in @("endpoint", "mcpEndpoint", "mcp_endpoint", "url")) {
        $value = $ToolboxShow.$field
        if ($value) {
            return [string]$value
        }
    }

    return ""
}

function Ensure-RemoteToolConnection {
    param(
        [hashtable]$ExistingByName,
        [string]$ConnectionName,
        [string]$Target
    )

    $existing = $ExistingByName[$ConnectionName]
    if ($existing) {
        Write-Status -Level "INFO" -Message "Updating connection $ConnectionName"
        if ($WhatIfOnly) {
            return
        }

        Invoke-AzdRaw -Args @(
            "ai", "agent", "connection", "update", $ConnectionName,
            "--category", "remote-tool",
            "--target", $Target,
            "--auth-type", "agentic-identity",
            "--audience", "https://search.azure.com",
            "--no-prompt"
        ) | Out-Null
        return
    }

    Write-Status -Level "INFO" -Message "Creating connection $ConnectionName"
    if ($WhatIfOnly) {
        return
    }

    Invoke-AzdRaw -Args @(
        "ai", "agent", "connection", "create", $ConnectionName,
        "--category", "remote-tool",
        "--target", $Target,
        "--auth-type", "agentic-identity",
        "--audience", "https://search.azure.com",
        "--no-prompt"
    ) | Out-Null
}

function Upsert-Toolbox {
    param(
        [string]$ToolboxName,
        [string]$ToolboxFile,
        [string]$EndpointEnvName
    )

    $showResult = $null
    try {
        $showResult = Invoke-AzdJson -Args @("ai", "toolbox", "show", $ToolboxName, "--output", "json", "--no-prompt")
    }
    catch {
        $showResult = $null
    }

    if ($showResult) {
        Write-Status -Level "INFO" -Message "Toolbox exists, updating connections: $ToolboxName"
        if (-not $WhatIfOnly) {
            Invoke-AzdRaw -Args @(
                "ai", "toolbox", "connection", "add", $ToolboxName,
                "--from-file", $ToolboxFile,
                "--no-prompt"
            ) | Out-Null
        }
    }
    else {
        Write-Status -Level "INFO" -Message "Creating toolbox: $ToolboxName"
        if (-not $WhatIfOnly) {
            Invoke-AzdRaw -Args @(
                "ai", "toolbox", "create", $ToolboxName,
                "--from-file", $ToolboxFile,
                "--no-prompt"
            ) | Out-Null
        }
    }

    Write-Status -Level "INFO" -Message "Publishing toolbox version: $ToolboxName"
    if (-not $WhatIfOnly) {
        Invoke-AzdRaw -Args @("ai", "toolbox", "publish", $ToolboxName, "--no-prompt") | Out-Null

        $published = Invoke-AzdJson -Args @("ai", "toolbox", "show", $ToolboxName, "--output", "json", "--no-prompt")
        $endpoint = Resolve-ToolboxEndpoint -ToolboxShow $published
        if (-not $endpoint) {
            throw "Unable to resolve toolbox endpoint for $ToolboxName"
        }

        Invoke-AzdRaw -Args @("env", "set", $EndpointEnvName, $endpoint, "--no-prompt") | Out-Null
    }

    Write-Status -Level "OK" -Message "Ensured $EndpointEnvName for toolbox $ToolboxName"
}

if (-not (Get-Command azd -ErrorAction SilentlyContinue)) {
    throw "Azure Developer CLI (azd) is required."
}

Ensure-AzdAiToolboxSupport

$envRaw = Invoke-AzdRaw -Args @("env", "get-values", "--no-prompt")
$envValues = Parse-AzdEnvValues -RawValues $envRaw

$requiredEnv = @(
    "KB_MCP_ENDPOINT_SHARED",
    "KB_MCP_ENDPOINT_DEVELOPMENT",
    "KB_MCP_ENDPOINT_HUMAN_RESOURCES",
    "KB_MCP_ENDPOINT_MARKETING"
)

foreach ($name in $requiredEnv) {
    if (-not $envValues.ContainsKey($name) -or -not $envValues[$name]) {
        throw "Missing required azd environment value: $name"
    }
}

$connections = Invoke-AzdJson -Args @("ai", "agent", "connection", "list", "--output", "json", "--no-prompt")
$connectionByName = @{}
if ($connections) {
    foreach ($conn in $connections) {
        $connectionByName[$conn.name] = $conn
    }
}

Ensure-RemoteToolConnection -ExistingByName $connectionByName -ConnectionName "kb-shared-remote-tool" -Target $envValues["KB_MCP_ENDPOINT_SHARED"]
Ensure-RemoteToolConnection -ExistingByName $connectionByName -ConnectionName "kb-development-remote-tool" -Target $envValues["KB_MCP_ENDPOINT_DEVELOPMENT"]
Ensure-RemoteToolConnection -ExistingByName $connectionByName -ConnectionName "kb-human-resources-remote-tool" -Target $envValues["KB_MCP_ENDPOINT_HUMAN_RESOURCES"]
Ensure-RemoteToolConnection -ExistingByName $connectionByName -ConnectionName "kb-marketing-remote-tool" -Target $envValues["KB_MCP_ENDPOINT_MARKETING"]

Upsert-Toolbox -ToolboxName "development-knowledge-toolbox" -ToolboxFile "toolboxes/development.yaml" -EndpointEnvName "TOOLBOX_ENDPOINT_DEVELOPMENT"
Upsert-Toolbox -ToolboxName "human-resources-knowledge-toolbox" -ToolboxFile "toolboxes/human-resources.yaml" -EndpointEnvName "TOOLBOX_ENDPOINT_HUMAN_RESOURCES"
Upsert-Toolbox -ToolboxName "marketing-knowledge-toolbox" -ToolboxFile "toolboxes/marketing.yaml" -EndpointEnvName "TOOLBOX_ENDPOINT_MARKETING"

Write-Status -Level "OK" -Message "Toolbox configuration completed."
