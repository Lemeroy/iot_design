$ErrorActionPreference = "Stop"

$HostIp = "106.75.229.61"
$Remote = "ubuntu@${HostIp}"

Write-Host "=== StrokeGuard cloud SSH tunnel ==="
Write-Host "MQTT:     127.0.0.1:11883 -> VPS 127.0.0.1:1883"
Write-Host "FastAPI:  http://127.0.0.1:18000"
Write-Host "Dashboard:http://127.0.0.1:18084"
Write-Host "Keep this window open while the host UI uses cloud services."
Write-Host "Enter the SSH password when prompted."
Write-Host ""

& ssh.exe `
    -N `
    -T `
    -o ExitOnForwardFailure=yes `
    -o ServerAliveInterval=30 `
    -o ServerAliveCountMax=3 `
    -L 127.0.0.1:11883:127.0.0.1:1883 `
    -L 127.0.0.1:18000:127.0.0.1:8000 `
    -L 127.0.0.1:18084:127.0.0.1:18083 `
    $Remote

if ($LASTEXITCODE -ne 0) {
    throw "SSH tunnel exited with code $LASTEXITCODE"
}
