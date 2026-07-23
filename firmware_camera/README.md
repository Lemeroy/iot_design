# StrokeGuard Camera Coprocessor

This ESP-IDF v5.5.3 project targets the Hiwonder ESP32-S3-Cam board
(`ESP32-S3-WROOM-1U-N8R8`) with the onboard GC2145 camera. It runs local
`esp32-camera` YUV422 capture, local PSRAM RGB888 conversion, and ESP-WHO
`human_face_detect`. It computes a quality-gated FAST Face (F) engineering
score from ESP-WHO's five landmarks and a volatile personal neutral baseline.
During an explicitly started guided session it also computes local pupil-motion
E and auxiliary tongue-deviation T scores, then exposes only numeric results to
the N16R8 main controller over I2C.

Raw images are not uploaded. The normal device output is face presence and
normalized geometry only. An explicit USB debug session may send requested
JPEG frames directly to the attached PC; frames are not saved or uploaded.
The USB face box remains a detection diagnostic. The five-point F score is a
risk feature, not a diagnosis, and is not equivalent to evaluated 68-point
facial analysis.

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

GC2145 does not provide native JPEG output through `esp32-camera`. The
firmware captures QVGA YUV422 and converts it locally to a reusable RGB888
PSRAM buffer for ESP-WHO. An explicit USB preview request encodes the original
YUV422 frame to JPEG locally; it does not change the normal I2C-only output.
The `esp32-camera` converter emits BGR byte order for YUV422 input, so the
adapter swaps the red and blue channels before ESP-WHO preprocessing. Removing
that normalization prevents reliable face detection on the real board.
The camera uses one frame buffer with `CAMERA_GRAB_WHEN_EMPTY`; real-board
testing showed that the two-buffer latest-frame mode spliced DMA regions from
different frames. The resulting frame rate and inference latency are pending
final measurement.

## I2C Protocol

The camera board is the I2C target on GPIO47/GPIO48:

```text
address:  0x52
register 0x01: 4 bytes: center_x, center_y, width, height
register 0x02: 4 bytes: status, F_score, signed_mouth_angle, quality
register 0x03: 4 bytes: status, E_score, binocular_difference, quality
register 0x04: 4 bytes: status, T_score, signed_offset_percent, quality
register 0x10: write 2 bytes: register, start(1)/cancel(0)
register 0x11: 4 bytes: stage, progress, 0, 0
```

Register `0x01` values are normalized to `0..255`; all zeros mean no face.
For register `0x02`, status `1` means the remaining values are valid and
status `0` means F is unavailable. Score and quality are `0..100`; angle is a
signed degree value in `-90..90`. N16R8 uses register `0x02` for fusion.

Stages are `idle`, `face`, `eye-center`, `eye-left`, `eye-right`, `tongue`,
`done`, and `error`. E and T remain unavailable outside a guided session or
when image quality gates fail. E does not claim visual-field testing. T is an
auxiliary observation only and never acts as a single-item danger veto.
If the tongue stage times out without three valid samples, the session enters
`error` and T remains unavailable; no zero or synthetic tongue score is sent
to fusion.
The tongue color candidate must also extend below the detected mouth line;
lip-colored regions without protrusion remain unavailable.
During a new guided run, the previous valid E/T values remain visible until
replacement results are ready. A tongue-stage failure clears T immediately.
Guided eye steps that do not move in opposite directions are treated as an
unavailable acquisition, not E=0; continuous eye monitoring remains available.

The F feature requires a face at least 64 pixels wide, sufficient eye spacing,
a near-frontal nose position, and eye-line roll within 25 degrees. It removes
eye-line roll from the mouth angle, combines mouth angle with nose-to-mouth
distance asymmetry, and publishes a three-frame median relative to a five-sample
neutral baseline. These are
initial engineering thresholds pending measured sensitivity, specificity,
and K-fold evaluation.

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
model. I2C numeric F polling at `0x52`/`0x02` continues during preview.
