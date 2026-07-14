# Camera Coprocessor and NMO432 Bring-up

## Hardware

- Main controller: ESP32-S3-WROOM-1 N16R8.
- Camera: Hiwonder ESP32-S3-Cam with its expansion board.
- Microphone: NMO432 digital I2S module, powered only from 3.3 V.
- ST7789, MAX98357A, RGB, buzzer, and buttons are not used.

Power off before changing wiring. All modules must share GND. Verify the
camera expansion-board I2C connector order and 3.3 V logic level before power.

| Signal | Peripheral | N16R8 |
| --- | --- | --- |
| Camera SDA | camera GPIO47 | GPIO8 |
| Camera SCL | camera GPIO48 | GPIO9 |
| Camera ground | GND | GND |
| NMO432 SCK | SCK | GPIO17 |
| NMO432 WS | WS | GPIO18 |
| NMO432 SD | SD | GPIO16 |
| NMO432 supply | VDD | 3.3 V |
| NMO432 ground | GND | GND |

Tie NMO432 `L/R` to GND for the configured left slot, or to 3.3 V for the
right slot. The deployment YAML channel must match this connection.

## Build and flash

Open `C:\Users\Administrator\Desktop\IDF_v5.5.3_Powershell.lnk`.

```powershell
cd F:\iot_design\firmware_esp32
idf.py build
idf.py -p COM3 flash monitor

Get-CimInstance Win32_SerialPort | Select-Object DeviceID,Name
cd F:\iot_design\firmware_camera
idf.py set-target esp32s3
idf.py build
idf.py -p COM4 flash monitor
```

The camera expansion board must use its own USB serial port, not COM3. Do not
run `erase-flash` unless intentionally clearing all local configuration. Keep
the inter-board 5 V jumper disconnected; both boards are powered by USB and
share only GND plus I2C.

## Expected behavior

- Camera I2C address is `0x52`, face register is `0x01`, and N16R8 polls every
  500 ms.
- Camera firmware runs local GC2145 capture plus ESP-WHO human face detection
  and returns four normalized bytes: `center_x`, `center_y`, `width`, `height`.
  All zeros mean no face detected.
- The current face box proves camera/model operation only. It is not a FAST
  facial asymmetry score, so F/T/E remain unavailable until evaluated
  asymmetry, tongue, and eye algorithms are added.
- NMO432 logs aggregate RMS, peak, and valid-block counts every five seconds.
  These are electrical diagnostics, not a speech-risk score.
- S remains unavailable without an evaluated versioned model.
- Missing modalities keep fusion at `insufficient`; they never become zero or
  fabricated normal scores.

## Acceptance

1. Run both boards for 30 minutes without resets.
2. Disconnect camera I2C; CSI, Wi-Fi, MQTT, and NMO432 must continue.
3. Reconnect I2C; camera communication must recover without reboot.
4. Speak near NMO432 and verify RMS/peak change; silence must not create S.
5. Confirm MQTT and InfluxDB contain no JPEG, PCM, MFCC, or raw media.
6. Confirm unavailable F/S/T/E are displayed as unavailable rather than 0.

This product provides risk prompts and medical-attention reminders, not a
diagnosis. Arm weakness is not independently measured by the mirror.
