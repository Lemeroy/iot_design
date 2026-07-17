# Speech Score Retention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retain the last valid S score for five minutes without allowing stale speech to veto fusion.

**Architecture:** `score_bus.c` owns the independent S retention boundary and veto downgrade. `app_main.c` decides which terminal speech reasons preserve or clear the cached score and clears it when a new guided screening starts.

**Tech Stack:** ESP-IDF 5.5.3, FreeRTOS, Unity, C.

## Global Constraints

- Speech retention is exactly `300000` milliseconds.
- Retained speech never has veto eligibility.
- I/O failure, reboot, and new screening clear retained speech.
- Raw audio never leaves the device.

---

### Task 1: Score bus retention boundary

**Files:**
- Modify: `firmware_esp32/main/score_bus.h`
- Modify: `firmware_esp32/main/score_bus.c`
- Test: `firmware_esp32/test_apps/e1_core/main/test_e1_core.c`

- [ ] Add failing Unity tests for availability at 300 seconds, expiry after the boundary, and stale veto downgrade.
- [ ] Add `SG_SPEECH_RETAIN_MS 300000U` and use it only for S snapshots.
- [ ] Preserve the original veto flag only while S is inside the caller's real-time `stale_ms` window.
- [ ] Build the E1 Unity target.

### Task 2: Window and screening clear policy

**Files:**
- Modify: `firmware_esp32/main/app_main.c`
- Test: `host_pc/tests/test_e1_standalone_firmware.py`

- [ ] Add source-contract tests proving only `SG_SPEECH_REASON_IO_ERROR` clears an unavailable speech window.
- [ ] Preserve S for ordinary unavailable terminal windows.
- [ ] Clear S before starting a new guided screening.
- [ ] Build production N16R8 firmware and run focused host tests.

### Task 3: Device delivery

- [ ] Commit and push the implementation.
- [ ] Flash production firmware to COM3 without erasing NVS.
- [ ] Verify boot, NMO432 continuous windows, MQTT uplink, and retained S behavior from serial logs.
