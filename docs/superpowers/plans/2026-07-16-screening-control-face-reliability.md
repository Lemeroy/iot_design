# Screening Control and Face Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reliably start/cancel camera screening under I2C polling and produce a stable, validity-aware F score from real ESP-WHO landmarks.

**Architecture:** Camera control writes bypass the ordinary I2C event queue and enter a latest-value latch. The N16R8 confirms control by polling the stage with bounded retries. The F stage accepts two eligible landmark samples in a five-frame window within a 20-second deadline and never substitutes a constant score.

**Tech Stack:** ESP-IDF 5.5.3, FreeRTOS, ESP-WHO/ESP-DL, ESP32-S3 N16R8, I2C target/controller, C/C++, pytest structural tests, Unity target tests.

## Global Constraints

- Raw images, bounding boxes, landmarks, and personal baselines remain local.
- Missing, stale, or low-quality F stays unavailable; no fallback score is allowed.
- Existing MQTT topics, numeric uplink schema, and I2C register numbers remain unchanged.
- F is a risk-screening signal and must not be described as a diagnosis.
- Every completed implementation unit is committed and pushed.

---

### Task 1: Reliable Camera Control Latch

**Files:**
- Modify: `firmware_camera/main/camera_score_target.c`
- Test: `host_pc/tests/test_camera_score_target_source.py`

**Interfaces:**
- Consumes: I2C write `[SG_CAMERA_CONTROL_REGISTER, action]`.
- Produces: existing `bool sg_camera_score_target_take_control(sg_screening_control_t *control)` with latest-action semantics.

- [ ] **Step 1: Write failing structural tests**

Add tests that require the receive callback to latch valid control writes before the ordinary `xQueueSendFromISR` path, require an overwrite-safe critical section, and require queue overflow logging/counters for non-control traffic.

- [ ] **Step 2: Verify RED**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_camera_score_target_source.py`

Expected: FAIL because control still enters the shared event queue.

- [ ] **Step 3: Implement minimal latch**

In `camera_target_on_receive`, validate the two-byte control packet, write `pending_control` and `control_pending` under `response_lock`, and return without enqueueing. Preserve the register event path for one-byte writes. Check `xQueueSendFromISR` return values without logging secrets or image data.

- [ ] **Step 4: Verify GREEN and build camera firmware**

Run the focused pytest command, then:

```powershell
. C:\Espressif\tools\Microsoft.v5.5.3.PowerShell_profile.ps1
idf.py -C firmware_camera build
```

Expected: focused tests pass and firmware links successfully.

- [ ] **Step 5: Commit and push**

Commit message: `fix(camera): latch screening controls reliably`

### Task 2: N16R8 Control Confirmation

**Files:**
- Modify: `firmware_esp32/main/camera_coprocessor.c`
- Modify: `firmware_esp32/main/camera_coprocessor.h`
- Modify: `firmware_esp32/main/app_main.c`
- Test: `host_pc/tests/test_camera_coprocessor_source.py`

**Interfaces:**
- Consumes: `sg_camera_coprocessor_control(action)`.
- Produces: bounded confirmation that `start -> SG_STAGE_FACE` and `cancel -> SG_STAGE_IDLE`.

- [ ] **Step 1: Write failing confirmation tests**

Require fixed retry count/delay constants, an expected-stage helper, success logging only after observed stage confirmation, and an error return after all retries.

- [ ] **Step 2: Verify RED**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_camera_coprocessor_source.py`

Expected: FAIL because the current function returns after one unconfirmed write.

- [ ] **Step 3: Implement bounded write-confirm loop**

Transmit the unchanged two-byte command, delay for the camera loop, poll the stage response, and accept only the expected stage. Retry a fixed small count. Return `ESP_ERR_TIMEOUT` on no acknowledgement and preserve offline fusion/MQTT behavior.

- [ ] **Step 4: Verify GREEN and build N16R8 firmware**

Run the focused pytest command, then:

```powershell
. C:\Espressif\tools\Microsoft.v5.5.3.PowerShell_profile.ps1
idf.py -C firmware_esp32 build
```

Expected: focused tests pass and firmware links successfully.

- [ ] **Step 5: Commit and push**

Commit message: `fix(edge): confirm camera screening controls`

### Task 3: Validity-Aware F Acquisition

**Files:**
- Modify: `firmware_camera/main/screening_session.c`
- Modify: `firmware_camera/main/screening_session.h`
- Modify: `firmware_camera/main/camera_capture_adapter.cpp`
- Test: `host_pc/tests/test_screening_session_source.py`
- Test: `firmware_camera/test_apps/screening_session/main/test_screening_session.c`

**Interfaces:**
- Consumes: `sg_screening_sample_t.face_ready` from valid ESP-WHO five-point geometry and ready personal baseline.
- Produces: transition from `FACE` only after two eligible samples in the latest five sampled frames; bounded `ERROR` with no numeric F otherwise.

- [ ] **Step 1: Add failing host and Unity tests**

Cover five-frame-window completion, temporary invalid recovery, deadline failure, and no score from bbox-only input.

- [ ] **Step 2: Verify RED**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_screening_session_source.py`

Expected: FAIL because the current sample counter does not enforce consecutiveness or expose bounded F diagnostics.

- [ ] **Step 3: Implement eligible-sample state**

Use a five-bit F validity window with a two-sample threshold, retain the overall stage start time, use a 20-second F deadline, and retain median/baseline scoring. Configure detector thresholds at `0.40/0.45`, retain bbox display for at most two misses without validating F, and add rate-limited local rejection reasons without logging coordinates.

- [ ] **Step 4: Verify tests and both builds**

Run focused host tests, the existing full host suite, and both ESP-IDF builds. Expected: zero host failures and two successful links.

- [ ] **Step 5: Commit and push**

Commit message: `feat(camera): stabilize guided face acquisition`

### Task 4: Flash and End-to-End Acceptance

**Files:**
- Modify: `docs/demo-acceptance-checklist.md`
- Modify: `docs/camera-nmo432-bringup.md`

**Interfaces:**
- Consumes: COM4 camera firmware, COM3 N16R8 firmware, public demo, MQTT/VPS.
- Produces: measured acceptance record without invented accuracy or latency.

- [ ] **Step 1: Flash production firmware**

With board-to-board SDA/SCL/GND retained and no board-to-board 5 V:

```powershell
. C:\Espressif\tools\Microsoft.v5.5.3.PowerShell_profile.ps1
idf.py -C firmware_camera -p COM4 flash
idf.py -C firmware_esp32 -p COM3 flash
```

- [ ] **Step 2: Verify guided screening**

Confirm serial evidence for MQTT control type 1, camera control receipt, `IDLE -> FACE`, stage progression, numeric F/E/T uplink, and advice downlink. Confirm CSI/MQTT continue during screening.

- [ ] **Step 3: Verify negative cases**

Obscure the lens and repeat. The session must end unavailable/error with no fabricated F. Remove the obstruction and verify a new session can recover.

- [ ] **Step 4: Record measured results and run final checks**

Update only observed outcomes, then run full pytest, `git diff --check`, both builds, and `git status --short`.

- [ ] **Step 5: Commit and push**

Commit message: `test(demo): verify reliable guided screening`
