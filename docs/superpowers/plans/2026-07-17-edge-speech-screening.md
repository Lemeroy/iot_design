# Edge Speech Screening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a quality-gated preliminary FAST S score on the standalone N16R8 from real NMO432 audio, without uploading audio or allowing the unevaluated heuristic to trigger a speech danger veto.

**Architecture:** `audio_nmo432` remains the only I2S owner and passes fixed 20 ms blocks into a bounded `speech_screening` state machine. A camera `SG_STAGE_DONE` edge starts a four-second guided utterance window; a valid result enters the existing score bus with explicit veto provenance, while failed quality leaves S unavailable. The existing MQTT schema remains numeric-only, and the web page infers the speech prompt from `screening_stage == DONE` plus a missing S value.

**Tech Stack:** ESP-IDF 5.5.3, ESP32-S3 N16R8, FreeRTOS, C11, ESP-IDF Unity, pytest structural/privacy tests, FastAPI static demo, vanilla JavaScript, COM3 hardware-in-loop testing.

## Global Constraints

- NMO432 is 16 kHz mono, left slot, with SCK GPIO17, WS GPIO18, SD GPIO16, L/R tied to GND, and 3.3 V supply.
- The guided phrase is `今天的天气很好`; there is no speech-to-text or phrase-content verification.
- PCM, encoded audio, MFCC arrays, FFT bins, voice embeddings, and utterance fingerprints never cross the device boundary.
- Only `scores.speech`, the existing final score, and the existing level are uploaded; `p_clear` remains local.
- A failed or low-quality capture leaves S unavailable and never becomes score zero or a fabricated normal result.
- The preliminary heuristic may contribute to weighted fusion after quality passes but must never trigger the speech single-item danger veto.
- The UI calls this `初赛声学筛查`; it must not claim CNN inference, diagnosis, dysarthria detection, sensitivity, or specificity.
- Exact score ranges and latency are measured on the installed hardware and are not claimed before measurement.

---

## File Structure

- Create `firmware_esp32/main/speech_screening.h`: public state, reason, result, and lifecycle API with no FreeRTOS dependency.
- Create `firmware_esp32/main/speech_screening.c`: bounded frame features, adaptive noise floor, quality gates, deterministic heuristic score, and session state.
- Modify `firmware_esp32/main/audio_nmo432.c`: feed each valid 20 ms block to the speech engine and log bounded session results.
- Modify `firmware_esp32/main/app_main.c`: synchronize speech lifecycle with screening controls and the camera DONE edge.
- Modify `firmware_esp32/main/score_bus.h` and `.c`: preserve speech veto eligibility with each fresh speech result.
- Modify `firmware_esp32/main/fusion.h` and `.c`: require explicit evaluated-model provenance before speech veto.
- Modify `firmware_esp32/main/CMakeLists.txt`: compile the speech component.
- Modify `firmware_esp32/test_apps/e1_core/main/CMakeLists.txt`: compile speech and score/fusion code into the Unity app.
- Modify `firmware_esp32/test_apps/e1_core/main/test_e1_core.c`: deterministic speech, session, and veto-provenance tests.
- Modify `host_pc/tests/test_e1_standalone_firmware.py`: structural and privacy assertions.
- Modify `host_pc/tests/test_demo_web.py`: guided S copy and state behavior assertions.
- Modify `cloud/backend/app/static/demo/app.js`: show the phrase after camera completion while S remains unavailable.
- Modify `docs/camera-nmo432-bringup.md`: commands, expected logs, measured acceptance results, and medical limitation.

### Task 1: Pure Speech Feature Engine

**Files:**
- Create: `firmware_esp32/main/speech_screening.h`
- Create: `firmware_esp32/main/speech_screening.c`
- Modify: `firmware_esp32/test_apps/e1_core/main/CMakeLists.txt`
- Modify: `firmware_esp32/test_apps/e1_core/main/test_e1_core.c`
- Modify: `host_pc/tests/test_e1_standalone_firmware.py`

