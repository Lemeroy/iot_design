# Guided Eye And Tongue Screening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a web-started, device-local guided screening that publishes real F/E/T values from the GC2145 camera board through N16R8 and VPS without uploading images.

**Architecture:** Shared fixed-size I2C messages define control, stage, E, and T registers. The camera coprocessor owns the guided state machine and fixed-storage RGB ROI algorithms; N16R8 forwards authenticated MQTT control, polls results, fuses locally, and uploads numeric state. FastAPI publishes control and exposes state to the existing authenticated demo UI.

**Tech Stack:** ESP-IDF 5.5.3, ESP-WHO/ESP-DL, C/C++, Unity, I2C, ESP-MQTT, FastAPI, Pydantic, Paho MQTT, vanilla HTML/CSS/JavaScript, pytest.

## Global Constraints

- Raw images, ROIs, landmarks, and personal baselines remain local and never enter MQTT, InfluxDB, VPS, or the LLM.
- Missing or quality-rejected E/T values remain invalid; no layer substitutes `100`.
- T is auxiliary only and never triggers a single-item danger veto.
- Existing F register `0x02` and existing advice downlink remain compatible.
- Stage durations of 3/2/2/2/3 seconds and all image thresholds are engineering defaults pending real-device measurement.
- Every task ends with tests, a commit, and a push to `codex/preliminary-demo`.

---

### Task 1: Shared I2C Screening Protocol

**Files:**
- Modify: `firmware_common/camera_scores_protocol.h`
- Modify: `firmware_common/camera_scores_protocol.c`
- Modify: `firmware_camera/test_apps/face_geometry/main/test_face_geometry.cpp`
- Modify: `host_pc/tests/test_camera_coprocessor_firmware.py`

**Interfaces:**
- Produces: registers `SG_CAMERA_EYE_REGISTER=0x03`, `SG_CAMERA_TONGUE_REGISTER=0x04`, `SG_CAMERA_CONTROL_REGISTER=0x10`, `SG_CAMERA_STAGE_REGISTER=0x11`.
- Produces: four-byte `sg_camera_modal_response_t`, control enum, and stage enum shared by both boards.

- [ ] Add failing protocol tests asserting all register values, `sizeof(sg_camera_modal_response_t) == 4`, signed offset round trips, and rejection of invalid status/score/stage bytes.
- [ ] Run `python -m pytest host_pc/tests/test_camera_coprocessor_firmware.py -q` and build the Unity app; verify failures are caused by missing protocol symbols.
- [ ] Add the exact shared types and helpers:

```c
typedef struct __attribute__((packed)) {
    uint8_t valid;
    uint8_t score;
    int8_t signed_value;
    uint8_t quality;
} sg_camera_modal_response_t;

typedef enum { SG_SCREENING_CANCEL = 0, SG_SCREENING_START = 1 } sg_screening_control_t;
typedef enum {
    SG_STAGE_IDLE = 0, SG_STAGE_FACE, SG_STAGE_EYE_CENTER, SG_STAGE_EYE_LEFT,
    SG_STAGE_EYE_RIGHT, SG_STAGE_TONGUE, SG_STAGE_DONE, SG_STAGE_ERROR
} sg_screening_stage_t;
```

- [ ] Implement strict encode/parse functions using byte assignment, not struct pointer casting.
- [ ] Re-run focused pytest and Unity tests; expect all protocol cases to pass.
- [ ] Commit and push as `feat(protocol): add guided screening registers`.

### Task 2: Pure E Pupil-Tracking Kernel

**Files:**
- Create: `firmware_camera/main/eye_tracking.h`
- Create: `firmware_camera/main/eye_tracking.cpp`
- Create: `firmware_camera/test_apps/eye_tongue/CMakeLists.txt`
- Create: `firmware_camera/test_apps/eye_tongue/main/CMakeLists.txt`
- Create: `firmware_camera/test_apps/eye_tongue/main/test_eye_tongue.cpp`
- Modify: `host_pc/tests/test_camera_coprocessor_firmware.py`

**Interfaces:**
- Consumes: RGB888 image, width/height, two eye centers, inter-eye distance, and eye-line angle.
- Produces: `bool sg_eye_measure(const sg_eye_input_t *, sg_eye_measurement_t *)` with normalized left/right horizontal centroids and quality `0..100`.

- [ ] Write failing Unity tests using small synthetic RGB images for centered pupils, same-direction displacement, opposite-direction displacement, low contrast, implausible dark area, and ROI clipping.
- [ ] Build the test app and verify RED because `sg_eye_measure` is absent.
- [ ] Implement bounded ROI extraction, integer intensity, histogram-derived dark threshold, dark-area gate, weighted centroid, and contrast-derived quality without heap allocation.
- [ ] Add `sg_eye_score_sequence(center, left, right, out)` and failing tests requiring common-direction travel, minimum travel, binocular agreement, and `0..100` bounds.
- [ ] Implement the minimum sequence scorer and run all eye tests to GREEN.
- [ ] Run focused host structural tests to ensure eye code contains no network, file, or allocation API.
- [ ] Commit and push as `feat(camera): add local eye movement scoring`.

