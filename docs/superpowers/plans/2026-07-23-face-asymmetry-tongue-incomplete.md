# Face Asymmetry and Tongue Incomplete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect upright one-sided mouth droop more reliably and explicitly keep an uncompleted tongue action out of fusion.

**Architecture:** Extend the camera-side five-point geometry score with a compensated corner-height signal and take the minimum of three local asymmetry scores. Keep the existing invalid/empty T contract and update the web copy for stage error.

**Tech Stack:** ESP-IDF v5.5.3, ESP-WHO five-point landmarks, C/C++, Python pytest, FastAPI static demo.

## Global Constraints

- Raw audio/video remains local.
- F/E/T are screening prompts, not diagnosis.
- No random or simulated medical score is introduced.
- T unavailable means `status=0` and is excluded from fusion.

### Task 1: Face Geometry Regression

**Files:**
- Modify: `firmware_camera/test_apps/face_geometry/main/test_face_geometry.cpp`
- Modify: `host_pc/tests/test_camera_coprocessor_firmware.py`

- [ ] Add a failing regression for a level head with one mouth corner displaced vertically.
- [ ] Run the focused test and confirm it fails against the current single-signal score.
- [ ] Keep the test threshold at F `<= 35` and retain the frontal-face high-score case.

### Task 2: Camera Geometry Implementation

**Files:**
- Modify: `firmware_camera/main/face_geometry.cpp`
- Modify: `firmware_camera/main/face_geometry.h` only if the new diagnostic metric is exposed.

- [ ] Compute eye-line-compensated left/right mouth-corner height difference.
- [ ] Score mouth angle, compensated height difference, and nose distance asymmetry separately.
- [ ] Set `out->score` to the bounded minimum of the three scores.
- [ ] Run focused host/source tests and rebuild the camera production firmware.

### Task 3: Tongue Incomplete Contract and Copy

**Files:**
- Modify: `firmware_camera/main/screening_session.c` only if a regression shows a valid T result leaks on timeout.
- Modify: `host_pc/tests/test_screening_session_source.py`.
- Modify: `cloud/backend/app/static/demo/app.js`.
- Modify: `host_pc/tests/test_demo_web.py`.

- [ ] Add a regression proving tongue timeout enters error with no valid tongue result.
- [ ] Make the web error copy state that the tongue action was incomplete and T was excluded.
- [ ] Run focused web/session tests.

### Task 4: Full Verification and Device Delivery

**Files:**
- No additional source files.

- [ ] Run the full host suite with cache disabled.
- [ ] Build and flash camera production firmware to COM9.
- [ ] Build and flash main production firmware to COM3 if its binary changed.
- [ ] Verify upright neutral face, one-sided mouth drop, tongue incomplete, Wi-Fi, MQTT, and no raw media upload.
- [ ] Commit only task-related files and push `codex/preliminary-demo`.
