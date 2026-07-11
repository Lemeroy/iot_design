$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $Root "cloud\.env"

if (-not (Test-Path $EnvPath)) {
    throw "cloud environment file not found: $EnvPath"
}

Write-Host "Paste the Volcengine Ark API key. Input will not be displayed."
$secureKey = Read-Host -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    if ([string]::IsNullOrWhiteSpace($plainKey)) {
        throw "API key cannot be empty"
    }

    $lines = [Collections.Generic.List[string]]::new()
    $found = $false
    foreach ($line in [IO.File]::ReadAllLines($EnvPath, [Text.Encoding]::UTF8)) {
        if ($line -match '^VOLC_ARK_API_KEY=') {
            $lines.Add("VOLC_ARK_API_KEY=$plainKey")
            $found = $true
        }
        else {
            $lines.Add($line)
        }
    }
    if (-not $found) {
        $lines.Add("VOLC_ARK_API_KEY=$plainKey")
    }
    [IO.File]::WriteAllLines($EnvPath, $lines, [Text.UTF8Encoding]::new($false))
}
finally {
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    $plainKey = $null
    $secureKey.Dispose()
}

Write-Host "VOLC_ARK_API_KEY updated in cloud\.env."
