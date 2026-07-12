param(
    [string]$HostIp = $env:SG_VPS_HOST,
    [string]$SshPort = "22",
    [string]$RemoteUser = "ubuntu"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Probe = Join-Path $Root "cloud\native\e2e_mqtt.py"
if (-not $HostIp) {
    throw "VPS host missing: set SG_VPS_HOST or pass -HostIp"
}
$Remote = "${RemoteUser}@${HostIp}"
$Log = Join-Path $Root ("cloud_e2e_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

if (-not (Test-Path $Probe)) {
    throw "probe not found: $Probe"
}

$Encoded = [Convert]::ToBase64String([IO.File]::ReadAllBytes($Probe))
$RemoteCommand = "cd /opt/strokeguard/cloud && printf '%s' '$Encoded' | base64 -d | native/runtime/venv/bin/python -"

Start-Transcript -Path $Log -Append | Out-Null
try {
    Write-Host "=== StrokeGuard internal MQTT E2E ==="
    Write-Host "Enter the SSH password once."
    & ssh.exe -tt -p $SshPort -o StrictHostKeyChecking=accept-new $Remote $RemoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw "ssh.exe exited with code $LASTEXITCODE"
    }
}
finally {
    Stop-Transcript | Out-Null
    Write-Host "Transcript saved to: $Log"
}
