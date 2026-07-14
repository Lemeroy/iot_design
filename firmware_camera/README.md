# StrokeGuard Camera Coprocessor

This ESP-IDF v5.5.3 project targets the Hiwonder ESP32-S3-Cam board
(`ESP32-S3-WROOM-1U-N8R8`) with the onboard GC2145 camera. It runs local
`esp32-camera` capture plus ESP-WHO `human_face_detect`, then exposes only a
4-byte face bounding box to the N16R8 main controller over I2C.

Raw images never leave the camera board. The current output is face presence
and normalized geometry only; it is not a FAST facial asymmetry score and must
not be treated as a medical F result.

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
