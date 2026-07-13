[CmdletBinding()]
param(
    [switch]$SkipExe
)

$ErrorActionPreference = "Stop"
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$distPath = [IO.Path]::GetFullPath((Join-Path $repoRoot "dist"))
$expectedDist = [IO.Path]::GetFullPath("$repoRoot\dist")
if ($distPath -ne $expectedDist) {
    throw "Refusing unexpected dist path: $distPath"
}

Push-Location $repoRoot
try {
    & git diff --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Tracked working-tree changes must be committed before release"
    }
    & git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Staged changes must be committed before release"
    }

    if (Test-Path -LiteralPath $distPath) {
        Get-ChildItem -LiteralPath $distPath -Force | Remove-Item -Recurse -Force
    } else {
        New-Item -ItemType Directory -Path $distPath | Out-Null
    }

    $python = Join-Path $repoRoot "host_pc\.venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Missing host_pc virtual environment"
    }

    if (-not $SkipExe) {
        & $python -c "import PyInstaller"
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller is missing; install host_pc[ui,dev]"
        }
        & $python -m PyInstaller `
            --noconfirm `
            --clean `
            --onefile `
            --windowed `
            --name "StrokeGuard-Demo" `
            --paths (Join-Path $repoRoot "host_pc") `
            --add-data "$(Join-Path $repoRoot 'host_pc\config\device-deployment.example.yaml');stroke_host\config" `
            --distpath $distPath `
            --workpath (Join-Path $repoRoot ".release-build\work") `
            --specpath (Join-Path $repoRoot ".release-build\spec") `
            --exclude-module "numpy" `
            --exclude-module "cv2" `
            --exclude-module "mediapipe" `
            --exclude-module "sounddevice" `
            --exclude-module "pyttsx3" `
            --exclude-module "keyring" `
            --exclude-module "cryptography" `
            --exclude-module "paho" `
            --exclude-module "torch" `
            --exclude-module "ultralytics" `
            --exclude-module "matplotlib" `
            (Join-Path $repoRoot "host_pc\stroke_host\demo_entry.py")
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller build failed"
        }
    }

    $zipPath = Join-Path $distPath "StrokeGuard-Developer-Handoff.zip"
    & git archive `
        --format=zip `
        --prefix="StrokeGuard-Developer-Handoff/" `
        --output=$zipPath `
        HEAD
    if ($LASTEXITCODE -ne 0) {
        throw "git archive failed"
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        $forbidden = @(
            "/sdkconfig$",
            "/sdkconfig\.old$",
            "/\.env$",
            "/data/",
            "/build/",
            "/dist/",
            "/device-deployment\.local\.ya?ml$",
            "/\.strokeguard-build/",
            "__pycache__",
            "\.pyc$",
            "\.log$",
            "\.docx$"
        )
        foreach ($entry in $archive.Entries) {
            foreach ($pattern in $forbidden) {
                if ($entry.FullName -match $pattern) {
                    throw "Forbidden handoff entry: $($entry.FullName)"
                }
            }
        }
    } finally {
        $archive.Dispose()
    }

    $expected = @("StrokeGuard-Demo.exe", "StrokeGuard-Developer-Handoff.zip")
    $actual = @(Get-ChildItem -LiteralPath $distPath -File | Select-Object -ExpandProperty Name)
    if (-not $SkipExe -and (Compare-Object $expected $actual)) {
        throw "dist must contain only the two release artifacts"
    }
    Get-ChildItem -LiteralPath $distPath -File | ForEach-Object {
        $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName
        [pscustomobject]@{
            Name = $_.Name
            Bytes = $_.Length
            SHA256 = $hash.Hash
        }
    } | Format-Table -AutoSize
} finally {
    Pop-Location
}
