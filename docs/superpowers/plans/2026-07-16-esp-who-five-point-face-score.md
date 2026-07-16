# ESP-WHO Five-Point Face Score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute a quality-gated, five-frame-stabilized FAST Face score on the GC2145 camera board and deliver it numerically over I2C to N16R8 fusion.

**Architecture:** A pure camera-side geometry module converts ESP-WHO five-point landmarks into a frame score and signed mouth angle. A temporal filter publishes only the median of five valid frames. Shared register `0x02` carries the numeric result; N16R8 validates it and updates the existing score bus while register `0x01` remains the bbox debug contract.

**Tech Stack:** ESP-IDF 5.5.3, ESP-WHO `HumanFaceDetect`, ESP-DL result landmarks, C/C++, FreeRTOS, I2C slave-v2/master, pytest structural regression tests, ESP-IDF builds, COM3/COM4 hardware verification.

## Global Constraints

- Original audio, images, and landmarks remain local and are never sent to VPS or the LLM.
- Five-point F is a risk feature, not a diagnosis; thresholds are initial engineering values pending measured calibration.
- Invalid, low-quality, incomplete, or stale observations produce unavailable F, never a fabricated healthy score.
- Register `0x01` and USB bbox preview remain backward compatible.
- Register `0x02` is exactly `[status, score, signed_angle_i8, quality]` at address `0x52`.
- S, T, and E remain unavailable in this implementation increment.
- Each completed task is committed and pushed on `codex/preliminary-demo`.

---

### Task 1: Add The Numeric F Wire Contract

**Files:**
- Modify: `firmware_common/camera_scores_protocol.h`
- Modify: `firmware_common/camera_scores_protocol.c`
- Modify: `firmware_esp32/test_apps/camera_protocol/main/test_camera_protocol.c`
- Modify: `host_pc/tests/test_camera_coprocessor_firmware.py`

**Interfaces:**
- Produces: `SG_CAMERA_FACE_METRICS_REGISTER`, `sg_camera_face_metrics_response_t`, `sg_camera_face_metrics_t`, `sg_camera_face_metrics_parse()`, and `sg_camera_face_metrics_encode()`.
- Consumes: existing `SG_CAMERA_I2C_ADDRESS` and protocol result enum.

- [ ] **Step 1: Write failing protocol tests**

Add Unity cases that accept `{1, 72, (uint8_t)(int8_t)-8, 91}`, reject status above 1, score/quality above 100, angle magnitude above 90, and reject a three-byte response. Add structural assertions for register `0x02`, packed size four, parser, and encoder.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
host_pc\.venv\Scripts\python.exe -m pytest host_pc\tests\test_camera_coprocessor_firmware.py -q -p no:cacheprovider
```

Expected: failure because the metrics register and parser do not exist.

- [ ] **Step 3: Implement the four-byte contract**

Add:

```c
#define SG_CAMERA_FACE_METRICS_REGISTER 0x02U

typedef struct __attribute__((packed)) {
    uint8_t status;
    uint8_t score;
    int8_t mouth_angle_deg;
    uint8_t quality;
} sg_camera_face_metrics_response_t;

typedef struct {
    bool valid;
    uint8_t score;
    int8_t mouth_angle_deg;
    uint8_t quality;
} sg_camera_face_metrics_t;
```

The parser accepts status 0 as unavailable, accepts status 1 only with bounded fields, and rejects all other values. The encoder zeroes all value bytes when invalid.

- [ ] **Step 4: Verify GREEN and build the protocol test app**

Run the focused pytest test and:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_idf_task.ps1 -IdfPath E:\esp\v5.5.3\esp-idf -ProjectPath firmware_esp32\test_apps\camera_protocol -Action build
```

Expected: focused tests pass and the Unity firmware builds.

- [ ] **Step 5: Commit and push**

```powershell
git add firmware_common/camera_scores_protocol.* firmware_esp32/test_apps/camera_protocol/main/test_camera_protocol.c host_pc/tests/test_camera_coprocessor_firmware.py
git commit -m "feat(face): add numeric F camera protocol"
git push
```

### Task 2: Implement Quality-Gated Five-Point Geometry

**Files:**
- Create: `firmware_camera/main/face_geometry.h`
- Create: `firmware_camera/main/face_geometry.cpp`
- Create: `firmware_camera/test_apps/face_geometry/CMakeLists.txt`
- Create: `firmware_camera/test_apps/face_geometry/main/CMakeLists.txt`
- Create: `firmware_camera/test_apps/face_geometry/main/test_face_geometry.cpp`
- Modify: `host_pc/tests/test_camera_coprocessor_firmware.py`