**Interfaces:**
- Consumes: signed mono `int16_t samples[320]` at 16 kHz, one frame every 20 ms.
- Produces: caller-owned `sg_speech_context_t` plus `sg_speech_screening_init(ctx)`, `sg_speech_screening_start(ctx)`, `sg_speech_screening_cancel(ctx)`, `sg_speech_screening_process(ctx, const int16_t *, size_t)`, and `sg_speech_screening_snapshot(const ctx, result)`.
- Result fields: `state`, `available`, `score`, `p_clear`, `reason`, `valid_frames`, `voiced_frames`, `rms`, and `peak`.

- [ ] **Step 1: Write failing Unity and structural tests**

Add Unity fixtures that generate frames without dynamic allocation:

```c
static void fill_silence(int16_t *samples) {
    memset(samples, 0, 320 * sizeof(*samples));
}

static void fill_speech_like(int16_t *samples, unsigned frame) {
    for (size_t i = 0; i < 320; ++i) {
        float t = (float)(frame * 320 + i) / 16000.0f;
        float envelope = 0.55f + 0.35f * sinf(2.0f * (float)M_PI * 4.0f * t);
        samples[i] = (int16_t)(envelope * (
            900.0f * sinf(2.0f * (float)M_PI * 220.0f * t)
            + 420.0f * sinf(2.0f * (float)M_PI * 1050.0f * t)));
    }
}
```

Test these behaviors:

```c
TEST_CASE("silence produces no preliminary speech score", "[speech]")
TEST_CASE("short utterance produces too_short", "[speech]")
TEST_CASE("clipped utterance produces clipped", "[speech]")
TEST_CASE("speech-like utterance produces bounded score", "[speech]")
TEST_CASE("cancel clears partial speech result", "[speech]")
TEST_CASE("completed result is stable until next start", "[speech]")
```

Extend the Python structural test to require both new files, the four public
functions, fixed 320-sample blocks, and absence of `malloc`, `calloc`, and
`realloc` in `speech_screening.c`.

- [ ] **Step 2: Run tests to verify RED**

```powershell
host_pc\.venv\Scripts\python.exe -m pytest host_pc\tests\test_e1_standalone_firmware.py -q --basetemp=F:\iot_design\.pytest-speech-red
powershell -ExecutionPolicy Bypass -Command ". E:\esp\v5.5.3\esp-idf\export.ps1; idf.py -C firmware_esp32/test_apps/e1_core build"
```

Expected: pytest and the Unity build fail because `speech_screening.h/.c` and
their symbols do not exist.

- [ ] **Step 3: Implement the minimal engine**

Define the public contract:

```c
typedef enum {
    SG_SPEECH_IDLE = 0,
    SG_SPEECH_LISTENING,
    SG_SPEECH_COMPLETE,
    SG_SPEECH_RETRY,
} sg_speech_state_t;

typedef enum {
    SG_SPEECH_REASON_NONE = 0,
    SG_SPEECH_REASON_NO_VOICE,
    SG_SPEECH_REASON_TOO_SHORT,
    SG_SPEECH_REASON_TOO_QUIET,
    SG_SPEECH_REASON_CLIPPED,
    SG_SPEECH_REASON_IO_ERROR,
} sg_speech_reason_t;

typedef struct {
    sg_speech_state_t state;
    bool available;
    uint8_t score;
    float p_clear;
    sg_speech_reason_t reason;
    uint16_t valid_frames;
    uint16_t voiced_frames;
    float rms;
    int16_t peak;
} sg_speech_result_t;
```

Use named engineering defaults: 200 frames maximum, 15 startup-noise frames,
at least 35 voiced frames, at least 55 total valid frames, clipping below five
percent, and VAD hysteresis based on `max(noise_rms * 1.6, noise_rms + 3)`.
Remove per-frame DC, calculate RMS/peak/zero crossings, and use three bounded
Goertzel accumulators centered near 300, 1000, and 3000 Hz as the equivalent
low/mid/high filter bank. Clamp all normalized features and calculate:

```c
p_clear = 0.35f * continuity
        + 0.25f * voiced_ratio_quality
        + 0.20f * energy_dynamics
        + 0.10f * zcr_quality
        + 0.10f * band_balance;
score = (uint8_t)lroundf(100.0f * clamp01(p_clear));
```

