# StrokeGuard Camera Coprocessor

This ESP-IDF v5.5.3 project targets the Hiwonder ESP32-S3-Cam board
(`ESP32-S3-WROOM-1U-N8R8`) with the onboard GC2145 camera. It runs local
`esp32-camera` capture plus ESP-WHO `human_face_detect`, then exposes only a
4-byte face bounding box to the N16R8 main controller over I2C.

Raw images are not uploaded. The normal device output is face presence and
normalized geometry only. An explicit USB debug session may send requested
JPEG frames directly to the attached PC; frames are not saved or uploaded.
The face box is not a FAST facial asymmetry score and must not be treated as a
medical F result.

## Wiring

Both boards are powered by their own USB cables. Keep the 5 V jumper between
boards disconnected. Share ground.

| Camera board signal | Camera GPIO | N16R8 GPIO |
| --- | ---: | ---: |
| SDA | 47 | 8 |
| SCL | 48 | 9 |
| GND | GND | GND |

The camera's internal GC2145 DVP/SCCB pins are configured in
`main/camera_capture_adapter.cpp` from the vendor example:

```text
XCLK=15, SCCB_SDA=4, SCCB_SCL=5
D0..D7 = 11,9,8,10,12,18,17,16
VSYNC=6, HREF=7, PCLK=13
```

## I2C Protocol

The camera board is the I2C target on GPIO47/GPIO48:

```text
address:  0x52
register: 0x01
reply:    4 bytes: center_x, center_y, width, height
```

Each value is normalized to `0..255` against the current frame. All zeros mean
no face detected. The N16R8 writes register `0x01` and reads four bytes.

## Build And Flash

Open `C:\Users\Administrator\Desktop\IDF_v5.5.3_Powershell.lnk`:

```powershell
cd F:\iot_design\firmware_camera
idf.py set-target esp32s3
idf.py build
idf.py -p COM4 flash monitor
```

The app uses a custom `3 MB` factory partition and `8 MB` flash because the
embedded ESP-WHO model is larger than the default 1 MB app partition.

## Local USB Preview

Close every COM4 serial monitor before opening the preview; COM4 must be closed
by other programs because one process owns the port. From the repository root:

```powershell
host_pc\.venv\Scripts\python.exe host_pc\tools\camera_usb_preview.py --port COM4
```

The debug protocol uses `921600 8N1`. The PC requests one JPEG at a time, so
preview work stops when the window disconnects. Images remain on the directly
connected PC, are not saved, and are not uploaded to MQTT, VPS, or the large
model. I2C face-box polling at `0x52`/`0x01` continues during preview.
