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

## Local camera preview

The optional USB preview is only for local debugging. Close `idf.py monitor`
and every other COM4 serial tool, then run from `F:\iot_design`:

```powershell
host_pc\.venv\Scripts\python.exe host_pc\tools\camera_usb_preview.py --port COM4
```

The camera preview uses `921600 8N1`. It requests one JPEG at a time and does
not record or upload frames. The N16R8 connection is separate: I2C remains active
on GPIO8/GPIO9 while the PC preview window is connected. The displayed box is
face-presence geometry only. The production F score is a separate numeric
result computed locally from ESP-WHO five-point landmarks.

## Expected behavior

- Camera I2C address is `0x52`; bbox register `0x01` remains for debugging.
  N16R8 polls F `0x02`, E `0x03`, T `0x04`, and stage `0x11`. It controls a
  session by writing `0x10,1` (start) or `0x10,0` (cancel).
- Camera firmware runs local GC2145 capture plus ESP-WHO human face detection
  and retains the normalized bbox for USB preview.
- ESP-WHO's two eyes, nose, and two mouth corners feed quality gating,
  eye-line roll correction, asymmetry scoring, and a personal baseline. A
  valid frontal face produces `F score`, signed mouth angle, and quality on
  register `0x02`; rejected frames do not create a healthy score.
- The five-point F result is an initial risk feature, not a diagnosis or a
  replacement for evaluated 68-point analysis. Its thresholds and accuracy
  remain pending measured calibration.
- A guided session asks for frontal face, center gaze, left gaze, right gaze,
  and tongue extension. E uses local pupil ROIs; T uses a local lower-face
  color component. Invalid regions remain unavailable rather than healthy.
- E is an ocular-movement risk prompt and does not test visual fields. T is
  auxiliary only and never causes a single-item danger result.
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
6. Hold a well-lit frontal face steady for five valid frames and verify COM3
   logs `camera F score=... angle=... quality=...`.
7. Start a guided session from the authenticated VPS page and follow the F/E/T
   prompts. Confirm COM3 reports stage changes and E/T only after completion.
8. Obscure the camera during another session and confirm error/retry with
   unavailable F/E/T rather than 0 or 100.

## Verified NMO432 bring-up

On 2026-07-17, the N16R8 on COM3 reported `valid=250/250` audio blocks with
non-constant RMS and peak values (`rms=8.7..17.9`, `peak=25..41`) using GPIO17,
GPIO18, GPIO16, and the left slot (`L/R` tied to GND). This confirms I2S bus
activity and sample capture for the installed module. The observed amplitude
is only a wiring/driver bring-up result; microphone gain, acoustic response,
and S-model thresholds remain to be calibrated with recorded local test data.

This product provides risk prompts and medical-attention reminders, not a
diagnosis. Arm weakness is not independently measured by the mirror.
