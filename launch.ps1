# StrokeGuard M4+M5 一键全栈启动
# 用法: 右键"使用 PowerShell 运行", 或在 ESP-IDF 5.5.3 PowerShell 里:
#   .\launch.ps1
#
# 前置条件:
#   1. ESP32-S3 已插 COM3
#   2. VPS 云端已部署 (见 cloud/README.md)
#   3. 火山引擎 API Key 已填 cloud/.env (不填也跑, LLM 走 fallback)

param(
    [string]$Port = "COM3",
    [string]$MqttHost = "106.75.229.61",
    [string]$MqttPort = "1883",
    [string]$MqttUser = "host01",
    [string]$MqttPass = "",
    [string]$DeviceId = "sg-0001",
    [string]$Source = "real",
    [switch]$SkipFlash = $false
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $MqttPass) {
    $envPath = Join-Path $root "cloud\.env"
    if (Test-Path $envPath) {
        foreach ($line in Get-Content -Encoding UTF8 $envPath) {
            if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
            $parts = $line -split '=', 2
            $name = $parts[0].Trim()
            $value = $parts[1].Trim()
            if ($name -eq "MQTT_HOST_USER" -and $value) { $MqttUser = $value }
            if ($name -eq "MQTT_HOST_PASS" -and $value) { $MqttPass = $value }
        }
    }
}
if (-not $MqttPass) {
    throw "MQTT password missing: configure cloud\.env or pass -MqttPass explicitly"
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " StrokeGuard 全栈启动" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# ---- 1. Flash ESP32-S3 ----
if (-not $SkipFlash) {
    Write-Host "`n[1/3] 编译并烧录 ESP32-S3 @ $Port ..." -ForegroundColor Yellow
    $fwDir = Join-Path $root "firmware_esp32"
    Push-Location $fwDir
    try {
        idf.py build
        if ($LASTEXITCODE -ne 0) { throw "idf.py build failed" }
        idf.py -p $Port flash
        if ($LASTEXITCODE -ne 0) { throw "idf.py flash failed" }
        Write-Host "  S3 flash OK" -ForegroundColor Green
    } finally {
        Pop-Location
    }
} else {
    Write-Host "`n[1/3] 跳过烧录 (--SkipFlash)" -ForegroundColor DarkGray
}

# ---- 2. 设云端环境变量 ----
Write-Host "`n[2/3] 设置 MQTT 环境变量 -> $MqttHost`:$MqttPort ..." -ForegroundColor Yellow
$env:SG_MQTT_HOST = $MqttHost
$env:SG_MQTT_PORT = $MqttPort
$env:SG_MQTT_USER = $MqttUser
$env:SG_MQTT_PASS = $MqttPass
$env:SG_DEVICE_ID  = $DeviceId
Write-Host "  SG_MQTT_HOST=$MqttHost SG_DEVICE_ID=$DeviceId" -ForegroundColor Green

# ---- 3. 启动 GUI ----
Write-Host "`n[3/3] 启动 PyQt5 GUI (source=$Source) ..." -ForegroundColor Yellow
$venvPython = Join-Path $root "host_pc\.venv\Scripts\python.exe"
& $venvPython -m stroke_host.ui.main_window --source $Source --perception --port $Port

Write-Host "`nGUI 已退出." -ForegroundColor Cyan