### Task 3: Pure Auxiliary T Segmentation Kernel

**Files:**
- Create: `firmware_camera/main/tongue_deviation.h`
- Create: `firmware_camera/main/tongue_deviation.cpp`
- Modify: `firmware_camera/test_apps/eye_tongue/main/CMakeLists.txt`
- Modify: `firmware_camera/test_apps/eye_tongue/main/test_eye_tongue.cpp`
- Modify: `host_pc/tests/test_camera_coprocessor_firmware.py`

**Interfaces:**
- Consumes: RGB888 lower-face ROI and roll-corrected facial midline.
- Produces: `bool sg_tongue_measure(const sg_tongue_input_t *, sg_tongue_measurement_t *)` with signed offset percentage, auxiliary score, and quality.

- [ ] Add failing synthetic-image tests for centered tongue, left/right offset, absent red component, tiny component, border-touching component, and low saturation.
- [ ] Verify RED because `sg_tongue_measure` is absent.
- [ ] Implement red-dominance/saturation selection, fixed-size scanline connected-component labeling, geometry gates, centroid, signed offset, and quality without heap allocation.
- [ ] Implement a continuous configurable score mapping where zero offset is highest and large absolute offset is lower; clamp every output to its wire range.
- [ ] Run the eye/tongue Unity app and focused privacy/structure pytest to GREEN.
- [ ] Commit and push as `feat(camera): add auxiliary tongue deviation scoring`.

### Task 4: Camera Guided State Machine And I2C Serving

**Files:**
- Create: `firmware_camera/main/screening_session.h`
- Create: `firmware_camera/main/screening_session.c`
- Modify: `firmware_camera/main/camera_capture_adapter.h`
- Modify: `firmware_camera/main/camera_capture_adapter.cpp`
- Modify: `firmware_camera/main/camera_score_target.c`
- Modify: `firmware_camera/main/app_main.c`
- Modify: `firmware_camera/main/CMakeLists.txt`
- Modify: `firmware_camera/test_apps/eye_tongue/main/test_eye_tongue.cpp`

**Interfaces:**
- Consumes: start/cancel writes on `0x10`, monotonic time, face geometry, eye measurements, and tongue measurements.
- Produces: stage on `0x11`, E on `0x03`, T on `0x04`, and unchanged F on `0x02`.

- [ ] Write failing state tests for exact stage order, three accepted samples, timeout to error, cancel to idle, duplicate start restart, and invalid values before completion.
- [ ] Verify RED, then implement `sg_screening_session_start`, `cancel`, `update`, `stage`, `eye_result`, and `tongue_result` with fixed RAM state.
- [ ] Integrate the state machine into the existing RGB888 frame path; derive eye and lower-face ROIs only when their stage is active.
- [ ] Extend the I2C receive callback so a two-byte `[0x10, command]` write changes state, while one-byte writes remain register selection.
- [ ] Serve all new read registers through the existing event queue and keep ISR callbacks allocation-free.
- [ ] Build production camera firmware and the Unity app; run focused pytest.
- [ ] Flash COM4 and verify serial stage transitions with images obscured first, then a guided valid run.
- [ ] Commit and push as `feat(camera): run guided F E T screening`.

### Task 5: N16R8 Control, Polling, Fusion, And Numeric Uplink

**Files:**
- Modify: `firmware_esp32/main/camera_coprocessor.h`
- Modify: `firmware_esp32/main/camera_coprocessor.c`
- Modify: `firmware_esp32/main/sg_mqtt.h`
- Modify: `firmware_esp32/main/sg_mqtt.c`
- Modify: `firmware_esp32/main/cloud_contract.h`
- Modify: `firmware_esp32/main/cloud_contract.c`
- Modify: `firmware_esp32/main/app_main.c`
- Modify: `host_pc/tests/test_e1_standalone_firmware.py`
- Modify: `host_pc/tests/test_e1_cloud_contract.py`

**Interfaces:**
- Consumes: MQTT `screening_control` downlink and camera registers `0x03/0x04/0x11`.
- Produces: score-bus E/T values, immediate uplink on stage changes, and uplink field `screening_stage`.

