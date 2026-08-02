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

    & azd ai connection --help --no-prompt *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "The current azd installation does not support 'azd ai connection'. Install/upgrade azd AI extensions before running this script."
    }
}

function Normalize-ConnectionName {
    param([string]$Value)

    if (-not $Value) {
        return ""
    }

    $trimmed = $Value.Trim()
    if ($trimmed.Contains("/")) {
        $parts = $trimmed.TrimEnd("/") -split "/"
        return $parts[-1]
    }

    return $trimmed
}

function Add-ConnectionNamesFromNode {
    param(
        [object]$Node,
        [System.Collections.Generic.HashSet[string]]$Set
    )

    if ($null -eq $Node) {
        return
    }

    if ($Node -is [System.Collections.IDictionary]) {
        if ($Node.Contains("project_connection_id")) {
            $name = Normalize-ConnectionName -Value ([string]$Node["project_connection_id"])
            if ($name) {
                [void]$Set.Add($name)
            }
        }

        if ($Node.Contains("connections") -and $Node["connections"] -is [System.Collections.IEnumerable]) {
            foreach ($entry in $Node["connections"]) {
                if ($entry -is [System.Collections.IDictionary] -and $entry.Contains("name")) {
                    $name = Normalize-ConnectionName -Value ([string]$entry["name"])
                    if ($name) {
                        [void]$Set.Add($name)
                    }
                }
                elseif ($entry -is [string]) {
                    $name = Normalize-ConnectionName -Value $entry
                    if ($name) {
                        [void]$Set.Add($name)
                    }
                }
            }
        }

        foreach ($value in $Node.Values) {
            Add-ConnectionNamesFromNode -Node $value -Set $Set
        }
        return
    }

    if ($Node -is [System.Collections.IEnumerable] -and -not ($Node -is [string])) {
        foreach ($item in $Node) {
            Add-ConnectionNamesFromNode -Node $item -Set $Set
        }
    }
}

function Get-ToolboxConnectionNames {
    param([object]$ToolboxShow)

    $set = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    Add-ConnectionNamesFromNode -Node $ToolboxShow -Set $set
    return @($set)
}

function Add-EndpointCandidatesFromNode {
    param(
        [object]$Node,
        [System.Collections.Generic.List[string]]$Candidates
    )

    if ($null -eq $Node) {
        return
    }

    if ($Node -is [System.Collections.IDictionary]) {
        foreach ($pair in $Node.GetEnumerator()) {
            $key = [string]$pair.Key
            $value = $pair.Value
            if ($value -is [string] -and $value) {
                $k = $key.ToLowerInvariant()
                if ($k -eq "endpoint" -or $k -eq "mcpendpoint" -or $k -eq "mcp_endpoint" -or $k -eq "url") {
                    $Candidates.Add($value)
                }
            }
            Add-EndpointCandidatesFromNode -Node $value -Candidates $Candidates
        }
        return
    }

    if ($Node -is [System.Collections.IEnumerable] -and -not ($Node -is [string])) {
        foreach ($item in $Node) {
            Add-EndpointCandidatesFromNode -Node $item -Candidates $Candidates
        }
    }
}

function Resolve-ToolboxEndpoint {
    param(
        [object]$ToolboxShow,
        [string]$ToolboxName,
        [string]$ProjectEndpoint
    )

    $candidates = [System.Collections.Generic.List[string]]::new()
    Add-EndpointCandidatesFromNode -Node $ToolboxShow -Candidates $candidates
    if ($candidates.Count -gt 0) {
        return [string]$candidates[0]
    }

    if ($ProjectEndpoint -and $ToolboxName) {
        $base = $ProjectEndpoint.TrimEnd("/")
        return "$base/toolboxes/$ToolboxName/mcp?api-version=v1"
    }

    return ""
}

function Add-VersionCandidatesFromNode {
    param(
        [object]$Node,
        [System.Collections.Generic.List[string]]$Candidates
    )

    if ($null -eq $Node) {
        return
    }

    if ($Node -is [System.Collections.IDictionary]) {
        foreach ($key in @("version", "id", "name")) {
            if ($Node.Contains($key)) {
                $value = [string]$Node[$key]
                if ($value) {
                    $Candidates.Add($value)
                    break
                }
            }
        }

        foreach ($value in $Node.Values) {
            Add-VersionCandidatesFromNode -Node $value -Candidates $Candidates
        }
        return
    }

    if ($Node -is [System.Collections.IEnumerable] -and -not ($Node -is [string])) {
        foreach ($item in $Node) {
            Add-VersionCandidatesFromNode -Node $item -Candidates $Candidates
        }
    }
}

