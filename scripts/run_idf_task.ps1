[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$IdfPath,
    [Parameter(Mandatory = $true)][string]$ProjectPath,
    [Parameter(Mandatory = $true)][ValidateSet("build", "erase", "flash")][string]$Action,
    [string]$OverlayPath = "",
    [string]$Port = ""
)

$ErrorActionPreference = "Stop"
$exportScript = Join-Path $IdfPath "export.ps1"
if (-not (Test-Path -LiteralPath $exportScript -PathType Leaf)) {
    throw "ESP-IDF export.ps1 not found"
}
if (-not (Test-Path -LiteralPath $ProjectPath -PathType Container)) {
    throw "Firmware project not found"
}
if ($Port -and $Port -notmatch '^COM[1-9][0-9]{0,2}$') {
    throw "Invalid COM port"
}

. $exportScript
Push-Location $ProjectPath
try {
    $buildDir = Join-Path $ProjectPath ".strokeguard-build\idf"
    $sdkconfig = Join-Path $ProjectPath ".strokeguard-build\sdkconfig"
    $defaults = Join-Path $ProjectPath "sdkconfig.defaults"
    if ($OverlayPath) {
        $defaults = "$defaults;$OverlayPath"
    }

    switch ($Action) {
        "build" {
            & idf.py -B $buildDir -D "SDKCONFIG=$sdkconfig" -D "SDKCONFIG_DEFAULTS=$defaults" set-target esp32s3
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            & idf.py -B $buildDir -D "SDKCONFIG=$sdkconfig" -D "SDKCONFIG_DEFAULTS=$defaults" build
        }
        "erase" { & idf.py -B $buildDir -p $Port erase-flash }
        "flash" { & idf.py -B $buildDir -p $Port flash }
    }
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
