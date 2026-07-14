# Camera Coprocessor and NMO432 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the Hiwonder ESP32-S3-Cam as an I2C scoring coprocessor and capture real 16 kHz mono audio from NMO432 on the N16R8 main controller without uploading raw media or fabricating F/S/T/E scores.

**Architecture:** The N16R8 is the I2C controller, audio/CSI/fusion owner, and sole MQTT device. The camera board is an I2C target at address `0x42`; it performs local image acquisition and eventually local F/T/E inference, returning only a fixed-size CRC-protected status frame. Camera acquisition remains unavailable until the vendor camera source or verified internal camera pin map is supplied.

**Tech Stack:** ESP-IDF v5.5.3, FreeRTOS, ESP-IDF `driver/i2c_master.h`, ESP-IDF I2S standard-mode driver, C11, pytest static contract tests, ESP-IDF Unity component tests.

## Global Constraints

- Main controller is ESP32-S3-WROOM-1 N16R8; camera is a separate Hiwonder ESP32-S3-Cam coprocessor.
- Production communication carries structured scores/status only; continuous JPEG and raw PCM never enter MQTT or VPS storage.
- Camera I2C uses N16R8 GPIO8/GPIO9; NMO432 uses GPIO17/GPIO18/GPIO16 and 3.3 V.
- ST7789, MAX98357A, RGB LED, buzzer, and buttons remain disabled and outside this implementation.
- Missing sensors, models, bad CRC, poor quality, and stale data produce invalid modalities and `insufficient`, never score zero or fabricated normal values.
- Do not invent the camera module's internal DVP pin mapping or claim medical accuracy.
- Every task ends with focused tests, one commit, and push to `codex/preliminary-demo`.
- Never commit Wi-Fi, MQTT, VPS, management-token, web-login, or LLM credentials.

## File Map

- `firmware_common/camera_scores_protocol.h`: wire-format constants, packed frame, status and validity definitions shared by both ESP-IDF projects.
- `firmware_common/camera_scores_protocol.c`: CRC validation and frame decoding with no ESP-IDF dependency.
- `firmware_esp32/main/camera_coprocessor.*`: N16R8 I2C controller, polling, staleness tracking, and score-bus publication.
- `firmware_esp32/main/audio_nmo432.*`: NMO432 I2S initialization, bounded PCM reads, and signal-quality metrics.
- `firmware_camera/`: separate ESP-IDF target firmware for the Hiwonder camera board.
- `firmware_camera/main/camera_score_target.*`: I2C target snapshot service.
- `firmware_camera/main/camera_capture_adapter.*`: vendor camera integration boundary; reports `model_missing`/`error` until verified source and pins are available.
- `host_pc/config/device-deployment.example.yaml`: corrected coprocessor/NMO432 deployment declaration.
- `host_pc/stroke_host/deployment/schema.py`: deployment validation and Kconfig mapping for the corrected hardware.

---

### Task 1: Correct Hardware Identity and Deployment Configuration

**Files:**
- Modify: `firmware_esp32/main/Kconfig.projbuild`
- Modify: `firmware_esp32/main/board_pins.h`
- Modify: `host_pc/config/device-deployment.example.yaml`
- Modify: `host_pc/stroke_host/deployment/schema.py`
- Modify: `host_pc/tests/test_deployment_schema.py`
- Modify: `host_pc/tests/test_firmware_m1_frame_static.py`

**Interfaces:**
- Produces Kconfig symbols `CONFIG_STROKEGUARD_CAMERA_COPROCESSOR_ENABLE`, `CONFIG_STROKEGUARD_CAMERA_I2C_SDA=8`, `CONFIG_STROKEGUARD_CAMERA_I2C_SCL=9`, `CONFIG_STROKEGUARD_CAMERA_I2C_ADDRESS=0x42`, `CONFIG_STROKEGUARD_NMO432_ENABLE`, `CONFIG_STROKEGUARD_NMO432_BCLK=17`, `CONFIG_STROKEGUARD_NMO432_WS=18`, `CONFIG_STROKEGUARD_NMO432_DIN=16`, and channel selection.
- Removes production references that identify the installed hardware as GC2145 or INMP441; legacy files are removed only after replacement modules compile.

- [x] **Step 1: Write failing schema and static contract tests**

