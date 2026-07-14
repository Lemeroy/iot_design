# Camera USB Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display live GC2145 frames and the ESP-WHO bounding box in a local PC window over camera-board COM4 without storing or uploading images.

**Architecture:** The existing camera acquisition loop remains the sole frame-buffer owner. A UART request flag triggers occasional RGB565-to-JPEG conversion; the complete CRC-protected packet is written to UART0, while a PyQt5 worker requests, parses, validates, and displays one frame at a time.

**Tech Stack:** ESP-IDF 5.5.3, esp32-camera `frame2jpg`, UART0/CH340, C/C++, Python 3.11, PyQt5, pyserial, pytest.

## Global Constraints

- UART is `921600 8N1`; COM4 is exclusive while preview is connected.
- JPEG payload limit is 128 KiB.
- Raw images remain on the camera board and directly connected PC; no network calls or disk recording.
- Face bounding boxes remain presence metadata and are never converted into a medical F score.
- ESP-WHO inference and N16R8 I2C address `0x52`, register `0x01`, must continue during preview.
- Remove temporary ASCII preview and high-frequency frame diagnostics before final verification.

---

### Task 1: Shared Preview Packet Contract

**Files:**
- Create: `firmware_common/camera_preview_protocol.h`
- Create: `firmware_common/camera_preview_protocol.c`
- Create: `host_pc/stroke_host/camera_preview/__init__.py`
- Create: `host_pc/stroke_host/camera_preview/protocol.py`
- Create: `host_pc/tests/test_camera_preview_protocol.py`

**Interfaces:**
- Produces C constants `SG_CAMERA_PREVIEW_MAGIC`, `SG_CAMERA_PREVIEW_VERSION`, `SG_CAMERA_PREVIEW_MAX_JPEG` and packed `sg_camera_preview_header_t`.
- Produces Python `PreviewFrame`, `encode_test_packet(...)`, and incremental `PreviewStreamParser.feed(data) -> list[PreviewFrame]`.

- [ ] **Step 1: Write failing parser tests** for partial packets, garbage-prefix resynchronization, CRC rejection, 128 KiB length rejection, JPEG marker validation, and bounding-box fields.
- [ ] **Step 2: Run** `host_pc\.venv\Scripts\python.exe -m pytest host_pc\tests\test_camera_preview_protocol.py -q`; expect failures because the package does not exist.
- [ ] **Step 3: Implement the packed C header and Python parser** using little-endian `struct.Struct("<4sBBHII4B")` and `zlib.crc32` over header bytes after magic plus JPEG payload.
- [ ] **Step 4: Re-run the focused tests**; expect all protocol tests to pass.
- [ ] **Step 5: Commit** with `feat(camera): define USB preview protocol`.

### Task 2: Camera UART Request/Response Service

**Files:**
- Create: `firmware_camera/main/camera_usb_preview.h`
- Create: `firmware_camera/main/camera_usb_preview.c`
- Modify: `firmware_camera/main/CMakeLists.txt`
- Modify: `firmware_camera/main/camera_capture_adapter.cpp`
- Modify: `firmware_camera/main/app_main.c`
- Modify: `host_pc/tests/test_camera_coprocessor_firmware.py`

**Interfaces:**
- `esp_err_t sg_camera_usb_preview_init(void)` initializes UART request handling.
- `bool sg_camera_usb_preview_requested(void)` atomically consumes one pending `0xA5` request.
- `esp_err_t sg_camera_usb_preview_send(camera_fb_t *, const sg_camera_face_bbox_t *)` converts JPEG quality 70, validates 128 KiB, appends CRC32, and writes one contiguous response.

- [ ] **Step 1: Replace interrupted diagnostic assertions with failing firmware contract tests** that require request-gated `frame2jpg`, packet CRC, size bound, and no ASCII preview.
- [ ] **Step 2: Run the focused firmware tests** and confirm expected failures.
- [ ] **Step 3: Implement UART service and acquisition-loop call** after ESP-WHO inference and before `esp_camera_fb_return`; initialize it from `app_main`.
- [ ] **Step 4: Run focused tests and** `idf.py -C firmware_camera build`; expect success.
- [ ] **Step 5: Commit** with `feat(camera): stream requested JPEG frames over USB`.

### Task 3: PyQt5 COM4 Preview Tool

**Files:**
- Create: `host_pc/stroke_host/camera_preview/serial_worker.py`
- Create: `host_pc/stroke_host/camera_preview/window.py`
- Create: `host_pc/tools/camera_usb_preview.py`
- Create: `host_pc/tests/test_camera_preview_worker.py`
- Create: `host_pc/tests/test_camera_preview_privacy.py`

**Interfaces:**
- `CameraPreviewWorker(port: str, baudrate: int = 921600)` emits validated `PreviewFrame` and status/error signals.
- `CameraPreviewWindow` owns connection controls, image label, overlay, and telemetry labels.

- [ ] **Step 1: Write failing tests** for request-after-frame backpressure, timeout/offline state, port release, and absence of file/network APIs.
- [ ] **Step 2: Run focused tests** and confirm failures because worker/UI modules do not exist.
- [ ] **Step 3: Implement worker and window** with `QImage.fromData`, `QPainter` bounding box overlay, COM4 default selection, explicit connect/disconnect, and no save control.
- [ ] **Step 4: Run focused tests and import smoke test** using the host virtual environment.
- [ ] **Step 5: Commit** with `feat(host): add local camera USB preview`.

### Task 4: Hardware Integration And Documentation

**Files:**
- Modify: `firmware_camera/README.md`
- Modify: `docs/camera-nmo432-bringup.md`
- Modify: `README.md`

**Interfaces:**
- Documents the exact launch command, COM4 ownership, 921600 baud, privacy boundary, and recovery steps.

- [ ] **Step 1: Add documentation assertions** to existing camera firmware tests.
- [ ] **Step 2: Update documentation** with `host_pc\.venv\Scripts\python.exe host_pc\tools\camera_usb_preview.py --port COM4` and note that other serial monitors must be closed.
- [ ] **Step 3: Run all host tests** with `host_pc\.venv\Scripts\python.exe -m pytest host_pc\tests -q`.
- [ ] **Step 4: Build both firmware projects**, flash camera COM4, and verify N16R8 COM3 still reports camera online.
- [ ] **Step 5: Launch the preview tool**, verify changing frames, overlay when a face is detected, disconnect behavior, and no network/disk output.
- [ ] **Step 6: Commit and push** with `docs(camera): document USB preview workflow`.