Quality gates run before scoring and return one deterministic reason. Keep all
state in the caller-owned bounded context. The component has no static mutable
state, FreeRTOS dependency, or allocation.

- [ ] **Step 4: Verify GREEN**

Run the focused pytest and Unity build again. Expected: pytest passes and the
Unity app compiles with all speech cases registered.

- [ ] **Step 5: Commit**

```powershell
git add firmware_esp32/main/speech_screening.* firmware_esp32/test_apps/e1_core host_pc/tests/test_e1_standalone_firmware.py
git commit -m "feat(speech): add bounded edge feature engine"
git push origin codex/preliminary-demo
```

### Task 2: Real NMO432 Session Integration

**Files:**
- Modify: `firmware_esp32/main/audio_nmo432.c`
- Modify: `firmware_esp32/main/audio_nmo432.h`
- Modify: `firmware_esp32/main/app_main.c`
- Modify: `firmware_esp32/main/CMakeLists.txt`
- Modify: `host_pc/tests/test_e1_standalone_firmware.py`

**Interfaces:**
- Consumes: `sg_audio_block_t` from the existing I2S task and camera stages from `sg_camera_coprocessor_stage()`.
- Produces: thread-safe `sg_audio_nmo432_speech_start()`, `sg_audio_nmo432_speech_cancel()`, and `sg_audio_nmo432_speech_snapshot()` wrappers around one audio-task-owned context; one session for each new `SG_STAGE_DONE` edge.

- [ ] **Step 1: Write failing integration-structure tests**

Require the source to:

```python
assert "sg_speech_screening_process(block.samples" in audio
assert "sg_audio_nmo432_speech_start" in app
assert "sg_audio_nmo432_speech_cancel" in app
assert "SG_STAGE_DONE" in app
assert '"speech_screening.c"' in cmake
assert "pcm" not in cloud.lower()
assert "audio_b64" not in cloud.lower()
```

Also require that a repeated fusion-loop observation of `SG_STAGE_DONE` does
not restart a completed session; source must retain the previous camera stage
and start only on a transition into DONE.

- [ ] **Step 2: Run the focused test to verify RED**

```powershell
host_pc\.venv\Scripts\python.exe -m pytest host_pc\tests\test_e1_standalone_firmware.py -q --basetemp=F:\iot_design\.pytest-speech-integration-red
```

Expected: failure on missing lifecycle calls and CMake registration.

- [ ] **Step 3: Connect the audio task and stage edge**

In `audio_diagnostic_task`, own the `sg_speech_context_t`, pass every successful
valid block to `sg_speech_screening_process`, and service start/cancel commands
received through a length-one FreeRTOS queue. The public start/cancel wrappers
enqueue commands; the snapshot wrapper copies the last result under a short
critical section. Report only aggregate result values and reason codes when a
state changes; never log samples or feature arrays.

In `task_fusion`, retain `previous_screening_stage`. On a transition into
`SG_STAGE_DONE`, call `sg_audio_nmo432_speech_start()`. During LISTENING and
after COMPLETE, snapshot and log state without writing the score bus yet; Task
3 adds the provenance-safe score write. On RETRY, leave S unavailable and log
the stable reason. In `task_downlink`, call
`sg_audio_nmo432_speech_cancel()` before forwarding a cancel control to the
camera. Starting a new screening clears the previous speech result so stale S
cannot appear during the next session.

- [ ] **Step 4: Build production firmware**

```powershell
powershell -ExecutionPolicy Bypass -Command ". E:\esp\v5.5.3\esp-idf\export.ps1; idf.py -C firmware_esp32 build"
```

Expected: successful N16R8 build with no undefined speech symbols and no new
partition overflow.

- [ ] **Step 5: Commit**

```powershell
git add firmware_esp32/main/audio_nmo432.* firmware_esp32/main/app_main.c firmware_esp32/main/CMakeLists.txt host_pc/tests/test_e1_standalone_firmware.py
git commit -m "feat(audio): run speech screening from NMO432"
git push origin codex/preliminary-demo
```

### Task 3: Veto Provenance And Numeric-Only Contract