```python
def test_example_declares_camera_coprocessor_and_nmo432():
    text = EXAMPLE.read_text(encoding="utf-8")
    assert "ESP32-S3-Cam" in text
    assert "NMO432" in text
    assert "GC2145" not in text
    assert "INMP441" not in text

def test_camera_and_audio_defaults_match_approved_gpio_allocation():
    kconfig = read_firmware("Kconfig.projbuild")
    for token in ("CAMERA_I2C_SDA", "default 8", "CAMERA_I2C_SCL",
                  "default 9", "NMO432_BCLK", "default 17",
                  "NMO432_WS", "default 18", "NMO432_DIN", "default 16"):
        assert token in kconfig
```

- [x] **Step 2: Run tests and verify the old names fail**

Run: `python -m pytest host_pc/tests/test_deployment_schema.py host_pc/tests/test_firmware_m1_frame_static.py -q`

Expected: FAIL because the example and Kconfig still declare GC2145/INMP441.

- [x] **Step 3: Replace the schema and Kconfig hardware contract**

Use an enabled camera declaration with no raw DVP pins:

```yaml
hardware:
  camera:
    model: ESP32-S3-Cam
    enabled: true
    transport: i2c
    address: 66
    pins: {sda: 8, scl: 9}
  microphone:
    model: NMO432
    enabled: true
    sample_rate: 16000
    channel: left
    pins: {sck: 17, ws: 18, sd: 16}
```

Reject duplicate pins, camera addresses outside `0x08..0x77`, sample rates other than 16000, and unknown models. Map resolved YAML to the new Kconfig symbols without logging secrets.

- [x] **Step 4: Run focused tests and verify pass**

Run: `python -m pytest host_pc/tests/test_deployment_schema.py host_pc/tests/test_firmware_m1_frame_static.py -q`

Expected: PASS.

- [x] **Step 5: Commit and push**

```powershell
git add firmware_esp32/main/Kconfig.projbuild firmware_esp32/main/board_pins.h host_pc/config/device-deployment.example.yaml host_pc/stroke_host/deployment/schema.py host_pc/tests docs/superpowers/plans/2026-07-14-camera-coprocessor-nmo432.md
git commit -m "refactor(device): model camera coprocessor and NMO432"
git push origin codex/preliminary-demo
```

### Task 2: Add the Shared Camera Score Protocol

**Files:**
- Create: `firmware_common/camera_scores_protocol.h`
- Create: `firmware_common/camera_scores_protocol.c`
- Create: `firmware_esp32/test_apps/camera_protocol/CMakeLists.txt`
- Create: `firmware_esp32/test_apps/camera_protocol/main/CMakeLists.txt`
- Create: `firmware_esp32/test_apps/camera_protocol/main/test_camera_protocol.c`

**Interfaces:**
- Produces `sg_camera_scores_v1_t`, `sg_camera_scores_crc(const sg_camera_scores_v1_t *)`, and `sg_camera_scores_validate(const sg_camera_scores_v1_t *)`.
- Validation returns the project enum `SG_CAMERA_PROTOCOL_OK`, `SG_CAMERA_PROTOCOL_BAD_VERSION`, `SG_CAMERA_PROTOCOL_BAD_CRC`, or `SG_CAMERA_PROTOCOL_BAD_VALUE`; score fields are usable only when their `valid_mask` bit is set.

- [x] **Step 1: Write Unity tests for packed size, CRC, version, range, and mask handling**

```c
TEST_CASE("camera score v1 validates known frame", "[camera_protocol]")
{
    sg_camera_scores_v1_t frame = {
        .version = SG_CAMERA_PROTOCOL_V1,
        .sequence = 7,
        .face = 81, .tongue = 72, .eye = 90, .quality = 88,
        .valid_mask = SG_CAMERA_VALID_FACE | SG_CAMERA_VALID_EYE,
        .status = SG_CAMERA_STATUS_READY,
        .mouth_angle_x10 = 35,
        .latency_ms = 42,
    };
    frame.crc16 = sg_camera_scores_crc(&frame);
    TEST_ASSERT_EQUAL(SG_CAMERA_PROTOCOL_OK,
                      sg_camera_scores_validate(&frame));
    TEST_ASSERT_EQUAL(14, sizeof(frame));
}
```

