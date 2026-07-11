$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$CloudDir = Join-Path $Root "cloud"
$HostIp = "106.75.229.61"
$SshPort = "22"
$RemoteUser = "ubuntu"
$Remote = "${RemoteUser}@${HostIp}"
$Archive = Join-Path $env:TEMP "strokeguard-cloud-native.tar.gz"
$Log = Join-Path $Root ("cloud_native_deploy_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList
    )
    Write-Host ""
    Write-Host ("> {0} {1}" -f $FilePath, ($ArgumentList -join " "))
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath exited with code $LASTEXITCODE"
    }
}

Start-Transcript -Path $Log -Append | Out-Null
try {
    Write-Host "=== StrokeGuard native cloud deploy ==="
    Write-Host "Target: $Remote port $SshPort"
    Write-Host "Enter the SSH password for upload and SSH, then the sudo password if requested."

    Invoke-Checked "tar.exe" @("-czf", $Archive, "-C", $Root, "cloud")
    Invoke-Checked "scp.exe" @(
        "-P", $SshPort,
        "-o", "StrictHostKeyChecking=accept-new",
        $Archive,
        (Join-Path $CloudDir "native\deploy_remote.sh"),
        "${Remote}:/tmp/"
    )

    Invoke-Checked "ssh.exe" @(
        "-tt",
        "-p", $SshPort,
        "-o", "StrictHostKeyChecking=accept-new",
        $Remote,
        "sudo bash /tmp/deploy_remote.sh"
    )
    Write-Host ""
    Write-Host "=== Native deploy finished ==="
}
finally {
    if (Test-Path $Archive) {
        Remove-Item -LiteralPath $Archive -Force
    }
    Stop-Transcript | Out-Null
    Write-Host "Transcript saved to: $Log"
}