**Files:**
- Modify: `firmware_esp32/main/score_bus.h`
- Modify: `firmware_esp32/main/score_bus.c`
- Modify: `firmware_esp32/main/fusion.h`
- Modify: `firmware_esp32/main/fusion.c`
- Modify: `firmware_esp32/test_apps/e1_core/main/test_e1_core.c`
- Modify: `host_pc/tests/test_e1_standalone_firmware.py`

**Interfaces:**
- Consumes: `sg_score_bus_set_speech(int score, float p_clear, bool veto_eligible, int64_t now_us)`.
- Produces: `sg_scores_in_t.speech_veto_eligible`, preserved only while the speech entry is fresh.

- [ ] **Step 1: Write failing provenance tests**

Add Unity cases:

```c
TEST_CASE("heuristic low speech contributes without danger veto", "[speech][fusion]")
TEST_CASE("evaluated low speech remains veto eligible", "[speech][fusion]")
TEST_CASE("stale speech clears veto provenance", "[speech][score_bus]")
```

For identical `speech=20` and `p_clear=0.2`, assert the first case has
`veto_speech == 0` when eligibility is false and the second has
`veto_speech == 1` when eligibility is true.

- [ ] **Step 2: Run Unity build to verify RED**

Build `firmware_esp32/test_apps/e1_core`. Expected: failure because the setter
and `sg_scores_in_t` do not yet carry provenance.

- [ ] **Step 3: Implement provenance at the source boundary**

Add a boolean to the private speech score entry and copy it to
`sg_scores_in_t.speech_veto_eligible` only for a fresh entry. Initialize it to
false in snapshots and resets. Change the veto condition to:

```c
if (a_speech && in->speech_veto_eligible
    && speech <= SG_SPEECH_DANGER_MAX
    && !isnan(in->speech_p_clear)
    && in->speech_p_clear < SPEECH_P_DANGER_MAX) {
    out->veto_speech = 1;
}
```

Do not serialize the provenance flag or `p_clear` in `cloud_contract.c`. After
the new setter is available, update `task_fusion` so the first COMPLETE
snapshot in each session writes exactly once:

```c
sg_score_bus_set_speech(result.score, result.p_clear, false,
                        esp_timer_get_time());
```

The `false` argument is mandatory for the preliminary heuristic.

- [ ] **Step 4: Verify Unity, privacy, and production builds**

Run the e1_core build, focused pytest, and production firmware build. Expected:
all pass; cloud source still contains none of `pcm`, `mfcc`, `fft_bins`,
`audio_b64`, `p_clear`, or `speech_veto_eligible`.

- [ ] **Step 5: Commit**

```powershell
git add firmware_esp32/main/score_bus.* firmware_esp32/main/fusion.* firmware_esp32/test_apps/e1_core host_pc/tests/test_e1_standalone_firmware.py
git commit -m "fix(fusion): gate speech veto by model provenance"
git push origin codex/preliminary-demo
```

### Task 4: Guided Web Presentation

**Files:**
- Modify: `cloud/backend/app/static/demo/app.js`
- Modify: `host_pc/tests/test_demo_web.py`

**Interfaces:**
- Consumes: existing `screening_stage` and nullable `scores.speech` fields.
- Produces: a phrase-reading instruction without adding an API or MQTT field.

- [ ] **Step 1: Write failing browser-contract tests**

Require the static script to contain the exact copy `请朗读：今天的天气很好`
and `初赛声学筛查`. Add a source behavior assertion that stage 6 with a null
speech score selects the reading instruction, while stage 6 with a numeric
speech score selects `筛查完成`.

- [ ] **Step 2: Run the focused web test to verify RED**

```powershell
host_pc\.venv\Scripts\python.exe -m pytest host_pc\tests\test_demo_web.py -q --basetemp=F:\iot_design\.pytest-speech-web-red
```

Expected: failure because stage 6 currently always displays completion.

- [ ] **Step 3: Implement derived speech-prompt rendering**

Change `renderScreening` to accept `scores.speech`. For stage 6 and a
non-numeric speech value, render `请朗读：今天的天气很好`, progress 90, and keep
start disabled. Once a numeric S arrives, render `筛查完成`, progress 100. Keep
offline and stage-error behavior unchanged. Add a compact `初赛声学筛查` label
next to the S value only if the existing markup already has a metric subtitle;
do not add a new card or explanatory panel.