**Interfaces:**
- Consumes: integer pixel coordinates for bbox, left/right eye, nose, and left/right mouth.
- Produces: `bool sg_face_geometry_evaluate(const sg_face_geometry_input_t *, sg_face_frame_metrics_t *)`.

- [ ] **Step 1: Write failing geometry tests**

Create Unity tests for level geometry, a displaced mouth corner, equal eye/mouth roll cancellation, small face rejection, short eye distance rejection, off-center nose rejection, and mouth-above-eyes rejection. Assert the level case scores at least 90 and a 20-degree corrected mouth angle scores at most 25.

- [ ] **Step 2: Verify RED**

Run the face-geometry test app build. Expected: compile failure because `face_geometry.h` is absent.

- [ ] **Step 3: Implement the pure geometry module**

Use named constants:

```cpp
constexpr int kMinFaceWidth = 64;
constexpr float kMinEyeDistance = 20.0f;
constexpr float kMaxEyeRollDeg = 25.0f;
constexpr float kAngleHealthyDeg = 2.0f;
constexpr float kAngleZeroDeg = 20.0f;
constexpr float kAsymmetryHealthy = 0.05f;
constexpr float kAsymmetryZero = 0.35f;
```

Compute corrected mouth angle and nose-to-mouth distance asymmetry exactly as specified. Return false and zero the output on any failed quality gate. Calculate quality from normalized face-width, eye-distance, nose-centering, and roll margins, clamped to `0..100`.

- [ ] **Step 4: Verify GREEN**

Build the Unity test app and run structural pytest. Expected: build and tests pass without warnings from the new module.

- [ ] **Step 5: Commit and push**

```powershell
git add firmware_camera/main/face_geometry.* firmware_camera/test_apps/face_geometry host_pc/tests/test_camera_coprocessor_firmware.py
git commit -m "feat(face): compute five-point asymmetry score"
git push
```

### Task 3: Add Five-Frame Median Stabilization

**Files:**
- Create: `firmware_camera/main/face_stabilizer.h`
- Create: `firmware_camera/main/face_stabilizer.c`
- Modify: `firmware_camera/test_apps/face_geometry/main/test_face_geometry.cpp`
- Modify: `firmware_camera/test_apps/face_geometry/main/CMakeLists.txt`

**Interfaces:**
- Consumes: valid `sg_face_frame_metrics_t` samples or an invalid-frame reset.
- Produces: `bool sg_face_stabilizer_push(...)` and `void sg_face_stabilizer_reset(...)` with a stable median result after exactly five valid samples.

- [ ] **Step 1: Write failing temporal tests**

Test that four samples do not publish, the fifth publishes medians, one outlier does not dominate, and an invalid reset requires five new samples.

- [ ] **Step 2: Verify RED**

Build the test app. Expected: failure because stabilizer symbols are missing.

- [ ] **Step 3: Implement fixed-storage median logic**

Use fixed arrays of five scores, signed angles, and qualities; no heap allocation. Copy each array before insertion sort and choose index two. Clear count and buffers on reset.

- [ ] **Step 4: Verify GREEN**

Build the test app. Expected: all geometry and temporal Unity tests compile successfully.

- [ ] **Step 5: Commit and push**

```powershell
git add firmware_camera/main/face_stabilizer.* firmware_camera/test_apps/face_geometry
git commit -m "feat(face): stabilize F over five frames"
git push
```

### Task 4: Integrate Landmarks And Register 0x02 On The Camera Board

**Files:**
- Modify: `firmware_camera/main/camera_capture_adapter.h`
- Modify: `firmware_camera/main/camera_capture_adapter.cpp`
- Modify: `firmware_camera/main/camera_score_target.h`
- Modify: `firmware_camera/main/camera_score_target.c`
- Modify: `firmware_camera/main/app_main.c`
- Modify: `firmware_camera/main/CMakeLists.txt`
- Modify: `host_pc/tests/test_camera_coprocessor_firmware.py`

**Interfaces:**
- Consumes: `dl::detect::result_t::keypoint` for the largest face.
- Produces: bbox at register `0x01` and stable F metrics at register `0x02`.

- [ ] **Step 1: Write failing integration assertions**

Assert the adapter requires ten keypoint integers, calls geometry and stabilizer functions, and never derives tongue or eye. Assert the target selects both registers and serves the matching four-byte response.

- [ ] **Step 2: Verify RED**

Run focused pytest. Expected: failures for missing metrics integration.

- [ ] **Step 3: Integrate largest-face landmarks**

