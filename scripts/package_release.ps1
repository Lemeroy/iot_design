[CmdletBinding()]
param(
    [switch]$SkipExe,
    [string[]]$ValidatePaths
)

$ErrorActionPreference = "Stop"
$forbiddenReleasePathPatterns = @(
    "(^|/)\.env$",
    "(^|/)(?:\.pytest_cache|\.mypy_cache|\.ruff_cache|\.cache)(?:/|$)",
    "(^|/)(?:__pycache__|data|build|dist)(?:/|$)",
    "(^|/)device-deployment\.local\.ya?ml$",
    "(^|/)\.strokeguard-build(?:/|$)",
    "/cloud/native/(?:runtime|state|logs|run|downloads)/",
    "\.(?:log|pyc)$"
)

function Assert-ReleasePathsAllowed {
    param(
        [string[]]$Paths,
        [string]$Source
    )

    foreach ($path in $Paths) {
        $normalizedPath = $path -replace "\\", "/"
        foreach ($pattern in $forbiddenReleasePathPatterns) {
            if ($normalizedPath -match $pattern) {
                throw "Forbidden release path from ${Source}: $path"
            }
        }
    }
}

if ($PSBoundParameters.ContainsKey("ValidatePaths")) {
    Assert-ReleasePathsAllowed -Paths $ValidatePaths -Source "validation input"
    exit 0
}

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$buildScript = Join-Path $PSScriptRoot "build_release.ps1"

& $buildScript -SkipExe:$SkipExe
if ($LASTEXITCODE -ne 0) {
    throw "Release build failed"
}

$distPath = Join-Path $repoRoot "dist"
$expectedArtifacts = @("StrokeGuard-Demo.exe", "StrokeGuard-Developer-Handoff.zip")
foreach ($artifact in $expectedArtifacts) {
    if (-not $SkipExe -or $artifact -eq "StrokeGuard-Developer-Handoff.zip") {
        if (-not (Test-Path -LiteralPath (Join-Path $distPath $artifact))) {
            throw "Missing release artifact: $artifact"
        }
    }
}

$zipPath = Join-Path $distPath "StrokeGuard-Developer-Handoff.zip"
Add-Type -AssemblyName System.IO.Compression.FileSystem
$trackedPaths = @(& git -C $repoRoot ls-files)
if ($LASTEXITCODE -ne 0) {
    throw "Could not enumerate tracked release paths"
}
Assert-ReleasePathsAllowed -Paths $trackedPaths -Source "tracked"

$archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $entries = @($archive.Entries.FullName)
    $required = @(
        "/cloud/backend/app/static/demo/index.html$",
        "/cloud/backend/app/static/demo/app.css$",
        "/cloud/backend/app/static/demo/app.js$",
        "/cloud/README.md$",
        "/host_pc/stroke_host/demo/window.py$",
        "/host_pc/config/device-deployment.example.yaml$",
        "/README.md$"
    )
    foreach ($pattern in $required) {
        if (-not ($entries | Where-Object { $_ -match $pattern })) {
            throw "Missing preliminary monitor handoff entry: $pattern"
        }
    }

    # A local cloud/.env must never enter the developer handoff.
    Assert-ReleasePathsAllowed -Paths $entries -Source "archive"
} finally {
    $archive.Dispose()
}

# The release contains no raw audio, raw video, MFCC, landmarks, or ROI examples.
