# StrokeGuard Camera Coprocessor

This ESP-IDF v5.5.3 project targets the Hiwonder ESP32-S3-Cam module. The
module connects to its expansion board and exposes I2C on its documented
GPIO47 (SDA) and GPIO48 (SCL). It serves the 14-byte StrokeGuard camera score
frame at address `0x42`.

The vendor camera initialization source and verified internal sensor pin map
are not currently available. The firmware therefore reports `model_missing`
with `valid_mask=0`; it never fabricates F/T/E scores. Add verified camera
acquisition and evaluated local models only in `camera_capture_adapter.c`.

Raw images remain local to this board and its directly attached development
computer. The production I2C path contains only numeric scores and status.

Build and flash from the ESP-IDF v5.5.3 PowerShell:

```powershell
cd F:\iot_design\firmware_camera
idf.py set-target esp32s3
idf.py build
$CameraPort = Read-Host "Camera expansion-board COM port"
idf.py -p $CameraPort flash monitor
```