Also corrupt one byte, set version 2, set `face=101` while face-valid, and verify each is rejected.

- [x] **Step 2: Build the test app and verify it fails before implementation**

Run from an ESP-IDF v5.5.3 shell:

```powershell
cd F:\iot_design\firmware_esp32\test_apps\camera_protocol
idf.py set-target esp32s3
idf.py build
```

Expected: FAIL because the shared protocol files do not exist.

- [x] **Step 3: Implement the packed frame and CRC-16 validation**

Use CRC-16/CCITT-FALSE parameters: polynomial `0x1021`, initial value `0xFFFF`, no reflection, xor-out `0x0000`; cover bytes from `version` through `latency_ms` and store CRC little-endian in the struct.

- [x] **Step 4: Build, flash, and run Unity tests on COM3**

Run: `idf.py -p COM3 flash monitor`

Expected: all `[camera_protocol]` cases pass with zero failures.

- [x] **Step 5: Commit and push**

```powershell
git add firmware_common firmware_esp32/test_apps/camera_protocol
git commit -m "feat(protocol): add camera score wire contract"
git push origin codex/preliminary-demo
```

### Task 3: Implement the N16R8 Camera I2C Controller

**Files:**
- Create: `firmware_esp32/main/camera_coprocessor.h`
- Create: `firmware_esp32/main/camera_coprocessor.c`
- Modify: `firmware_esp32/main/CMakeLists.txt`
- Modify: `firmware_esp32/main/app_main.c`
- Modify: `firmware_esp32/main/score_bus.h`
- Modify: `firmware_esp32/main/score_bus.c`
- Modify: `host_pc/tests/test_e1_standalone_firmware.py`
- Delete after replacement builds: `firmware_esp32/main/camera_gc2145.h`
- Delete after replacement builds: `firmware_esp32/main/camera_gc2145.c`

**Interfaces:**
- Produces `esp_err_t sg_camera_coprocessor_init(void)`, `esp_err_t sg_camera_coprocessor_poll(sg_camera_observation_t *out)`, and a 500 ms FreeRTOS polling task.
- `sg_camera_observation_t` contains nullable validity, sequence, F/T/E, quality, status, mouth angle, latency, and monotonic receive timestamp.
- Publishes only valid F/T/E values to `sg_score_bus`; invalid or stale values clear those modalities.

- [x] **Step 1: Add failing static tests for I2C controller ownership and score validity**

```python
def test_camera_coprocessor_is_polled_locally():
    app = read("app_main.c")
    source = read("camera_coprocessor.c")
    assert "sg_camera_coprocessor_init" in app
    assert "i2c_new_master_bus" in source
    assert "i2c_master_receive" in source
    assert "sg_camera_scores_validate" in source
    assert "sg_score_bus_update" in source
```

- [x] **Step 2: Run the static test and verify failure**

Run: `python -m pytest host_pc/tests/test_e1_standalone_firmware.py -q`

Expected: FAIL because `camera_coprocessor.c` does not exist.

- [x] **Step 3: Implement bounded polling and recovery**

Initialize one 100 kHz I2C master bus on GPIO8/GPIO9, add address `0x42`, receive exactly `sizeof(sg_camera_scores_v1_t)` with a 100 ms timeout, validate version/CRC/ranges, and reject unchanged sequence values older than 2 seconds. Log state transitions only (`online`, `offline`, `protocol_error`) rather than every poll.

- [x] **Step 4: Wire the task into app startup without blocking Wi-Fi/MQTT**

Start camera polling only when enabled. An initialization or read failure must clear F/T/E and retry with bounded backoff; it must not call `ESP_ERROR_CHECK` from the polling loop or reboot the device.

- [x] **Step 5: Run static tests and build N16R8 firmware**

Run:

```powershell
python -m pytest host_pc/tests/test_e1_standalone_firmware.py -q
cd F:\iot_design\firmware_esp32
idf.py build
```

Expected: pytest PASS and ESP-IDF build completes with no error.

- [x] **Step 6: Commit and push**

```powershell
git add firmware_esp32/main host_pc/tests/test_e1_standalone_firmware.py
git commit -m "feat(device): poll camera score coprocessor"
git push origin codex/preliminary-demo
```

