param(
    [switch]$InstallDependencies,
    [switch]$Export,
    [switch]$Render
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ScadEntry = Join-Path $ProjectRoot 'scad\strokeguard_enclosure.scad'
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$Requirements = Join-Path $ProjectRoot 'requirements-dev.txt'

function Find-OpenScad {
    $candidates = [System.Collections.Generic.List[string]]::new()

    if ($env:OPENSCAD_EXE) {
        $candidates.Add($env:OPENSCAD_EXE)
    }

    foreach ($commandName in @('openscad.com', 'openscad.exe')) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command) {
            $candidates.Add($command.Source)
        }
    }

    $candidates.Add('C:\Program Files\OpenSCAD\openscad.com')
    $candidates.Add('C:\Program Files\OpenSCAD\openscad.exe')

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    throw 'OpenSCAD not found. Install OpenSCAD or set OPENSCAD_EXE.'
}

function Invoke-CheckedOpenScad {
    param([Parameter(Mandatory)][string[]]$Arguments)

    & (Find-OpenScad) @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "OpenSCAD exited with code $LASTEXITCODE"
    }
}

function Install-MechanicalEnvironment {
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        & python -m venv (Join-Path $ProjectRoot '.venv')
        if ($LASTEXITCODE -ne 0) {
            throw 'Unable to create the mechanical environment.'
        }
    }

    & $VenvPython -m pip install -r $Requirements
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to install packages in the mechanical environment.'
    }
}

function Export-Stl {
    param(
        [Parameter(Mandatory)][string]$Part,
        [Parameter(Mandatory)][string]$OutputPath,
        [ValidateSet('printable', 'display')][string]$Variant = 'printable'
    )

    $parent = Split-Path -Parent $OutputPath
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Invoke-CheckedOpenScad -Arguments @(
        '-D', "part=\`"$Part\`"",
        '-D', "variant=\`"$Variant\`"",
        '-o', $OutputPath,
        $ScadEntry
    )
}

function Export-Render {
    param(
        [Parameter(Mandatory)][string]$Part,
        [Parameter(Mandatory)][string]$OutputPath
    )

    $parent = Split-Path -Parent $OutputPath
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Invoke-CheckedOpenScad -Arguments @(
        '--imgsize=1600,1200',
        '--viewall',
        '--autocenter',
        '-D', "part=\`"$Part\`"",
        '-D', 'variant=\"display\"',
        '-o', $OutputPath,
        $ScadEntry
    )
}

if ($InstallDependencies) {
    Install-MechanicalEnvironment
}

if ($Export -or $Render) {
    if (-not (Test-Path -LiteralPath $ScadEntry)) {
        throw "OpenSCAD entry point not found: $ScadEntry"
    }
}

if ($Export) {
    throw 'Part export is enabled after the approved SCAD part modules are added.'
}

if ($Render) {
    throw 'Rendering is enabled after the approved assembly modules are added.'
}