function Get-LatestToolboxVersion {
    param([string]$ToolboxName)

    $versions = Invoke-AzdJson -Args @("ai", "toolbox", "versions", "list", $ToolboxName, "--output", "json", "--no-prompt")
    $candidates = [System.Collections.Generic.List[string]]::new()
    Add-VersionCandidatesFromNode -Node $versions -Candidates $candidates

    if ($candidates.Count -eq 0) {
        throw "Unable to identify latest toolbox version for '$ToolboxName'."
    }

    return [string]$candidates[$candidates.Count - 1]
}

function Publish-LatestToolboxVersion {
    param([string]$ToolboxName)

    $version = Get-LatestToolboxVersion -ToolboxName $ToolboxName
    Write-Status -Level "INFO" -Message "Publishing toolbox version: $ToolboxName $version"
    if ($WhatIfOnly) {
        return
    }

    Invoke-AzdRaw -Args @("ai", "toolbox", "publish", $ToolboxName, $version, "--no-prompt") | Out-Null
}

function Get-ExpectedToolboxConnections {
    param([string]$ToolboxFile)

    if (-not (Test-Path $ToolboxFile)) {
        throw "Toolbox file not found: $ToolboxFile"
    }

    $names = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($line in Get-Content $ToolboxFile) {
        if ($line -match '^\s*-\s*name:\s*([^\s#]+)') {
            [void]$names.Add($matches[1])
        }
    }

    if ($names.Count -eq 0) {
        throw "No connection names found in toolbox file: $ToolboxFile"
    }

    return @($names)
}

function ensure_exact_connection_set {
    param(
        [string]$ToolboxName,
        [string[]]$Expected,
        [string[]]$Actual
    )

    $expectedSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $actualSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($name in $Expected) { [void]$expectedSet.Add($name) }
    foreach ($name in $Actual) { [void]$actualSet.Add($name) }

    $missing = @($expectedSet | Where-Object { -not $actualSet.Contains($_) } | Sort-Object)
    $extra = @($actualSet | Where-Object { -not $expectedSet.Contains($_) } | Sort-Object)

    if ($missing.Count -gt 0 -or $extra.Count -gt 0) {
        throw "Toolbox '$ToolboxName' connection drift detected. missing=[$($missing -join ', ')] extra=[$($extra -join ', ')]. Resolve drift before continuing."
    }
}

function Get-ConnectionField {
    param(
        [object]$Connection,
        [string[]]$Names
    )

    foreach ($name in $Names) {
        if ($Connection -is [System.Collections.IDictionary] -and $Connection.Contains($name) -and $Connection[$name]) {
            return [string]$Connection[$name]
        }
    }

    return ""
}

function Ensure-RemoteToolConnection {
    param(
        [string]$ConnectionName,
        [string]$Target
    )

    $connections = Invoke-AzdJson -Args @("ai", "connection", "list", "--output", "json", "--no-prompt")
    $exists = $false
    if ($connections) {
        foreach ($conn in $connections) {
            if ($conn.name -eq $ConnectionName) {
                $exists = $true
                break
            }
        }
    }

    if (-not $exists) {
        Write-Status -Level "INFO" -Message "Creating connection $ConnectionName"
        if ($WhatIfOnly) {
            return
        }

        Invoke-AzdRaw -Args @(
            "ai", "connection", "create", $ConnectionName,
            "--kind", "remote-tool",
            "--target", $Target,
            "--auth-type", "agentic-identity",
            "--audience", "https://search.azure.com",
            "--no-prompt"
        ) | Out-Null
        return
    }

    $details = Invoke-AzdJson -Args @("ai", "connection", "show", $ConnectionName, "--output", "json", "--no-prompt")
    if ($null -eq $details) {
        throw "Connection '$ConnectionName' exists but details could not be loaded with 'azd ai connection show'. Resolve manually and rerun."
    }

    $kind = (Get-ConnectionField -Connection $details -Names @("kind", "category")).ToLowerInvariant()
    $targetActual = Get-ConnectionField -Connection $details -Names @("target", "endpoint", "url")
    $authType = (Get-ConnectionField -Connection $details -Names @("authType", "auth_type")).ToLowerInvariant()
    $audience = Get-ConnectionField -Connection $details -Names @("audience")

    $drift = @()
    if ($kind -ne "remote-tool") { $drift += "kind='$kind' expected='remote-tool'" }
    if ($targetActual -ne $Target) { $drift += "target='$targetActual' expected='$Target'" }
    if ($authType -ne "agentic-identity") { $drift += "authType='$authType' expected='agentic-identity'" }
    if ($audience -ne "https://search.azure.com") { $drift += "audience='$audience' expected='https://search.azure.com'" }

    if ($drift.Count -gt 0) {
        throw "Connection '$ConnectionName' drift detected. $($drift -join '; '). Fix the connection manually or remove/recreate it, then rerun."
    }

    Write-Status -Level "OK" -Message "Verified connection $ConnectionName"
}

