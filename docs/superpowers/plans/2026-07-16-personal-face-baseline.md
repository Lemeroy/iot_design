# Personal Face Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the saturated absolute five-point F score with a volatile personal neutral baseline and a responsive three-frame relative score.

**Architecture:** A pure C baseline state machine consumes the existing geometry frames, calibrates from five stable high-quality samples, scores subsequent frames by change from the baseline, and clears after ten seconds without a valid face. The camera adapter publishes the state machine's stable output through the unchanged `0x02` contract.

**Tech Stack:** ESP-IDF 5.5.3, C/C++, Unity on COM4, ESP-WHO five-point geometry, pytest structural tests, COM3/VPS acceptance.

## Global Constraints

- Images, landmarks, and baseline values never leave camera RAM.
- I2C register `0x02` remains exactly four bytes and status `0/1` semantics remain compatible.
- Baseline requires five samples with quality at least 70, angle range at most 2 degrees, and asymmetry range at most 0.03.
- Relative angle score uses `0.5..8` degrees; relative asymmetry score uses `0.01..0.15`.
- Stable output uses a rolling median of three valid samples.
- Ten seconds without valid geometry clears baseline and output state.
- Absolute signed mouth angle remains on the wire for the existing 20-degree veto.
- Thresholds are engineering defaults pending measured calibration; this is not a diagnosis.
- Each task is committed and pushed on `codex/preliminary-demo`.

---

### Task 1: Implement And Test The Baseline State Machine

**Files:**
- Create: `firmware_camera/main/face_baseline.h`
- Create: `firmware_camera/main/face_baseline.c`
- Modify: `firmware_camera/test_apps/face_geometry/main/CMakeLists.txt`
- Modify: `firmware_camera/test_apps/face_geometry/main/test_face_geometry.cpp`
- Modify: `host_pc/tests/test_camera_coprocessor_firmware.py`

**Interfaces:**
- Consumes: `sg_face_frame_metrics_t` and monotonic microseconds.
- Produces: `sg_face_baseline_update()`, `sg_face_baseline_note_invalid()`, `sg_face_baseline_ready()`, and stable relative `sg_face_frame_metrics_t` output.

- [ ] Write failing Unity tests for five-sample calibration, quality/range rejection, relative low/high boundaries, three-frame median, brief invalid retention, and ten-second reset.
- [ ] Build the test app and verify RED because `face_baseline` symbols are absent.
- [ ] Implement fixed-storage calibration and rolling windows with named threshold constants and no heap allocation.
- [ ] Build, flash COM4, and verify every baseline Unity case reports `PASS`.
- [ ] Run focused pytest, commit as `feat(face): add personal neutral baseline`, and push.

### Task 2: Integrate Relative Scoring Into Camera Production Firmware

**Files:**
- Modify: `firmware_camera/main/camera_capture_adapter.cpp`
- Modify: `firmware_camera/main/CMakeLists.txt`
- Modify: `host_pc/tests/test_camera_coprocessor_firmware.py`

**Interfaces:**
- Consumes: existing quality-gated frame metrics.
- Produces: unavailable F during calibration and relative stable F after readiness, through existing `sg_camera_face_metrics_t`.

- [ ] Write failing assertions that the adapter calls baseline update/invalid APIs and no longer calls `sg_face_stabilizer_push()`.
- [ ] Run focused pytest and verify RED.
- [ ] Replace the old five-frame stabilizer with the baseline state machine; log bounded `face baseline ready` and relative F values without logging baseline coordinates or images.
- [ ] Build production camera firmware and run focused tests.
- [ ] Commit as `feat(face): publish relative F from personal baseline` and push.

### Task 3: Flash And Measure Real-Time Response

**Files:**
- Modify: `firmware_camera/README.md`
- Modify: `docs/camera-nmo432-bringup.md`

**Interfaces:**
- Consumes: completed camera firmware and unchanged N16R8 firmware.
- Produces: measured natural, asymmetric, and recovery samples on COM3 and VPS.

- [ ] Flash production camera firmware to COM4; keep N16R8 on COM3 unchanged.
- [ ] Hold a neutral frontal face until five accepted calibration samples complete.
- [ ] Capture at least 10 seconds each of neutral, deliberate one-sided mouth lowering, and recovery.
- [ ] Record observed F ranges and response time without inventing accuracy claims.
- [ ] Confirm VPS latest payload receives the current relative F while S/T/E remain null.
- [ ] Update documentation with behavior and limitations, commit as `docs(face): document personal baseline flow`, and push.

### Task 4: Final Regression And Cleanup

**Files:**
- Verify all files changed above.

**Interfaces:**
- Produces: clean branch with reproducible evidence.

- [ ] Run the complete host pytest suite with a workspace basetemp.
- [ ] Build both production firmware projects under ESP-IDF 5.5.3.
- [ ] Remove `.pytest-*`, camera `.strokeguard-build`, and test-app build artifacts.
- [ ] Run `git diff --check`, verify `git status --short` is empty, and confirm all commits are pushed.
