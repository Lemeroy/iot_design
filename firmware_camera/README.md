# StrokeGuard Camera Coprocessor

This ESP-IDF v5.5.3 project targets the Hiwonder ESP32-S3-Cam board
(`ESP32-S3-WROOM-1U-N8R8`) with the onboard GC2145 camera. It runs local
`esp32-camera` YUV422 capture, local PSRAM RGB888 conversion, and ESP-WHO
`human_face_detect`. It computes a quality-gated FAST Face (F) engineering
score from ESP-WHO's five landmarks and a volatile personal neutral baseline.
During a locally guided session it also computes pupil-motion E and auxiliary
tongue-deviation T scores, then exposes only numeric results to the N16R8 main
controller over a one-way UART score stream.

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
| UART1 TX | 48 | 9 (UART1 RX) |
| SDA / I2C | 47 | disconnected |
| GND | GND | GND |

Both boards use independent USB power. Do not connect 5 V between boards.
The signal cable is only camera GPIO48 TX to N16R8 GPIO9 RX plus common GND.
Camera GPIO47/SDA stays disconnected.
The score stream is `115200 8N1`, numeric-only, with a CRC-protected 20-byte
frame. No external pull-up resistor is required for this link.

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

## UART Score Protocol

The camera sends one CRC-protected binary frame every 200 ms on UART1:

```text
magic: 0x53 0x47
version: 1
length: 20 bytes
payload: sequence, valid F/E/T scores, signed details, quality, stage, progress
trailer: CRC16-CCITT little-endian
```

Scores and quality are `0..100`; signed details are engineering diagnostics.
Invalid modalities are marked unavailable rather than converted to zero.

Stages are `idle`, `face`, `eye-center`, `eye-left`, `eye-right`, `tongue`,
`done`, and `error`. E and T remain unavailable outside a guided session or
when image quality gates fail. E does not claim visual-field testing. T is an
auxiliary observation only and never acts as a single-item danger veto.

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
model. USB preview is independent of the UART score stream.