### Task 4: Implement Real NMO432 I2S Capture

**Files:**
- Create: `firmware_esp32/main/audio_nmo432.h`
- Create: `firmware_esp32/main/audio_nmo432.c`
- Modify: `firmware_esp32/main/CMakeLists.txt`
- Modify: `firmware_esp32/main/app_main.c`
- Modify: `host_pc/tests/test_e1_standalone_firmware.py`
- Delete after replacement builds: `firmware_esp32/main/audio_inmp441.h`
- Delete after replacement builds: `firmware_esp32/main/audio_inmp441.c`

**Interfaces:**
- Produces `esp_err_t sg_audio_nmo432_init(void)` and `esp_err_t sg_audio_nmo432_read(sg_audio_block_t *out, TickType_t timeout)`.
- `sg_audio_block_t` owns 320 signed 16-bit mono samples (20 ms at 16 kHz), RMS, peak, clipped-sample count, and validity. No raw block is exposed to MQTT code.

- [x] **Step 1: Add failing static checks for the ESP-IDF standard I2S driver**

```python
def test_nmo432_uses_real_16khz_i2s_capture():
    source = read("audio_nmo432.c")
    assert "i2s_new_channel" in source
    assert "I2S_STD_CLK_DEFAULT_CONFIG(16000)" in source
    assert "I2S_DATA_BIT_WIDTH_32BIT" in source
    assert "i2s_channel_read" in source
    assert "GPIO_NUM_17" in source or "SG_PIN_NMO432_BCLK" in source
```

- [x] **Step 2: Run the test and verify failure**

Run: `python -m pytest host_pc/tests/test_e1_standalone_firmware.py -q`

Expected: FAIL because the NMO432 implementation does not exist.

- [x] **Step 3: Implement mono capture and safe sample conversion**

Configure standard Philips I2S receive-only mode at 16 kHz, 32-bit slots, selected left/right slot, BCLK GPIO17, WS GPIO18, DIN GPIO16. Right-shift the microphone's signed sample into int16 with saturation. Mark blocks invalid when reads time out, all samples are constant, or clipping exceeds 5 percent; do not turn quality metrics into an S medical score.

- [x] **Step 4: Start a bounded audio task and expose diagnostics locally**

Maintain latest RMS/peak/validity in RAM and log one aggregate line every 5 seconds. Do not serialize PCM, MFCC, or audio-derived features into cloud uplinks. Keep `speech=-1` until a versioned evaluated model is integrated.

- [ ] **Step 5: Build, flash COM3, and inspect real microphone diagnostics**

Run:

```powershell
cd F:\iot_design\firmware_esp32
idf.py build
idf.py -p COM3 flash monitor
```

Expected: boot succeeds; speaking changes RMS/peak; silence does not produce a speech score; Wi-Fi, CSI, MQTT, and camera polling continue.

- [x] **Step 6: Commit and push**

```powershell
git add firmware_esp32/main host_pc/tests/test_e1_standalone_firmware.py
git commit -m "feat(audio): capture NMO432 over I2S"
git push origin codex/preliminary-demo
```

### Task 5: Create the Camera Coprocessor Firmware

**Files:**
- Create: `firmware_camera/CMakeLists.txt`
- Create: `firmware_camera/sdkconfig.defaults`
- Create: `firmware_camera/main/CMakeLists.txt`
- Create: `firmware_camera/main/app_main.c`
- Create: `firmware_camera/main/camera_score_target.h`
- Create: `firmware_camera/main/camera_score_target.c`
- Create: `firmware_camera/main/camera_capture_adapter.h`
- Create: `firmware_camera/main/camera_capture_adapter.c`
- Create: `firmware_camera/README.md`
- Create: `host_pc/tests/test_camera_coprocessor_firmware.py`

**Interfaces:**
- Consumes `sg_camera_scores_v1_t` from `firmware_common`.
- Produces an I2C target at `0x42` that always returns a coherent CRC-protected snapshot.
- `sg_camera_capture_observe(sg_camera_observation_source_t *out)` reports image quality and status; it sets no F/T/E validity bits until real model outputs exist.

- [x] **Step 1: Add failing project-structure and privacy tests**