- [ ] Add failing tests for strict start/cancel JSON parsing, rejection of unknown actions, I2C command writes, E/T validity propagation, stage serialization, and no media fields.
- [ ] Verify focused tests fail for missing APIs.
- [ ] Generalize the downlink callback to a tagged event containing either advice or screening control; keep existing advice age validation unchanged.
- [ ] Add `sg_camera_coprocessor_control()` and extend polling to parse stage/E/T, writing only valid scores into `sg_score_bus`.
- [ ] Extend numeric uplink JSON with a bounded `screening_stage`; trigger publish when the stage changes while retaining periodic publication.
- [ ] Build N16R8 firmware, run focused host tests, flash COM3, and verify I2C stage/E/T logs.
- [ ] Commit and push as `feat(edge): bridge guided screening to MQTT`.

### Task 6: Authenticated VPS Start Endpoint And State Schema

**Files:**
- Modify: `cloud/backend/app/schemas.py`
- Modify: `cloud/backend/app/mqtt_bridge.py`
- Modify: `cloud/backend/app/demo_api.py`
- Modify: `host_pc/tests/test_demo_api.py`
- Modify: `host_pc/tests/test_e1_cloud_contract.py`

**Interfaces:**
- Consumes: authenticated, device-bound `POST /demo/api/screening` with `{"action":"start"}` or `{"action":"cancel"}`.
- Produces: QoS 1 MQTT control publish, `screening_stage` in `GET /demo/api/device`, and authenticated `/demo/api/ws` state pushes.

- [ ] Write failing API tests for unauthenticated, unbound, offline, invalid-action, start, and cancel requests; assert the topic matches the bound device and payload contains no user-supplied device ID.
- [ ] Add strict Pydantic request/stage fields and a bridge method `publish_screening_control(device_id, action)`.
- [ ] Implement the endpoint using the signed session's bound device, online check, fixed action allowlist, and MQTT connectivity check.
- [ ] Include bounded stage in the monitor response while preserving old-device compatibility when the field is absent.
- [ ] Add an authenticated WebSocket endpoint that validates the signed cookie and bound device, sends a snapshot whenever the bridge cache generation changes, sends no raw MQTT payload, and closes cleanly on logout/session expiry.
- [ ] Add WebSocket tests for missing/invalid session, unbound session, first snapshot, changed-generation push, and disconnect cleanup.
- [ ] Run demo API, cloud contract, auth, and MQTT bridge tests.
- [ ] Commit and push as `feat(cloud): add authenticated screening control`.

### Task 7: Preliminary Demo Guided UI

**Files:**
- Modify: `cloud/backend/app/static/demo/index.html`
- Modify: `cloud/backend/app/static/demo/app.css`
- Modify: `cloud/backend/app/static/demo/app.js`
- Modify: `host_pc/tests/test_demo_web.py`

**Interfaces:**
- Consumes: `/demo/api/screening`, `/demo/api/ws`, and `/demo/api/device` stage/F/E/T/advice fields.
- Produces: one Start/Cancel control, prominent current instruction, compact progress, measured scores, retry/error state, and advice.

- [ ] Write failing DOM/source tests for authenticated start/cancel calls, WebSocket connection/reconnect, five-second polling fallback, disabled controls while offline, stage-to-Chinese-instruction mapping, missing-value display, and no simulation path.
- [ ] Add a compact screening command bar and stage progress without nesting cards or changing the existing login/device-connect flow.
- [ ] Implement start/cancel requests and WebSocket state updates; on socket close or error automatically poll `/demo/api/device` every five seconds until WebSocket reconnects.
- [ ] Map stages to concise prompts: face front, center gaze, look left, look right, extend tongue, complete, retry.
- [ ] Keep F/E/T unavailable until valid server data arrives and label T as auxiliary.
- [ ] Run demo web/API tests and inspect desktop/mobile layouts in a browser screenshot with no overlap or clipped text.
- [ ] Commit and push as `feat(demo): add guided screening controls`.

### Task 8: End-To-End Hardware And VPS Acceptance

**Files:**
- Modify: `firmware_camera/README.md`
- Modify: `docs/camera-nmo432-bringup.md`
- Modify: `README.md`

**Interfaces:**
- Produces: reproducible flashing, guided demonstration, measured observations, and known limitations.

- [ ] Deploy the updated cloud backend to `/opt/strokeguard/cloud`, restart native services, and verify health locally and through `http://106.75.229.61:8000/health`.
- [ ] Flash COM4 camera and COM3 N16R8 production firmware using `C:\Espressif\tools\Microsoft.v5.5.3.PowerShell_profile.ps1`.
- [ ] Start a web screening and capture evidence at every boundary: API accepted, downlink received, camera stage advanced, E/T registers valid, numeric uplink cached, and advice returned.
- [ ] Repeat with camera obscured and verify retry/unavailable instead of `100`.
- [ ] Record measured device timing and observed limitations without accuracy claims.
- [ ] Run the complete host pytest suite, build both firmware projects, and run `git diff --check`.
- [ ] Remove generated test builds, pytest caches, and logs; update the three documents with exact commands and safety language.
- [ ] Commit and push as `docs(demo): document guided screening flow`.
