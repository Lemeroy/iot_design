# Camera Single-Wire UART Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the failed camera I2C score link with a standalone one-wire UART score stream from camera GPIO48 to N16R8 GPIO9.

**Architecture:** A shared 20-byte binary protocol carries numeric F/E/T and guided-stage state with CRC16. The camera sends at 5 Hz on UART1 and automatically cycles guided screening. The N16R8 parses and fuses fresh packets while MQTT start controls only the local fusion session.

**Tech Stack:** ESP-IDF v5.5.3, FreeRTOS, ESP-IDF UART driver, Unity, pytest, C/C++.

## Global Constraints

- Camera GPIO48 TX connects to N16R8 GPIO9 RX; GPIO47/SDA stays disconnected.
- Camera UART0 at 921600 remains dedicated to optional local JPEG preview.
- UART1 score transport is 115200 baud, 8N1, numeric data only.
- No valid packet for two seconds makes F/E/T unavailable.
- Raw audio and video never leave local devices.
- Existing unrelated worktree changes must not be staged or reverted.

---

### Task 1: Shared UART score protocol

**Files:**
- Create: `firmware_common/camera_uart_protocol.h`
- Create: `firmware_common/camera_uart_protocol.c`
- Modify: `firmware_esp32/test_apps/camera_protocol/main/CMakeLists.txt`
- Modify: `firmware_esp32/test_apps/camera_protocol/main/test_camera_protocol.c`

**Interfaces:**
- Produces: `sg_camera_uart_encode`, `sg_camera_uart_parse`, `sg_camera_uart_stream_feed`, `sg_camera_uart_payload_t`, and `SG_CAMERA_UART_PACKET_SIZE`.
- Packet bytes: magic `0x53 0x47`, version `1`, length `20`, sequence LE16, valid flags, three bytes each for F/E/T, stage, progress, CRC16-CCITT LE16.

- [ ] **Step 1: Add failing Unity tests** for exact encoded bytes, signed fields, CRC rejection, invalid score rejection, noise resynchronization, and split packet input.
- [ ] **Step 2: Build the protocol test app** with `idf.py build`; expect compile failure because `camera_uart_protocol.h` does not exist.
- [ ] **Step 3: Implement the protocol** with explicit byte offsets and no packed-struct casts.
- [ ] **Step 4: Build the protocol test app again**; expect a successful build.
- [ ] **Step 5: Commit** only the shared protocol and its tests with `feat(camera): add UART score protocol`.

### Task 2: Camera UART sender and automatic guided cycle

**Files:**
- Create: `firmware_camera/main/camera_score_uart.h`
- Create: `firmware_camera/main/camera_score_uart.c`
- Modify: `firmware_camera/main/CMakeLists.txt`
- Modify: `firmware_camera/main/app_main.c`
- Modify: `firmware_camera/main/camera_capture_adapter.cpp`
- Test: `host_pc/tests/test_camera_coprocessor_firmware.py`

**Interfaces:**
- Consumes: `sg_camera_uart_encode(const sg_camera_uart_payload_t *, uint16_t, uint8_t[20])`.
- Produces: `sg_camera_score_uart_init()` and `sg_camera_score_uart_send(const sg_camera_source_observation_t *)`.
- UART configuration: UART1, TX GPIO48, no RX pin, 115200 baud, 8N1.

- [ ] **Step 1: Add failing source-contract tests** requiring UART1/GPIO48, the shared encoder, no network media, and automatic restart after `done` or `error`.
- [ ] **Step 2: Run the focused pytest file** and verify the new assertions fail.
- [ ] **Step 3: Implement the sender** and replace camera I2C initialization/serving in `app_main.c`.
- [ ] **Step 4: Start guided screening after capture initialization** and restart completed/error sessions after a two-second cooldown.
- [ ] **Step 5: Run focused pytest and `idf.py build` in `firmware_camera`**; expect both to pass.
- [ ] **Step 6: Commit** with `feat(camera): stream scores over UART`.

### Task 3: N16R8 UART receiver and freshness handling

**Files:**
- Modify: `firmware_esp32/main/camera_coprocessor.c`
- Modify: `firmware_esp32/main/CMakeLists.txt`
- Modify: `firmware_esp32/main/app_main.c`
- Modify: `host_pc/tests/test_camera_coprocessor_source.py`

**Interfaces:**
- Consumes: `sg_camera_uart_stream_feed` and UART1 RX on GPIO9.
- Preserves: `sg_camera_coprocessor_init`, `sg_camera_coprocessor_poll`, `sg_camera_coprocessor_control`, and `sg_camera_coprocessor_stage` so callers remain unchanged.
- `sg_camera_coprocessor_control(start)` clears local camera freshness and returns success; it does not claim camera-side synchronization.

- [ ] **Step 1: Add failing tests** requiring UART1/GPIO9, CRC stream parsing, a two-second freshness limit, and removal of I2C transmit/receive calls.
- [ ] **Step 2: Run focused pytest** and verify the assertions fail for the missing UART receiver.
- [ ] **Step 3: Implement UART initialization and parser-driven polling** while retaining the existing score-bus application and five-second valid-face hold.
- [ ] **Step 4: Make start/cancel local session controls** and log `camera UART session armed` rather than `screening control confirmed`.
- [ ] **Step 5: Run focused pytest and `idf.py build` in `firmware_esp32`**; expect both to pass.
- [ ] **Step 6: Commit** with `feat(firmware): receive camera scores over UART`.

### Task 4: Documentation and wiring migration

**Files:**
- Modify: `firmware_camera/README.md`
- Modify: `docs/camera-nmo432-bringup.md`
- Modify: `README.md`
- Test: `host_pc/tests/test_camera_coprocessor_firmware.py`

**Interfaces:**
- Documents the exact single-wire wiring and states that web start is a main-side fusion boundary.

- [ ] **Step 1: Add failing documentation assertions** for GPIO48-to-GPIO9, disconnected GPIO47, UART1 115200, and independent power.
- [ ] **Step 2: Update all three documents** and remove instructions that require the broken score I2C link.
- [ ] **Step 3: Run documentation tests and `git diff --check`**; expect success.
- [ ] **Step 4: Commit** with `docs(camera): document single-wire UART wiring`.

### Task 5: Build, flash, and end-to-end verification

**Files:**
- No source files expected unless evidence identifies a specific defect.

**Interfaces:**
- Camera COM8 sends UART1 scores over GPIO48.
- N16R8 COM3 uploads fused numeric scores over MQTT.

- [ ] **Step 1: Run focused and full host tests** with pytest cache disabled.
- [ ] **Step 2: Build both firmware projects** under the ESP-IDF v5.5.3 PowerShell environment.
- [ ] **Step 3: Flash camera COM8, then N16R8 COM3**.
- [ ] **Step 4: Monitor COM3** and require fresh camera packet logs with non-null F/E/T validity as the user performs the guided poses.
- [ ] **Step 5: Publish one MQTT screening start** and require local session arming, fusion output, and numeric VPS uplink.
- [ ] **Step 6: Verify the VPS device endpoint and demo page** show the latest real device data; no simulated result is permitted.
- [ ] **Step 7: Push `codex/preliminary-demo`** after all verification evidence is recorded.
