# Continuous F/S/E Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Continuously refresh F, preliminary S, and preliminary E on the standalone mirror while preserving guided E priority, guided-only T, numeric-only cloud data, and conservative medical behavior.

**Architecture:** The N16R8 retains fresh F for five seconds and runs successive four-second NMO432 windows from boot. The camera board measures pupils whenever landmarks exist, feeds a bounded continuous tracker, and selects a fresh guided E result over rolling E for 30 seconds. Existing score fields and I2C register sizes remain unchanged.

**Tech Stack:** ESP-IDF 5.5.3, ESP32-S3 N16R8, ESP-WHO, ESP-DL, FreeRTOS, C/C++17, I2C, ESP-MQTT, Unity, pytest, vanilla JavaScript, COM3/COM4 hardware tests.

## Global Constraints

- F retention is five seconds after detector loss; camera I2C failure clears camera scores immediately.
- S uses consecutive non-overlapping four-second windows and starts without a screening command.
- Invalid S windows clear old S and never write zero; `speech_veto_eligible` remains false.
- PCM, encoded audio, MFCC, FFT bins, embeddings, and fingerprints remain local and are never serialized.
- Continuous E requires current bbox/landmarks and bounded valid pupil samples.
- Guided center/left/right E overrides rolling E for 30 seconds, then rolling E resumes.
- Natural or guided preliminary E cannot independently upgrade the level to warning.
- T remains guided-only; Arm remains unmeasured; no clinical performance claims are introduced.
- Every completed task is committed and pushed to `codex/preliminary-demo`.

---

### Task 1: Five-Second Face Retention

**Files:**
- Modify: `firmware_esp32/main/camera_coprocessor.c`
- Modify: `host_pc/tests/test_camera_coprocessor_source.py`
- Modify: `host_pc/tests/test_e1_standalone_firmware.py`

**Interfaces:**
- Consumes: valid/invalid face observations and `esp_timer_get_time()`.
- Produces: fresh F for at most `SG_CAMERA_FACE_HOLD_US = 5000000LL`; transport failure remains immediate unavailable.

- [ ] **Step 1: Write failing source tests**

Require a named five-second constant, require the detector-miss path to compare
against it, and require `publish_unavailable` to remain in the I2C error path:

```python
assert "SG_CAMERA_FACE_HOLD_US 5000000LL" in source
assert "now_us - face_seen_us > SG_CAMERA_FACE_HOLD_US" in source
assert source.index("if (err != ESP_OK)") < source.index("publish_unavailable(now_us)")
```

- [ ] **Step 2: Run RED**

```powershell
host_pc\.venv\Scripts\python.exe -m pytest host_pc\tests\test_camera_coprocessor_source.py host_pc\tests\test_e1_standalone_firmware.py -q --basetemp=F:\iot_design\.pytest-continuous-f-red
```

Expected: failure because the current hold constant is two seconds.

- [ ] **Step 3: Implement the named five-second hold**

Rename `SG_CAMERA_STALE_US` to `SG_CAMERA_FACE_HOLD_US`, set it to
`5000000LL`, and change only the detector-miss expiry comparison. Do not change
the I2C failure branch, `publish_unavailable`, or global score freshness.

- [ ] **Step 4: Verify and commit**

Run the focused tests and production N16R8 build. Expected: all tests pass and
the firmware image remains within the app partition.

```powershell
git add firmware_esp32/main/camera_coprocessor.c host_pc/tests/test_camera_coprocessor_source.py host_pc/tests/test_e1_standalone_firmware.py
git commit -m "feat(face): retain valid score for five seconds"
git push origin codex/preliminary-demo
```

### Task 2: Continuous Four-Second Speech Windows

**Files:**
- Modify: `firmware_esp32/main/speech_screening.h`
- Modify: `firmware_esp32/main/audio_nmo432.h`
- Modify: `firmware_esp32/main/audio_nmo432.c`
- Modify: `firmware_esp32/main/app_main.c`
- Modify: `firmware_esp32/test_apps/e1_core/main/test_e1_core.c`
- Modify: `host_pc/tests/test_e1_standalone_firmware.py`

**Interfaces:**
- Consumes: valid NMO432 20 ms blocks continuously after audio initialization.
- Produces: `sg_speech_result_t.window_id`, incremented once for every completed or rejected four-second window; the latest completed result remains readable until the next window finishes.

- [ ] **Step 1: Write failing continuous-window tests**

Add structural assertions that the audio task starts the engine before its
loop, automatically restarts after COMPLETE/RETRY, and no longer depends on
`SG_STAGE_DONE`, `s_screening_requested`, or speech start/cancel calls in
`app_main.c`.