```python
def test_camera_firmware_exposes_i2c_scores_not_network_media():
    source = (CAMERA_MAIN / "camera_score_target.c").read_text("utf-8")
    app = (CAMERA_MAIN / "app_main.c").read_text("utf-8")
    assert "i2c_new_slave_device" in source
    assert "sg_camera_scores_crc" in source
    assert "esp_mqtt" not in app
    assert "jpeg_b64" not in app
```

- [x] **Step 2: Run test and verify failure**

Run: `python -m pytest host_pc/tests/test_camera_coprocessor_firmware.py -q`

Expected: FAIL because `firmware_camera` does not exist.

- [x] **Step 3: Implement the I2C target with an atomic snapshot**

Create one mutex-protected 14-byte frame. Initialize it as version 1, status `model_missing`, quality 0, and `valid_mask=0`. Update sequence only when a camera observation completes. Recompute CRC before atomically replacing the readable snapshot.

- [x] **Step 4: Add the verified vendor camera project instead of guessing pins**

Import the vendor-provided camera initialization source or its verified pin table into `camera_capture_adapter.c`. If neither is available, the adapter must compile in acquisition-disabled mode and return `SG_CAMERA_STATUS_ERROR` with `valid_mask=0`; flashing an invented pin map is prohibited. Record the source URL/version and sensor identity in `firmware_camera/README.md` when supplied.

- [ ] **Step 5: Build and flash through the camera expansion board Type-C port**

Run after identifying its actual COM port:

```powershell
cd F:\iot_design\firmware_camera
idf.py set-target esp32s3
idf.py build
$CameraPort = Read-Host "Camera expansion-board COM port"
idf.py -p $CameraPort flash monitor
```

Expected before verified camera source: firmware boots and serves valid `model_missing` frames. Expected after verified source: local capture succeeds and quality changes with occlusion/exposure, while F/T/E remain invalid without model weights.

- [x] **Step 6: Commit and push**

```powershell
git add firmware_camera firmware_common host_pc/tests/test_camera_coprocessor_firmware.py
git commit -m "feat(camera): add score coprocessor firmware"
git push origin codex/preliminary-demo
```

### Task 6: Integrate, Verify Privacy, and Document Bring-Up

**Files:**
- Modify: `firmware_esp32/README.md`
- Modify: `docs/wiring.md`
- Modify: `docs/developer-handoff.md`
- Create: `docs/camera-nmo432-bringup.md`
- Modify: `host_pc/tests/test_e1_standalone_firmware.py`
- Modify: `host_pc/tests/test_camera_coprocessor_firmware.py`

**Interfaces:**
- Documents one reproducible two-board flash, wire, monitor, disconnect, reconnect, and privacy acceptance flow.
- Does not introduce any runtime interface.

- [x] **Step 1: Add failing documentation checks**

Verify documentation contains `GPIO8`, `GPIO9`, `GPIO17`, `GPIO18`, `GPIO16`, `0x42`, shared-ground warning, 5 V camera supply, 3.3 V NMO432 supply, I2C connector-order verification, and no claim that the installed camera is GC2145.

- [x] **Step 2: Write the bring-up guide**

Include separate COM discovery for N16R8 and camera board; flash commands for both projects; wiring order with power removed; camera I2C logic-voltage verification; NMO432 L/R selection; expected online/offline logs; and a warning that F/S/T/E remain unavailable until evaluated models are installed.

- [x] **Step 3: Run software verification**

Run:

```powershell
python -m pytest host_pc/tests -q
cd F:\iot_design\firmware_esp32
idf.py build
cd F:\iot_design\firmware_camera
idf.py build
git diff --check
```

Expected: all PC tests pass, both ESP-IDF projects build, and `git diff --check` emits no output.

- [ ] **Step 4: Run 30-minute hardware acceptance**

Confirm increasing camera sequence/valid CRC, changing microphone RMS, continued CSI/MQTT operation, camera offline state after disconnect, automatic recovery after reconnect, no reboot or unbounded memory loss, `insufficient` while models are absent, and absence of JPEG/PCM/MFCC fields in MQTT and InfluxDB.

- [x] **Step 5: Commit and push**

```powershell
git add firmware_esp32/README.md docs host_pc/tests
git commit -m "docs(device): add camera and NMO432 bring-up"
git push origin codex/preliminary-demo
```