- [ ] **Step 4: Verify web and cloud tests**

```powershell
host_pc\.venv\Scripts\python.exe -m pytest host_pc\tests\test_demo_web.py host_pc\tests\test_demo_api.py host_pc\tests\test_cloud_native_contract.py -q --basetemp=F:\iot_design\.pytest-speech-web
```

Expected: all pass and no API schema changes.

- [ ] **Step 5: Commit**

```powershell
git add cloud/backend/app/static/demo/app.js host_pc/tests/test_demo_web.py
git commit -m "feat(web): guide preliminary speech reading"
git push origin codex/preliminary-demo
```

### Task 5: Full Verification, Flash, Calibration, And Handoff

**Files:**
- Modify: `docs/camera-nmo432-bringup.md`
- Modify only if measurements require it: named engineering constants in `firmware_esp32/main/speech_screening.c`

**Interfaces:**
- Consumes: completed firmware, COM3, installed NMO432, and authenticated VPS demo.
- Produces: reproducible build evidence, measured local acceptance notes, flashed production firmware, and deployed static web assets.

- [ ] **Step 1: Run full automated verification**

```powershell
host_pc\.venv\Scripts\python.exe -m pytest host_pc\tests -q --basetemp=F:\iot_design\.pytest-speech-full
git diff --check
powershell -ExecutionPolicy Bypass -Command ". E:\esp\v5.5.3\esp-idf\export.ps1; idf.py -C firmware_esp32/test_apps/e1_core build; idf.py -C firmware_esp32 build"
```

Expected: all pytest tests pass, both IDF builds succeed, and `git diff --check`
prints nothing.

- [ ] **Step 2: Flash production firmware and monitor COM3**

Close all COM3 users, then run:

```powershell
powershell -ExecutionPolicy Bypass -Command ". E:\esp\v5.5.3\esp-idf\export.ps1; idf.py -C firmware_esp32 -p COM3 flash monitor"
```

Expected: NMO432 initializes, I2S blocks remain valid, and the device stays
connected to Wi-Fi/MQTT. Exit monitor with `Ctrl+]`.

- [ ] **Step 3: Execute three hardware trials**

For each trial, start a guided screening from the VPS page and record only
aggregate log values and final availability:

1. Remain silent for the full speech window: expect RETRY with `no_voice` or
   `too_quiet`, and S remains unavailable.
2. Read `今天的天气很好` at normal volume 15-30 cm from the microphone: expect
   COMPLETE with bounded S and no speech veto.
3. Read the phrase from at least one meter: expect either a lower-quality valid
   result or RETRY; it must not fabricate a healthy result.

Repeat the near-field trial three times. Record the measured ranges without
calling them accuracy, sensitivity, or specificity. If quality gating fails
despite visible RMS separation, adjust only one named VAD/quality constant,
rerun all three trials, and document the before/after evidence.

- [ ] **Step 4: Deploy and verify the static page**

Deploy the changed cloud tree using the repository's existing VPS deployment
script. Verify `http://106.75.229.61:8000/demo/` shows the phrase prompt after
F/E/T completion, changes S only after valid speech capture, and continues to
show the latest Doubao advice. Confirm InfluxDB and MQTT payload inspection
contains no raw or derived audio arrays.

- [ ] **Step 5: Update handoff documentation**

Append the firmware version/commit, COM3 commands, observed quiet/near/far
ranges, quality reasons, and the statement that S is an unevaluated preliminary
acoustic heuristic. Preserve the emergency-care disclaimer and state that a
versioned evaluated INT8 model is required before enabling speech veto.

- [ ] **Step 6: Final commit and push**

```powershell
git add docs/camera-nmo432-bringup.md firmware_esp32/main/speech_screening.c
git commit -m "docs(speech): record NMO432 screening acceptance"
git push origin codex/preliminary-demo
git status --short
```

Expected: the commit and push succeed. `git status --short` may show only known
untracked local test-output directories; they must not be committed.