Add Unity coverage for two consecutive windows: a valid speech-like window
followed by silence. Assert the first publishes an available result with
`window_id=1`; the second publishes unavailable with `window_id=2` and a
bounded reason. Assert guided camera start/cancel cannot reset the speech
window.

- [ ] **Step 2: Run RED**

Run `test_e1_standalone_firmware.py` and build the e1_core Unity app. Expected:
failure because current audio starts only after camera DONE and holds one
terminal result.

- [ ] **Step 3: Make the audio task own continuous lifecycle**

Add `uint32_t window_id` to `sg_speech_result_t`. Keep it zero inside the pure
single-window engine. In `audio_diagnostic_task`:

1. initialize and start `speech_context` before entering the loop;
2. process every valid block;
3. when state is COMPLETE or RETRY, snapshot the terminal result, set
   `window_id=++window_id`, publish it under the existing critical section,
   log aggregate values, and immediately call `sg_speech_screening_start` for
   the next window;
4. on repeated I2S read failures, publish an unavailable IO-error window and
   restart without blocking camera/CSI.

Remove the speech command queue and public start/cancel APIs. `app_main` tracks
`last_speech_window_id`; on a new available result it calls:

```c
sg_score_bus_set_speech(result.score, result.p_clear, false, now_us);
```

On a new unavailable result it calls `sg_score_bus_clear_speech()`. Either
change triggers a fresh local fusion snapshot and immediate numeric MQTT
publish. Camera screening controls no longer touch S or map S RETRY to camera
stage error.

- [ ] **Step 4: Verify and commit**

Run focused pytest, e1_core build, and production N16R8 build. Inspect
`cloud_contract.c` for prohibited audio fields.

```powershell
git add firmware_esp32/main/speech_screening.h firmware_esp32/main/audio_nmo432.* firmware_esp32/main/app_main.c firmware_esp32/test_apps/e1_core/main/test_e1_core.c host_pc/tests/test_e1_standalone_firmware.py
git commit -m "feat(speech): monitor continuous local windows"
git push origin codex/preliminary-demo
```

### Task 3: Continuous Eye Tracker With Guided Override

**Files:**
- Create: `firmware_camera/main/eye_continuous.h`
- Create: `firmware_camera/main/eye_continuous.cpp`
- Modify: `firmware_camera/main/eye_tracking.h`
- Modify: `firmware_camera/main/camera_capture_adapter.cpp`
- Modify: `firmware_camera/main/CMakeLists.txt`
- Modify: `firmware_camera/test_apps/eye_tongue/main/CMakeLists.txt`
- Modify: `firmware_camera/test_apps/eye_tongue/main/test_eye_tongue.cpp`
- Modify: `host_pc/tests/test_camera_coprocessor_firmware.py`

**Interfaces:**
- Consumes: `sg_eye_measurement_t` from every frame with current valid landmarks.
- Produces: `sg_eye_continuous_result_t { valid, score, binocular_difference, quality }` from a fixed 12-sample ring, with six valid samples required and at most two consecutive invalid samples tolerated.
- Produces: pure `sg_eye_select_result(continuous, guided, guided_us, now_us, out)` that applies the 30-second guided override without hidden state.

- [ ] **Step 1: Write failing tracker and integration tests**

Add Unity cases for:

```cpp
TEST_CASE("continuous eye accepts coordinated stable samples", "[eye_continuous]")
TEST_CASE("continuous eye lowers discordant motion", "[eye_continuous]")
TEST_CASE("continuous eye tolerates two blink dropouts", "[eye_continuous]")
TEST_CASE("continuous eye expires after prolonged dropout", "[eye_continuous]")
TEST_CASE("guided eye overrides rolling result for thirty seconds", "[eye_continuous]")
```

Structural tests require `sg_eye_measure` outside the guided-stage condition,
the fixed 12-sample capacity, minimum six samples, `30000000LL` override age,
and unchanged four-byte I2C modal response.

- [ ] **Step 2: Run RED**

Build `firmware_camera/test_apps/eye_tongue` and run the focused camera pytest.
Expected: missing continuous tracker files and symbols.

- [ ] **Step 3: Implement bounded rolling eye scoring**

The context stores 12 measurements, current count/index, and consecutive
invalid count. For adjacent valid samples calculate left/right deltas. Normalize:

```cpp
coherence = clamp(1.0f - mean(abs(delta_left - delta_right)) / 40.0f, 0, 1);
quality = mean(sample.quality) / 100.0f;
usable = valid_samples / 12.0f;
score = round(100 * (0.45f * coherence + 0.35f * quality + 0.20f * usable));
```

