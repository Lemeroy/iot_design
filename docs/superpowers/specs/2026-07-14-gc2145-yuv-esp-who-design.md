# GC2145 YUV ESP-WHO Design

## Decision

The GC2145 does not support native JPEG output in `esp32-camera`. Capture
QVGA YUV422 instead, convert each requested frame to RGB888 in local PSRAM,
and pass that RGB888 image to ESP-WHO `HumanFaceDetect`.

## Data Flow

1. GC2145 captures `320x240` YUV422 into a camera frame buffer.
2. `fmt2rgb888` converts the frame into one reusable PSRAM buffer.
3. ESP-WHO consumes `DL_IMAGE_PIX_TYPE_RGB888` and emits a normalized bbox.
4. On an explicit USB preview request, `frame2jpg` encodes the original YUV
   frame and sends it only to the directly attached PC.
5. I2C continues to expose only the four-byte bbox at `0x52/0x01`.

## Failure And Privacy Rules

- Allocation or conversion failure produces no bbox and an error log.
- Raw image buffers never enter Wi-Fi, MQTT, VPS, or large-model payloads.
- USB preview remains request-gated, transient, and local.
- A face bbox is not a FAST facial-asymmetry score or medical diagnosis.

## Acceptance

- Firmware builds with ESP-IDF 5.5.3 for ESP32-S3.
- COM4 preview has coherent geometry without repeated horizontal sections.
- A visible face produces an ESP-WHO bbox in the preview and I2C response.

