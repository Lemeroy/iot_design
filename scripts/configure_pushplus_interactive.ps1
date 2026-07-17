$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $Root "cloud\.env"

if (-not (Test-Path -LiteralPath $EnvPath)) {
    throw "cloud environment file not found: $EnvPath"
}

function ConvertTo-ShellLiteral {
    param([Parameter(Mandatory = $true)][string]$Value)
    return "'" + $Value.Replace("'", "'`"'`"'") + "'"
}

function Set-EnvLine {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )
    for ($index = 0; $index -lt $script:EnvLines.Count; $index++) {
        if ($script:EnvLines[$index] -match ("^" + [regex]::Escape($Name) + "=")) {
            $script:EnvLines[$index] = "$Name=$Value"
            return
        }
    }
    $script:EnvLines.Add("$Name=$Value")
}

Write-Host "Enter the PushPlus message token. Input will not be displayed."
$secureToken = Read-Host -AsSecureString
$tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
$plainToken = $null
try {
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
    if ([string]::IsNullOrWhiteSpace($plainToken)) {
        throw "PushPlus token cannot be empty"
    }

    $deviceName = Read-Host "Device display name [StrokeGuard Mirror 1]"
    if ([string]::IsNullOrWhiteSpace($deviceName)) {
        $deviceName = "StrokeGuard Mirror 1"
    }

    $script:EnvLines = [Collections.Generic.List[string]]::new()
    foreach ($line in [IO.File]::ReadAllLines($EnvPath, [Text.Encoding]::UTF8)) {
        $script:EnvLines.Add($line)
    }
    Set-EnvLine -Name "PUSHPLUS_ENABLED" -Value "1"
    Set-EnvLine -Name "PUSHPLUS_TOKEN" -Value (ConvertTo-ShellLiteral $plainToken)
    Set-EnvLine -Name "PUSHPLUS_DEVICE_NAME" -Value (ConvertTo-ShellLiteral $deviceName)

    $temporaryEnv = "$EnvPath.tmp"
    [IO.File]::WriteAllLines(
        $temporaryEnv,
        $script:EnvLines,
        (New-Object Text.UTF8Encoding($false))
    )
    Move-Item -LiteralPath $temporaryEnv -Destination $EnvPath -Force
}
finally {
    if ($tokenPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
    }
    $plainToken = $null
    if ($null -ne $secureToken) {
        $secureToken.Dispose()
    }
}

Write-Host "PushPlus alerts enabled in cloud\.env. The token was not displayed."