Set `binocular_difference` to the clamped mean delta disagreement. Fewer than
six valid samples is unavailable. One or two invalid frames preserve the
rolling result; the third clears the ring and result.

- [ ] **Step 4: Integrate source precedence in camera capture**

Build the eye input and call `sg_eye_measure` whenever `selected.landmarks_valid`
and the current bbox is valid, regardless of stage. Feed the measurement or
invalid marker into the rolling tracker. Reuse the same measurement as the
guided session sample only in EYE_CENTER/EYE_LEFT/EYE_RIGHT stages.

Cache the first successful guided sequence result with its completion time.
Starting a new guided session clears that cache. Output guided metrics while
`now_us - guided_eye_us <= 30000000LL`; otherwise output the continuous result.
Call `sg_eye_select_result` for this choice so Unity can test exact boundary,
negative time, missing guided data, and expiry. Failed guided stages do not
replace a valid rolling result. T logic remains inside `SG_STAGE_TONGUE` only.

- [ ] **Step 5: Disable E-only warning escalation**

Modify `firmware_esp32/main/fusion.c` and the e1_core tests so E still
contributes its configured weight but no E threshold alone upgrades level to
warning. Leave CSI warning and F veto behavior unchanged.

- [ ] **Step 6: Verify and commit**

Build the eye_tongue Unity app, camera production firmware, e1_core app, and
N16R8 production firmware; run focused pytest.

```powershell
git add firmware_camera/main/eye_continuous.* firmware_camera/main/eye_tracking.h firmware_camera/main/camera_capture_adapter.cpp firmware_camera/main/CMakeLists.txt firmware_camera/test_apps/eye_tongue firmware_esp32/main/fusion.c firmware_esp32/test_apps/e1_core/main/test_e1_core.c host_pc/tests/test_camera_coprocessor_firmware.py
git commit -m "feat(eye): add continuous tracking with guided priority"
git push origin codex/preliminary-demo
```

### Task 4: Web State, Full Verification, And Hardware Acceptance

**Files:**
- Modify: `cloud/backend/app/static/demo/app.js`
- Modify: `host_pc/tests/test_demo_web.py`
- Modify: `docs/camera-nmo432-bringup.md`

**Interfaces:**
- Consumes: existing nullable F/S/T/E scores and existing guided camera stage.
- Produces: continuous-monitor copy without new API/MQTT fields, deployed VPS assets, and measured COM3/COM4 acceptance evidence.

- [ ] **Step 1: Write failing web tests**

Require stage 0 to render `持续监测中`. Remove the stage-6 missing-S fixed-phrase
branch because S is independent of guided screening. Stage 6 always means
`筛查完成`; null modality values still display `待采集`.

- [ ] **Step 2: Implement and verify web copy**

Update only the existing instruction area. Do not add cards or explanatory
panels. Run demo web/API/cloud-contract tests and verify WebSocket plus five
second polling fallback remain unchanged.

- [ ] **Step 3: Run all automated verification**

```powershell
host_pc\.venv\Scripts\python.exe -m pytest host_pc\tests -q --basetemp=F:\iot_design\.pytest-continuous-full
git diff --check
```

Build all four IDF targets: N16R8 production, e1_core Unity, camera production,
and eye_tongue Unity. Expected: every build succeeds without partition overflow.

- [ ] **Step 4: Flash and verify COM4 then COM3**

Flash camera production to COM4 and N16R8 production to COM3. Do not erase
flash. Monitor both ports and verify:

1. F updates with a face, remains for five seconds after leaving, then clears.
2. S starts from boot, speech creates a numeric window, and the next silent
   window clears S without score zero.
3. E updates while bbox/landmarks are valid without pressing Start.
4. Guided center/left/right E overrides rolling E, then rolling E resumes after
   30 seconds.
5. T appears only after the tongue prompt.
6. MQTT contains numeric scores only and the page updates through WebSocket.

- [ ] **Step 5: Deploy VPS and update documentation**

Use `scripts/deploy_cloud_native_interactive.ps1` so runtime state and `.env`
are preserved. Record measured timing/ranges as engineering observations only;
do not state accuracy, sensitivity, or specificity.

- [ ] **Step 6: Final commit and push**

```powershell
git add cloud/backend/app/static/demo/app.js host_pc/tests/test_demo_web.py docs/camera-nmo432-bringup.md
git commit -m "docs(edge): record continuous FSE acceptance"
git push origin codex/preliminary-demo
git status --short
```