function Upsert-Toolbox {
    param(
        [string]$ToolboxName,
        [string]$ToolboxFile,
        [string]$EndpointEnvName,
        [string]$ProjectEndpoint
    )

    $expected = Get-ExpectedToolboxConnections -ToolboxFile $ToolboxFile
    $expectedSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($name in $expected) {
        [void]$expectedSet.Add($name)
    }

    $showResult = $null
    try {
        $showResult = Invoke-AzdJson -Args @("ai", "toolbox", "show", $ToolboxName, "--output", "json", "--no-prompt")
    }
    catch {
        $showResult = $null
    }

    if ($showResult) {
        Write-Status -Level "INFO" -Message "Toolbox exists, reconciling connections: $ToolboxName"

        $current = Get-ToolboxConnectionNames -ToolboxShow $showResult

        $missing = @($expectedSet | Where-Object { $current -notcontains $_ } | Sort-Object)
        foreach ($name in $missing) {
            Write-Status -Level "INFO" -Message "Adding missing connection '$name' to toolbox '$ToolboxName'"
            if (-not $WhatIfOnly) {
                Invoke-AzdRaw -Args @("ai", "toolbox", "connection", "add", $ToolboxName, $name, "--no-prompt") | Out-Null
                Publish-LatestToolboxVersion -ToolboxName $ToolboxName
            }
            $showResult = Invoke-AzdJson -Args @("ai", "toolbox", "show", $ToolboxName, "--output", "json", "--no-prompt")
            $current = Get-ToolboxConnectionNames -ToolboxShow $showResult
        }

        $extra = @($current | Where-Object { -not $expectedSet.Contains($_) } | Sort-Object)
        foreach ($name in $extra) {
            if ($current.Count -le 1) {
                throw "Refusing to remove '$name' from '$ToolboxName' because toolbox cannot be left with zero tools."
            }

            Write-Status -Level "INFO" -Message "Removing extra connection '$name' from toolbox '$ToolboxName'"
            if (-not $WhatIfOnly) {
                Invoke-AzdRaw -Args @("ai", "toolbox", "connection", "remove", $ToolboxName, $name, "--no-prompt") | Out-Null
                Publish-LatestToolboxVersion -ToolboxName $ToolboxName
            }
            $showResult = Invoke-AzdJson -Args @("ai", "toolbox", "show", $ToolboxName, "--output", "json", "--no-prompt")
            $current = Get-ToolboxConnectionNames -ToolboxShow $showResult
        }

        ensure_exact_connection_set -ToolboxName $ToolboxName -Expected $expected -Actual $current
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

    if (-not $WhatIfOnly) {
        $published = Invoke-AzdJson -Args @("ai", "toolbox", "show", $ToolboxName, "--output", "json", "--no-prompt")
        $actual = Get-ToolboxConnectionNames -ToolboxShow $published
        ensure_exact_connection_set -ToolboxName $ToolboxName -Expected $expected -Actual $actual

        $endpoint = Resolve-ToolboxEndpoint -ToolboxShow $published -ToolboxName $ToolboxName -ProjectEndpoint $ProjectEndpoint
        if (-not $endpoint) {
            throw "Unable to resolve toolbox endpoint for '$ToolboxName'."
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

$projectEndpoint = ""
if ($envValues.ContainsKey("FOUNDRY_PROJECT_ENDPOINT")) {
    $projectEndpoint = [string]$envValues["FOUNDRY_PROJECT_ENDPOINT"]
}

Ensure-RemoteToolConnection -ConnectionName "kb-shared-remote-tool" -Target $envValues["KB_MCP_ENDPOINT_SHARED"]
Ensure-RemoteToolConnection -ConnectionName "kb-development-remote-tool" -Target $envValues["KB_MCP_ENDPOINT_DEVELOPMENT"]
Ensure-RemoteToolConnection -ConnectionName "kb-human-resources-remote-tool" -Target $envValues["KB_MCP_ENDPOINT_HUMAN_RESOURCES"]
Ensure-RemoteToolConnection -ConnectionName "kb-marketing-remote-tool" -Target $envValues["KB_MCP_ENDPOINT_MARKETING"]

Upsert-Toolbox -ToolboxName "development-knowledge-toolbox" -ToolboxFile "toolboxes/development.yaml" -EndpointEnvName "TOOLBOX_ENDPOINT_DEVELOPMENT" -ProjectEndpoint $projectEndpoint
Upsert-Toolbox -ToolboxName "human-resources-knowledge-toolbox" -ToolboxFile "toolboxes/human-resources.yaml" -EndpointEnvName "TOOLBOX_ENDPOINT_HUMAN_RESOURCES" -ProjectEndpoint $projectEndpoint
Upsert-Toolbox -ToolboxName "marketing-knowledge-toolbox" -ToolboxFile "toolboxes/marketing.yaml" -EndpointEnvName "TOOLBOX_ENDPOINT_MARKETING" -ProjectEndpoint $projectEndpoint

Write-Status -Level "OK" -Message "Toolbox configuration completed."
