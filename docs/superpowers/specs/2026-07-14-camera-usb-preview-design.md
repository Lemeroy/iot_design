# Camera USB Preview Design

## Goal

Provide a local debugging view of the GC2145 camera on the PC while the
camera coprocessor continues ESP-WHO face detection and I2C communication
with the N16R8 main controller.

The preview is a development aid. It is not part of the medical risk score
and must not upload or persist raw images.

## Scope

- Camera board: Hiwonder ESP32-S3-Cam N8R8 with GC2145 on COM4.
- Main board: ESP32-S3 N16R8 remains connected over I2C address `0x52`.
- PC: standalone Python preview tool using the existing host virtual
  environment.
- Transport: local UART through the camera board CH340 USB adapter.

VPS forwarding, browser streaming, recording, screenshots, and cloud storage
are out of scope.

## Runtime Design

The camera acquisition loop remains the only owner of `camera_fb_t`. It runs
ESP-WHO first, updates the latest face bounding box for I2C, and services at
most one pending PC preview request before returning the frame buffer.

The PC controls the preview rate by sending a request byte. The camera board
does not stream unless a tool is connected and requests a frame. RGB565 is
converted to JPEG only for the requested frame, limiting extra CPU and UART
load.

The preview tool requests the next frame only after the previous response is
validated and displayed. This provides natural backpressure and avoids a
second frame queue on the camera board.

## Serial Protocol

UART settings are `921600 8N1`.

PC request:

```text
0xA5
```

Camera response, little-endian fields:

```text
magic[4] = "SGJP"
version:u8 = 1
flags:u8
header_size:u16
sequence:u32
jpeg_length:u32
center_x:u8
center_y:u8
width:u8
height:u8
jpeg[jpeg_length]
crc32:u32
```

The CRC covers the fixed header after `magic`, followed by the JPEG payload.
The four bounding-box bytes use the existing normalized 0-255 camera protocol;
all zero means no face.

The PC parser scans for `SGJP`, validates version, size limits, JPEG markers,
and CRC, then recovers by scanning for the next magic value after malformed or
partial data. Maximum accepted JPEG size is 128 KiB.

## Console Interaction

Normal boot diagnostics remain at 115200 until the preview UART service is
initialized, then UART0 switches to 921600. The PC tool owns COM4 while open.
It shows protocol and firmware errors in its own status area; a second serial
monitor must not open COM4 concurrently.

## PC Tool

`host_pc/tools/camera_usb_preview.py` provides:

- COM port selector, defaulting to COM4 when present.
- Connect/disconnect controls.
- Live image without recording.
- Face bounding-box overlay from the camera response.
- FPS, JPEG size, frame sequence, and connection status.
- Clear offline and CRC/protocol error states.

The tool uses PyQt5, pyserial, and Pillow already available through the host
project dependency workflow. Closing the window releases COM4 immediately.

## Privacy And Medical Boundary

- JPEG bytes travel only from the camera board to the directly connected PC.
- The tool does not save images or send network requests.
- The VPS, MQTT, InfluxDB, and large-model service receive no image data.
- A detected face box is not a FAST face-asymmetry score and is never converted
  into an F score by this feature.

## Failure Handling

- No COM4: show offline and allow refresh/reconnect.
- Timeout: retain the last frame with a disconnected/stale indicator.
- Bad length, JPEG, or CRC: discard the frame and resynchronize.
- JPEG conversion failure: camera returns an error flag with no payload.
- PC disconnect: no new request arrives, so preview work stops automatically.
- I2C and ESP-WHO continue even when USB preview is unavailable.

## Verification

- Unit tests cover request parsing, response framing, CRC rejection, partial
  reads, resynchronization, and the no-save/no-network privacy boundary.
- Camera firmware and N16R8 firmware both build with ESP-IDF 5.5.3.
- On hardware, COM4 displays changing GC2145 frames and a face overlay when
  ESP-WHO reports a bounding box.
- COM3 continues to log `camera coprocessor online addr=0x52 reg=0x01` during
  preview.
- Closing the tool stops preview requests while face detection and I2C remain
  operational.