Extend the selected-face helper to retain bbox plus keypoints. Map indexes
`0..4` to left eye, left mouth, nose, right eye, right mouth according to the
ESP-DL MNP alignment template. Evaluate and stabilize before returning the
frame buffer. A no-face or failed gate resets the stabilizer and sets metrics
invalid.

- [ ] **Step 4: Serve both I2C registers**

Store latest bbox and metrics responses under the existing critical-section lock. On register selection, preserve `0x01` behavior and return the metrics response for `0x02`. Log only bounded numeric score, angle, quality, and latency.

- [ ] **Step 5: Verify and build camera firmware**

Run focused pytest and build `firmware_camera` with its `.strokeguard-build` configuration. Expected: tests and build pass.

- [ ] **Step 6: Commit and push**

```powershell
git add firmware_camera/main host_pc/tests/test_camera_coprocessor_firmware.py
git commit -m "feat(face): publish stabilized F from camera"
git push
```

### Task 5: Consume F Metrics In N16R8 Fusion

**Files:**
- Modify: `firmware_esp32/main/camera_coprocessor.h`
- Modify: `firmware_esp32/main/camera_coprocessor.c`
- Modify: `firmware_esp32/main/score_bus.c`
- Modify: `host_pc/tests/test_e1_standalone_firmware.py`

**Interfaces:**
- Consumes: register `0x02` metrics response.
- Produces: valid face score and absolute angle through `sg_score_bus_apply_camera()`; S/T/E remain invalid.

- [ ] **Step 1: Write failing N16R8 assertions**

Assert polling uses `SG_CAMERA_FACE_METRICS_REGISTER`, parses metrics, calls `sg_score_bus_apply_camera(metrics.valid, metrics.score, fabsf(metrics.mouth_angle_deg), false, 0, false, 0, now_us)`, and does not convert bbox into a score.

- [ ] **Step 2: Verify RED**

Run `test_e1_standalone_firmware.py`. Expected: failure because the master still consumes bbox only.

- [ ] **Step 3: Implement metrics polling**

Use the existing write-register, 5 ms settle, and receive sequence with the metrics register. Preserve bounded failure logs and stale handling. Log `camera F score=%u angle=%d quality=%u` only for valid observations.

- [ ] **Step 4: Verify and build N16R8 firmware**

Run focused pytest and `idf.py build` in `firmware_esp32`. Expected: tests and build pass.

- [ ] **Step 5: Commit and push**

```powershell
git add firmware_esp32/main/camera_coprocessor.* firmware_esp32/main/score_bus.c host_pc/tests/test_e1_standalone_firmware.py
git commit -m "feat(face): feed camera F into edge fusion"
git push
```

### Task 6: Full Verification, Flash, And Hardware Acceptance

**Files:**
- Modify: `firmware_camera/README.md`
- Modify: `docs/camera-nmo432-bringup.md`

**Interfaces:**
- Consumes: completed camera and N16R8 firmware.
- Produces: reproducible wiring, flashing, expected logs, limitations, and measured bring-up evidence.

- [ ] **Step 1: Run the full host suite**

```powershell
host_pc\.venv\Scripts\python.exe -m pytest host_pc\tests -q -p no:cacheprovider --basetemp F:\iot_design\.pytest-face-final
```

Expected: all tests pass.

- [ ] **Step 2: Build both production firmware projects**

Build `firmware_camera` and `firmware_esp32` under ESP-IDF 5.5.3. Expected: both binaries fit their configured app partitions.

- [ ] **Step 3: Flash COM4 then COM3**

Flash the camera coprocessor to COM4 and N16R8 firmware to COM3. Do not connect board-to-board 5 V; retain SDA, SCL, and common GND only.

- [ ] **Step 4: Verify live behavior**

Hold a well-lit frontal face steady until five valid samples arrive. Expected COM3 log contains numeric F score, angle, and quality; VPS `/devices/sg-0001/latest` reports numeric `face`; S/T/E remain null. Remove the face and verify F becomes unavailable after the stale interval.

- [ ] **Step 5: Document measured limitations**

Document that thresholds and accuracy remain unvalidated, bbox is not F, five landmarks are not equivalent to 68-point analysis, and the system is a risk prompt rather than a diagnostic device.

- [ ] **Step 6: Clean, commit, and push**

Remove generated pytest and `.strokeguard-build` artifacts, run `git diff --check`, then:

```powershell
git add firmware_camera/README.md docs/camera-nmo432-bringup.md
git commit -m "docs(face): document five-point F bring-up"
git push
```
