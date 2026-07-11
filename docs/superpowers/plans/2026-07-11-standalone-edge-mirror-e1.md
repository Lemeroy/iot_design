# Standalone Edge Mirror E1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ESP32-S3 independently produce deterministic fusion results, alarm locally while offline, publish numeric-only MQTT uplinks, and consume bounded advice downlinks without any PC runtime dependency.

**Architecture:** Add a thread-safe local score bus whose producers are future edge perception modules, then run fusion periodically from that bus plus the existing CSI score. Build MQTT payloads with cJSON, send them directly through ESP-MQTT, and route validated advice into a local alert/UI controller; USB remains telemetry/debug only. The existing cloud contract is made strict so media fields and topic/device mismatches are rejected.

**Tech Stack:** ESP-IDF 5.5.3, ESP32-S3-WROOM-1 N16R8, FreeRTOS, ESP-MQTT, NVS, cJSON, USB-Serial-JTAG, Python 3.14, pytest, FastAPI/Pydantic, EMQX.

## Global Constraints

- Target board is `ESP32-S3-WROOM-1 N16R8`; build and flash through `COM3`.
- The firmware must function with PC disconnected and cloud unreachable.
- Original image, audio, MFCC, landmarks, ROI data, and reconstructable biometric features never enter MQTT or cloud storage.
- MQTT topics remain `strokeguard/<device_id>/uplink` and `strokeguard/<device_id>/downlink`.
- Scores are integers in `0..100`; unavailable modalities are represented internally as `-1` and serialized as JSON `null`.
- The deterministic fusion weights and veto rules remain exactly those in `fusion.c`; cloud advice cannot lower or cancel local alarms.
- E1 may use MQTT 1883 only for the controlled competition/development deployment. TLS 8883 and device ACL hardening remain E6 acceptance requirements.
- Hardware pins remain `-1` and external drivers remain disabled until actual wiring is confirmed.
- With only CSI available in E1, the honest production result is `insufficient`; danger/normal paths are exercised by unit fixtures, not fabricated runtime sensor scores.
- The device does not publish an uplink until SNTP provides a sane Unix timestamp; local fusion and alerts never wait for time synchronization.
- Never print or commit Wi-Fi, MQTT, VPS, or LLM credentials.

---

## File Map

**Create:**

- `firmware_esp32/main/score_bus.h` and `.c`: thread-safe locally produced F/S/T/E score snapshot with freshness handling.
- `firmware_esp32/main/device_config.h` and `.c`: versioned NVS device/profile/MQTT configuration with CRC32 validation.
- `firmware_esp32/main/cloud_contract.h` and `.c`: numeric uplink builder and bounded downlink parser.
- `firmware_esp32/main/sg_mqtt.h` and `.c`: ESP-MQTT lifecycle, QoS 1 publishing, fragmented downlink assembly, reconnect state.
- `firmware_esp32/main/sg_time.h` and `.c`: nonblocking SNTP startup and validated Unix timestamp access.
- `firmware_esp32/main/local_alert.h` and `.c`: authoritative local level plus optional advice presentation.
- `firmware_esp32/test_apps/e1_core/`: ESP-IDF Unity app that proves local danger remains authoritative after lower-level cloud advice.
- `host_pc/tests/test_e1_standalone_firmware.py`: source-boundary and privacy regression tests.
- `host_pc/tests/test_e1_cloud_contract.py`: strict cloud schema and topic/device tests.
- `docs/e1-standalone-bringup.md`: secure configuration, COM3 flash, offline and cloud acceptance checklist.

**Modify:**

- `.gitignore` and `cloud/.gitignore`: exclude local sessions and PFX key containers before the source baseline commit.
- `firmware_esp32/main/app_main.c`: replace PC-triggered fusion with periodic local fusion and connect MQTT/alert modules.
- `firmware_esp32/main/app_config.h`: E1 task sizes, periods, payload bounds, and firmware version.
- `firmware_esp32/main/Kconfig.projbuild`: device ID, broker URI/user/password, profile defaults, legacy USB stream switch.
- `firmware_esp32/main/CMakeLists.txt`: register E1 sources and `mqtt` dependency; stop linking `scores_parser.c` into production.
- `firmware_esp32/sdkconfig.defaults`: safe empty defaults and legacy USB stream disabled.
- `cloud/backend/app/schemas.py`: explicitly model `schema_version` and `seq`, reject extra fields.
- `cloud/backend/app/mqtt_bridge.py`: reject topic/payload device mismatch and remove provider exception leakage fallback.
- `firmware_esp32/README.md` and root `README.md`: replace PC score-input instructions with standalone E1 operation.

**Retain but stop using in production:**

- `firmware_esp32/main/scores_parser.*`: historical USB score parser for reference; no call from `app_main.c` and no production linkage.
- `firmware_esp32/main/sensor_frame.*`: legacy synthetic USB frame builder, compiled only when the explicit legacy stream switch is enabled.

---

### Task 1: Establish a Safe Source Baseline

**Files:**
- Modify: `.gitignore`
- Modify: `cloud/.gitignore`
- Inspect: `cloud/.env`, `cloud/emqx/certs/`, `data/`, `host_pc/data/`, `firmware_esp32/sdkconfig`

**Interfaces:**
- Consumes: the current root commit containing architecture documents.
- Produces: a tracked source baseline from which a worktree can be created; no credentials, generated sessions, build output, or private certificate containers are tracked.

- [ ] **Step 1: Add failing ignore assertions**

Create a temporary PowerShell check in the shell; do not add a script file:

```powershell
$paths = @(
  'data/session_20260711_143654',
  'cloud/emqx/certs/server.pfx',
  'cloud/.env',
  'firmware_esp32/sdkconfig',
  'host_pc/data/session_20260709_203545'
)
foreach ($path in $paths) {
  git check-ignore $path | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "not ignored: $path" }
}
```

Expected: FAIL for root `data/` and `cloud/emqx/certs/*.pfx`.

- [ ] **Step 2: Add the exact ignore rules**

Append to root `.gitignore`:

```gitignore
# Local recordings and evaluation captures
data/

# Local editor/OS state
.vscode/
.idea/
Thumbs.db
```

Append to `cloud/.gitignore` below the certificate rules:

```gitignore
emqx/certs/*.pfx
emqx/certs/*.p12
```

- [ ] **Step 3: Re-run ignore and staged-secret checks**

Run the Step 1 command again. Expected: PASS.

Stage only source/config templates, not generated files:

```powershell
git add .gitattributes .gitignore cloud docs/wiring.md docs/superpowers/plans firmware_esp32 host_pc launch.ps1 scripts
git diff --cached --check
git status --short
```

Expected: `cloud/.env`, `*.pfx`, `data/`, `host_pc/data/`, `.venv/`, `firmware_esp32/build/`, and `firmware_esp32/sdkconfig` are absent from the staged list.

Run a staged-content scan:

```powershell
git grep --cached -n -E 'BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY|api[_-]?key[=:][^< ]{12,}'
```

Expected: no matches and exit code 1. If a match exists, unstage the containing file and add an ignore rule before continuing.

- [ ] **Step 4: Commit the baseline**

```powershell
git commit -m "chore: establish project source baseline"
```

Expected: one commit containing project source and templates only.

---

### Task 2: Replace PC Score Injection with a Local Score Bus

**Files:**
- Create: `firmware_esp32/main/score_bus.h`
- Create: `firmware_esp32/main/score_bus.c`
- Create: `host_pc/tests/test_e1_standalone_firmware.py`
- Modify: `firmware_esp32/main/app_main.c`
- Modify: `firmware_esp32/main/app_config.h`
- Modify: `firmware_esp32/main/CMakeLists.txt`

**Interfaces:**
- Consumes: `sg_scores_in_t` from `fusion.h` and `sg_csi_get_score()` from `csi_monitor.h`.
- Produces: `esp_err_t sg_score_bus_init(void)`, four typed producer setters, and `void sg_score_bus_snapshot(sg_scores_in_t *out, int64_t now_us, uint32_t stale_ms)`.

- [ ] **Step 1: Write the failing architecture tests**

Create `host_pc/tests/test_e1_standalone_firmware.py`:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "firmware_esp32" / "main"


def read(name: str) -> str:
    return (MAIN / name).read_text(encoding="utf-8")


def test_local_score_bus_is_wired_into_fusion():
    assert (MAIN / "score_bus.h").is_file()
    assert (MAIN / "score_bus.c").is_file()
    app = read("app_main.c")
    assert '#include "score_bus.h"' in app
    assert "sg_score_bus_snapshot" in app
    assert "sg_csi_get_score" in app
    assert "sg_fusion_compute" in app


def test_production_app_does_not_accept_pc_scores():
    app = read("app_main.c")
    cmake = read("CMakeLists.txt")
    assert "on_cdc_rx" not in app
    assert "sg_scores_parse" not in app
    assert '"scores_parser.c"' not in cmake


def test_no_runtime_fabricated_healthy_scores():
    bus = read("score_bus.c")
    assert "memset(out, 0xFF" not in bus
    assert "NAN" in bus
    assert "score = -1" in bus
```

- [ ] **Step 2: Run tests and verify failure**

```powershell
Set-Location host_pc
.venv\Scripts\python.exe -m pytest -q tests\test_e1_standalone_firmware.py
```

Expected: FAIL because `score_bus.*` does not exist and PC score injection is still present.

- [ ] **Step 3: Add the score bus interface**

Write `score_bus.h` with this public API:

```c
#pragma once

#include <stdint.h>
#include "esp_err.h"
#include "fusion.h"

esp_err_t sg_score_bus_init(void);
esp_err_t sg_score_bus_set_face(int score, float theta_deg, int64_t now_us);
esp_err_t sg_score_bus_set_speech(int score, float p_clear, int64_t now_us);
esp_err_t sg_score_bus_set_tongue(int score, int64_t now_us);
esp_err_t sg_score_bus_set_eye(int score, int64_t now_us);
void sg_score_bus_snapshot(sg_scores_in_t *out, int64_t now_us,
                           uint32_t stale_ms);
```

Implement `score_bus.c` with one FreeRTOS mutex and a private entry per F/S/T/E. Every entry initializes with `score = -1`, `aux = NAN`, and timestamp `0`. Setters reject scores outside `0..100`, face angles outside `0..90`, and speech probabilities outside `0..1`. `sg_score_bus_snapshot` copies only entries whose timestamp is positive and not older than `stale_ms`; every other output score is `-1`, both auxiliary floats are `NAN`, and `out->csi` remains `-1` for the caller to fill.

- [ ] **Step 4: Convert fusion to a periodic local task**

In `app_main.c`:

1. Remove `scores_parser.h`, the score queue, `on_cdc_rx`, and `sg_cdc_set_rx_cb`.
2. Initialize `sg_score_bus_init()` after NVS.
3. Change `task_fusion` to run every `SG_TASK_FUSION_PERIOD_MS`, snapshot local scores, set `in.csi = sg_csi_get_score()`, increment `in.seq`, call `sg_fusion_compute(&in, -1, &out)`, and emit the existing USB fusion telemetry.
4. Call the local alert interface added in Task 6 through a temporary `ESP_LOGI` in this task; do not create a fake sensor producer.

Add to `app_config.h`:

```c
#define SG_TASK_FUSION_PERIOD_MS 1000
#define SG_SCORE_STALE_MS        5000
```

Register `score_bus.c` and remove `scores_parser.c` from production `CMakeLists.txt`.

- [ ] **Step 5: Run tests and firmware build**

```powershell
Set-Location host_pc
.venv\Scripts\python.exe -m pytest -q tests\test_e1_standalone_firmware.py tests\test_fusion.py
Set-Location ..\firmware_esp32
. 'E:\esp\v5.5.3\esp-idf\export.ps1'
idf.py build
```

Expected: all selected pytest tests PASS and ESP-IDF build exits 0.

- [ ] **Step 6: Commit**

```powershell
git add firmware_esp32/main/score_bus.* firmware_esp32/main/app_main.c firmware_esp32/main/app_config.h firmware_esp32/main/CMakeLists.txt host_pc/tests/test_e1_standalone_firmware.py
git commit -m "feat(firmware): fuse locally produced edge scores"
```

---

### Task 3: Add Versioned NVS Device Configuration

**Files:**
- Create: `firmware_esp32/main/device_config.h`
- Create: `firmware_esp32/main/device_config.c`
- Modify: `firmware_esp32/main/Kconfig.projbuild`
- Modify: `firmware_esp32/sdkconfig.defaults`
- Modify: `firmware_esp32/main/CMakeLists.txt`
- Modify: `host_pc/tests/test_e1_standalone_firmware.py`

**Interfaces:**
- Produces: `sg_device_config_t`, `esp_err_t sg_device_config_load(sg_device_config_t *out)`, and `bool sg_device_config_mqtt_ready(const sg_device_config_t *cfg)`.
- Persists: NVS namespace `sg_cfg`, key `device`, schema version `1`, CRC32 over the struct bytes preceding `crc32`.

- [ ] **Step 1: Extend the failing static test**

Append:

```python
def test_nvs_config_has_version_crc_and_no_real_credentials():
    header = read("device_config.h")
    source = read("device_config.c")
    kconfig = read("Kconfig.projbuild")
    defaults = (ROOT / "firmware_esp32" / "sdkconfig.defaults").read_text(encoding="utf-8")
    assert "SG_DEVICE_CONFIG_VERSION" in header
    assert "crc32" in header
    assert 'nvs_open("sg_cfg"' in source
    assert '"device"' in source
    assert "CONFIG_STROKEGUARD_MQTT_URI" in kconfig
    assert "CONFIG_STROKEGUARD_DEVICE_ID" in kconfig
    assert "106.75.229.61" not in defaults
```

Run the target test. Expected: FAIL because the files/symbols do not exist.

- [ ] **Step 2: Define the fixed-size configuration**

Write `device_config.h`:

```c
#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#define SG_DEVICE_CONFIG_VERSION 1U
#define SG_DEVICE_ID_MAX         32
#define SG_MQTT_URI_MAX          127
#define SG_MQTT_USER_MAX         63
#define SG_MQTT_PASS_MAX         95
#define SG_PROFILE_ITEM_MAX      4
#define SG_PROFILE_TEXT_MAX      31

typedef struct {
    uint32_t schema_version;
    char device_id[SG_DEVICE_ID_MAX + 1];
    char mqtt_uri[SG_MQTT_URI_MAX + 1];
    char mqtt_user[SG_MQTT_USER_MAX + 1];
    char mqtt_pass[SG_MQTT_PASS_MAX + 1];
    uint8_t age;
    char gender[6];
    bool stroke_history;
    uint8_t condition_count;
    char conditions[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1];
    uint8_t med_count;
    char meds[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1];
    uint32_t crc32;
} sg_device_config_t;

esp_err_t sg_device_config_load(sg_device_config_t *out);
bool sg_device_config_mqtt_ready(const sg_device_config_t *cfg);
```

Implement `device_config.c` using `nvs_open("sg_cfg", NVS_READWRITE, &handle)`, `nvs_get_blob`, `nvs_set_blob`, `nvs_commit`, and `esp_crc32_le`. On a missing/invalid blob, construct factory defaults from Kconfig, calculate CRC, persist once, and return them. Reject invalid version, missing NUL terminators, age above 130, gender outside `M/F/other`, item counts above four, device IDs outside `[A-Za-z0-9_-]`, and MQTT URIs not beginning with `mqtt://` or `mqtts://`. Never log `mqtt_pass`.

- [ ] **Step 3: Add safe Kconfig defaults**

Add these symbols under the main StrokeGuard menu:

```kconfig
config STROKEGUARD_DEVICE_ID
    string "Device ID"
    default "sg-0001"

config STROKEGUARD_MQTT_URI
    string "MQTT broker URI"
    default ""

config STROKEGUARD_MQTT_USERNAME
    string "MQTT device username"
    default ""

config STROKEGUARD_MQTT_PASSWORD
    string "MQTT device password"
    default ""

config STROKEGUARD_PROFILE_AGE
    int "Profile age"
    range 0 130
    default 0

config STROKEGUARD_PROFILE_GENDER
    string "Profile gender: M, F, or other"
    default "other"
```

Mirror only non-secret placeholders in `sdkconfig.defaults`. Register `device_config.c` and add `esp_hw_support` if the CRC header requires it.

- [ ] **Step 4: Verify tests and build**

Run the targeted pytest file and `idf.py build`. Expected: PASS and exit 0.

- [ ] **Step 5: Commit**

```powershell
git add firmware_esp32/main/device_config.* firmware_esp32/main/Kconfig.projbuild firmware_esp32/sdkconfig.defaults firmware_esp32/main/CMakeLists.txt host_pc/tests/test_e1_standalone_firmware.py
git commit -m "feat(firmware): persist validated device configuration"
```

---

### Task 4: Implement Numeric Uplink and Bounded Advice Contracts

**Files:**
- Create: `firmware_esp32/main/cloud_contract.h`
- Create: `firmware_esp32/main/cloud_contract.c`
- Modify: `firmware_esp32/main/CMakeLists.txt`
- Modify: `host_pc/tests/test_e1_standalone_firmware.py`

**Interfaces:**
- Consumes: `sg_device_config_t`, `sg_scores_in_t`, `sg_fusion_out_t`, Unix timestamp, and sequence number.
- Produces: `int sg_cloud_build_uplink(char *, size_t, const sg_device_config_t *, const sg_scores_in_t *, const sg_fusion_out_t *, int64_t, uint32_t)` and `sg_contract_err_t sg_cloud_parse_advice(const char *, size_t, sg_cloud_advice_t *)`.

- [ ] **Step 1: Add contract boundary tests**

Append tests requiring `cloud_contract.*`, all required JSON field names, cJSON usage, `SG_ADVICE_TEXT_MAX`, and absence of `jpeg_b64`, `mfcc`, `landmarks`, and `roi` literals from `cloud_contract.c`.

Use this exact test body:

```python
def test_firmware_cloud_contract_is_numeric_only_and_bounded():
    header = read("cloud_contract.h")
    source = read("cloud_contract.c")
    for field in ('"scores"', '"face"', '"speech"', '"tongue"', '"eye"',
                  '"csi"', '"final"', '"level"', '"profile"', '"device_id"'):
        assert field in source
    assert "cJSON_CreateObject" in source
    assert "SG_ADVICE_TEXT_MAX" in header
    lowered = source.lower()
    for forbidden in ("jpeg_b64", "mfcc", "landmarks", '"roi"'):
        assert forbidden not in lowered
```

Run it. Expected: FAIL.

- [ ] **Step 2: Define the contract API**

Write `cloud_contract.h` with uplink cap `1536`, downlink cap `768`, advice text cap `384` UTF-8 bytes, source cap `64`, and:

```c
typedef enum {
    SG_CONTRACT_OK = 0,
    SG_CONTRACT_INVALID_JSON = -1,
    SG_CONTRACT_INVALID_FIELD = -2,
    SG_CONTRACT_TOO_LARGE = -3,
} sg_contract_err_t;

typedef struct {
    sg_level_t level;
    int64_t ts;
    char advice_text[SG_ADVICE_TEXT_MAX + 1];
    char source[SG_ADVICE_SOURCE_MAX + 1];
} sg_cloud_advice_t;

int sg_cloud_build_uplink(char *buf, size_t cap,
                          const sg_device_config_t *cfg,
                          const sg_scores_in_t *scores,
                          const sg_fusion_out_t *fusion,
                          int64_t unix_ts, uint32_t seq);

sg_contract_err_t sg_cloud_parse_advice(const char *json, size_t len,
                                        sg_cloud_advice_t *out);
```

- [ ] **Step 3: Implement with cJSON**

`sg_cloud_build_uplink` must create explicit objects/arrays, serialize unavailable modality scores as JSON null, include `schema_version=1`, `seq`, `reasons`, and `veto_by`, and use `cJSON_PrintPreallocated`. It must fail if any input pointer is null, the device ID is empty, the buffer is too small, or a supposedly available score is outside `0..100`.

`sg_cloud_parse_advice` must reject input above `SG_DOWNLINK_MAX`, malformed JSON, missing/unknown level, empty advice, advice/source over their caps, timestamps below zero, embedded NUL, invalid UTF-8, and any object containing keys other than `schema_version`, `level`, `advice_text`, `ts`, and `source`. Parse into a temporary struct and assign `*out` only on complete success.

- [ ] **Step 4: Run tests and build**

Run `test_e1_standalone_firmware.py`, `test_fusion.py`, and `idf.py build`. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add firmware_esp32/main/cloud_contract.* firmware_esp32/main/CMakeLists.txt host_pc/tests/test_e1_standalone_firmware.py
git commit -m "feat(firmware): add numeric cloud message contracts"
```

---

### Task 5: Add Direct ESP-MQTT Uplink and Downlink

**Files:**
- Create: `firmware_esp32/main/sg_mqtt.h`
- Create: `firmware_esp32/main/sg_mqtt.c`
- Create: `firmware_esp32/main/sg_time.h`
- Create: `firmware_esp32/main/sg_time.c`
- Modify: `firmware_esp32/main/app_main.c`
- Modify: `firmware_esp32/main/CMakeLists.txt`
- Modify: `firmware_esp32/main/app_config.h`
- Modify: `host_pc/tests/test_e1_standalone_firmware.py`

**Interfaces:**
- Consumes: validated `sg_device_config_t` and already-built uplink JSON.
- Produces: `sg_mqtt_start`, `sg_mqtt_publish_uplink`, `sg_mqtt_connected`, and an advice callback delivering `const sg_cloud_advice_t *`.

- [ ] **Step 1: Add failing MQTT tests**

Append:

```python
def test_esp_mqtt_is_direct_and_subscribes_to_device_downlink():
    header = read("sg_mqtt.h")
    source = read("sg_mqtt.c")
    cmake = read("CMakeLists.txt")
    assert "esp_mqtt_client_init" in source
    assert "esp_mqtt_client_subscribe" in source
    assert "esp_mqtt_client_enqueue" in source
    assert '"strokeguard/%s/uplink"' in source
    assert '"strokeguard/%s/downlink"' in source
    assert "sg_cloud_parse_advice" in source
    assert "total_data_len" in source and "current_data_offset" in source
    assert "mqtt" in cmake
    for line in source.splitlines():
        if "ESP_LOG" in line:
            assert "mqtt_pass" not in line


def test_sntp_time_gates_cloud_publish_only():
    time_source = read("sg_time.c")
    app = read("app_main.c")
    assert "esp_netif_sntp_init" in time_source
    assert "sg_time_sync_start" in app
```

Run it. Expected: FAIL.

- [ ] **Step 2: Define the MQTT adapter**

Write `sg_mqtt.h`:

```c
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "cloud_contract.h"
#include "device_config.h"

typedef void (*sg_mqtt_advice_cb_t)(const sg_cloud_advice_t *advice,
                                    void *ctx);

esp_err_t sg_mqtt_start(const sg_device_config_t *cfg,
                        sg_mqtt_advice_cb_t cb, void *ctx);
esp_err_t sg_mqtt_publish_uplink(const char *json, size_t len);
bool sg_mqtt_connected(void);
void sg_mqtt_stop(void);
```

- [ ] **Step 3: Implement ESP-MQTT lifecycle**

In `sg_mqtt.c`, keep one private client, connected event bit, copied config, bounded topic strings, and a `SG_DOWNLINK_MAX + 1` assembly buffer. Configure ESP-MQTT from `cfg->mqtt_uri`, username, and password; set keepalive to 30 seconds, reconnect timeout to 5 seconds, and client ID `sg-<device_id>`.

On `MQTT_EVENT_CONNECTED`, subscribe QoS 1 to the exact downlink topic. On the first `MQTT_EVENT_DATA` fragment (`current_data_offset == 0`), require the exact topic, reset assembly, record `total_data_len`, and validate it is no larger than `SG_DOWNLINK_MAX`. Later fragments are accepted only while that assembly is active and their offset/total length match. Parse/callback only when the complete payload has arrived. On disconnect clear the event bit and any partial assembly. Do not log credentials, profile contents, or advice text.

Publish with:

```c
int message_id = esp_mqtt_client_enqueue(
    s_client, s_uplink_topic, json, (int)len, 1, 0, true);
return message_id < 0 ? ESP_FAIL : ESP_OK;
```

Return `ESP_ERR_INVALID_STATE` when MQTT is not configured/started and `ESP_ERR_TIMEOUT` when not connected.

- [ ] **Step 4: Add nonblocking SNTP time validation**

Create `sg_time.h`:

```c
#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

esp_err_t sg_time_sync_start(void);
bool sg_time_is_synced(void);
int64_t sg_time_unix_seconds(void);
```

Implement `sg_time.c` with `ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org")` and `esp_netif_sntp_init`. `sg_time_unix_seconds()` calls `time(NULL)` and returns zero until the value is at least `1704067200` (2024-01-01 UTC); `sg_time_is_synced()` returns whether the same condition holds. Startup is nonblocking and never delays fusion. Call `sg_time_sync_start()` after `wifi_init_sta()` in `app_main.c`; log only success/failure, not network credentials.

- [ ] **Step 5: Register dependency and publish period**

Add `mqtt` to `REQUIRES` and this scheduling definition to `app_config.h`; payload bounds remain owned by `cloud_contract.h`:

```c
#define SG_MQTT_PUBLISH_PERIOD_MS 10000
#define SG_ADVICE_MAX_AGE_SEC       300
```

- [ ] **Step 6: Run tests and build**

Run the targeted pytest test and `idf.py build`. Expected: PASS and successful link against ESP-MQTT.

- [ ] **Step 7: Commit**

```powershell
git add firmware_esp32/main/sg_mqtt.* firmware_esp32/main/sg_time.* firmware_esp32/main/app_main.c firmware_esp32/main/CMakeLists.txt firmware_esp32/main/app_config.h host_pc/tests/test_e1_standalone_firmware.py
git commit -m "feat(firmware): connect mirror directly to MQTT"
```

---

### Task 6: Wire Authoritative Local Alerts and Advice Presentation

**Files:**
- Create: `firmware_esp32/main/local_alert.h`
- Create: `firmware_esp32/main/local_alert.c`
- Create: `firmware_esp32/test_apps/e1_core/CMakeLists.txt`
- Create: `firmware_esp32/test_apps/e1_core/main/CMakeLists.txt`
- Create: `firmware_esp32/test_apps/e1_core/main/test_e1_core.c`
- Modify: `firmware_esp32/main/app_main.c`
- Modify: `firmware_esp32/main/Kconfig.projbuild`
- Modify: `firmware_esp32/sdkconfig.defaults`
- Modify: `firmware_esp32/main/CMakeLists.txt`
- Modify: `host_pc/tests/test_e1_standalone_firmware.py`

**Interfaces:**
- Consumes: local `sg_fusion_out_t` and validated `sg_cloud_advice_t`.
- Produces: `sg_local_alert_init`, `sg_local_alert_apply_fusion`, `sg_local_alert_apply_advice`, and `sg_local_alert_get_level`.

- [ ] **Step 1: Write failing authority tests**

Append:

```python
def test_local_alarm_is_authoritative_and_usb_stream_defaults_off():
    source = read("local_alert.c")
    app = read("app_main.c")
    kconfig = read("Kconfig.projbuild")
    assert "sg_local_alert_apply_fusion" in app
    assert "sg_local_alert_apply_advice" in app
    assert "SG_ADVICE_MAX_AGE_SEC" in app
    assert "sg_alert_io_set_level" in source
    assert "sg_display_st7789_show_status" in source
    assert "advice->level" not in source
    assert "CONFIG_STROKEGUARD_LEGACY_USB_STREAM" in app
    block = kconfig.split("config STROKEGUARD_LEGACY_USB_STREAM", 1)[1].split("\n\n", 1)[0]
    assert "default n" in block
```

Run it. Expected: FAIL.

- [ ] **Step 2: Define and implement local alert state**

Use this API:

```c
esp_err_t sg_local_alert_init(void);
void sg_local_alert_apply_fusion(const sg_fusion_out_t *fusion);
void sg_local_alert_apply_advice(const sg_cloud_advice_t *advice);
sg_level_t sg_local_alert_get_level(void);
```

Protect state with a mutex. `apply_fusion` is the only function allowed to update the authoritative level. It must immediately call `sg_alert_io_set_level(sg_fusion_level_name(level))` and display one of these fixed local texts before any cloud response:

```text
normal: 当前未发现明显异常，请继续观察
warning: 检测到风险变化，请家属陪同并尽快评估
danger: 疑似高风险，请立即拨打120
insufficient: 数据不足，请按提示重新测量
```

`apply_advice` stores/displays only `advice_text`; it must not read `advice->level` and must not call `sg_alert_io_set_level`. If the local level is danger, prepend/retain the fixed danger text so cloud wording cannot soften it. Hardware adapters returning `ESP_ERR_NOT_SUPPORTED` are logged once at initialization, not on every 1 Hz update.

- [ ] **Step 3: Integrate config, MQTT, fusion, and alert tasks**

In `app_main.c`:

1. Load `sg_device_config_t` after NVS and initialize local alert plus score bus.
2. Start Wi-Fi, CSI, and MQTT independently. If MQTT config is invalid, log `mqtt disabled: configuration incomplete` without credentials and continue offline.
3. In `task_fusion`, apply every local fusion immediately. Read `sg_time_unix_seconds()` and build/publish an uplink on level change and at most once per `SG_MQTT_PUBLISH_PERIOD_MS`; skip publish while disconnected or while the timestamp is zero, without blocking local fusion.
4. Register an MQTT advice callback that copies the validated advice into a length-one FreeRTOS queue. A UI task drains the queue, compares `advice.ts` with `sg_time_unix_seconds()`, rejects messages more than `SG_ADVICE_MAX_AGE_SEC` old or more than 30 seconds in the future, and calls `sg_local_alert_apply_advice` outside the MQTT event callback.
5. Keep heartbeat/fusion USB telemetry. Create `task_sensor_frame` only when `CONFIG_STROKEGUARD_LEGACY_USB_STREAM=y`; default `n` in Kconfig and sdkconfig defaults.
6. Update `SG_FW_VERSION` to `e1-0.5.0`.

- [ ] **Step 4: Add a target-side authority test**

Create `firmware_esp32/test_apps/e1_core/CMakeLists.txt`:

```cmake
cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(strokeguard_e1_core_tests)
```

Create `firmware_esp32/test_apps/e1_core/main/CMakeLists.txt`:

```cmake
idf_component_register(
    SRCS
        "test_e1_core.c"
        "../../../main/fusion.c"
        "../../../main/local_alert.c"
    INCLUDE_DIRS "../../../main"
    REQUIRES unity freertos log
)
```

In `test_e1_core.c`, define mock implementations of `sg_alert_io_init`, `sg_alert_io_set_level`, `sg_display_st7789_init`, and `sg_display_st7789_show_status` that capture the latest level/text. Register a Unity test tagged `[e1][alert]` containing:

```c
sg_fusion_out_t fusion = { .level = SG_LEVEL_DANGER };
sg_cloud_advice_t advice = {
    .level = SG_LEVEL_NORMAL,
    .ts = 1,
    .advice_text = "continue observing",
    .source = "test",
};

TEST_ASSERT_EQUAL(ESP_OK, sg_local_alert_init());
sg_local_alert_apply_fusion(&fusion);
TEST_ASSERT_EQUAL_STRING("danger", captured_level);
TEST_ASSERT_EQUAL(SG_LEVEL_DANGER, sg_local_alert_get_level());

sg_local_alert_apply_advice(&advice);
TEST_ASSERT_EQUAL_STRING("danger", captured_level);
TEST_ASSERT_EQUAL(SG_LEVEL_DANGER, sg_local_alert_get_level());
```

Add a second `[e1][fusion]` test using F=20 and all other modalities 80; call `sg_fusion_compute` and assert `SG_LEVEL_DANGER` plus `veto_face == 1`. Its `app_main` calls `unity_run_all_tests()` and then delays forever so the serial result remains visible.

- [ ] **Step 5: Run focused tests, firmware build, and Unity app**

```powershell
Set-Location host_pc
.venv\Scripts\python.exe -m pytest -q tests\test_e1_standalone_firmware.py tests\test_fusion.py tests\test_cdc_parser.py
.venv\Scripts\python.exe -m pytest -q
Set-Location ..\firmware_esp32
. 'E:\esp\v5.5.3\esp-idf\export.ps1'
idf.py build
idf.py -C test_apps/e1_core set-target esp32s3
idf.py -C test_apps/e1_core build
idf.py -C test_apps/e1_core -p COM3 flash monitor
```

Expected: all pytest tests PASS, both ESP-IDF builds exit 0, and serial output reports two Unity tests with zero failures. Exit monitor with `Ctrl+]`.

- [ ] **Step 6: Commit**

```powershell
git add firmware_esp32/main/local_alert.* firmware_esp32/main/app_main.c firmware_esp32/main/Kconfig.projbuild firmware_esp32/sdkconfig.defaults firmware_esp32/main/CMakeLists.txt firmware_esp32/test_apps/e1_core host_pc/tests/test_e1_standalone_firmware.py
git commit -m "feat(firmware): keep alarms local and authoritative"
```

---

### Task 7: Make the Cloud Contract Strict

**Files:**
- Create: `host_pc/tests/test_e1_cloud_contract.py`
- Modify: `cloud/backend/app/schemas.py`
- Modify: `cloud/backend/app/mqtt_bridge.py`

**Interfaces:**
- Consumes: the E1 uplink payload from Task 4.
- Produces: Pydantic validation that rejects unknown/media fields and MQTT routing that rejects mismatched device IDs.

- [ ] **Step 1: Write failing cloud tests**

Create `host_pc/tests/test_e1_cloud_contract.py`:

```python
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cloud.backend.app.schemas import UplinkPayload


def valid_payload():
    return {
        "schema_version": 1,
        "scores": {"face": None, "speech": None, "tongue": None,
                   "eye": None, "csi": 80, "final": 0},
        "level": "insufficient",
        "profile": {"age": 68, "gender": "other", "conditions": [],
                    "meds": [], "stroke_history": False},
        "reasons": ["avail weight sum 0.08 < 0.50"],
        "veto_by": [],
        "device_id": "sg-0001",
        "ts": 1783760000,
        "seq": 1,
    }


@pytest.mark.parametrize("field,value", [
    ("jpeg_b64", "/9j/"), ("mfcc", [[0.1]]),
    ("landmarks", [[1, 2]]), ("roi", "raw"),
])
def test_uplink_rejects_raw_or_unknown_fields(field, value):
    payload = valid_payload()
    payload[field] = value
    with pytest.raises(ValidationError):
        UplinkPayload(**payload)


def test_uplink_accepts_versioned_numeric_payload():
    parsed = UplinkPayload(**valid_payload())
    assert parsed.schema_version == 1
    assert parsed.seq == 1
    assert parsed.scores.csi == 80


def test_bridge_checks_topic_device_before_storage():
    source = (ROOT / "cloud" / "backend" / "app" / "mqtt_bridge.py").read_text(
        encoding="utf-8"
    )
    check = "if up.device_id != device_id:"
    assert check in source
    assert source.index(check) < source.index("self._influx.write_uplink")
```

Run the file. Expected: FAIL because extras are currently ignored and version/seq are not modeled.

- [ ] **Step 2: Enforce strict Pydantic models**

Import `ConfigDict` and define a shared base:

```python
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

Make `Scores`, `Profile`, `UplinkPayload`, and `DownlinkPayload` inherit `StrictModel`. Add:

```python
schema_version: Literal[1] = 1
seq: int = Field(default=0, ge=0)
```

to `UplinkPayload`, and `schema_version: Literal[1] = 1` to `DownlinkPayload`. Keep existing field names and levels unchanged.

- [ ] **Step 3: Reject topic/device mismatch and sanitize failures**

Immediately after parsing `up` in `_on_message`:

```python
if up.device_id != device_id:
    log.warning("uplink device mismatch topic=%s", device_id)
    return
```

In `_handle_advice`, do not publish provider exception text. On failure, publish the fixed safe text `建议服务暂时不可用；请以镜端风险提示为准，如有突发症状立即拨打120。` and mark source as `fallback`.

- [ ] **Step 4: Run cloud and full tests**

```powershell
Set-Location host_pc
.venv\Scripts\python.exe -m pytest -q tests\test_e1_cloud_contract.py tests\test_cloud_native_contract.py tests\test_cloud_llm_optional.py
.venv\Scripts\python.exe -m pytest -q
```

Expected: all tests PASS.

- [ ] **Step 5: Redeploy the strict backend and verify health**

From the repository root, run the existing interactive deployer; enter the VPS password only into its secure prompt:

```powershell
Set-Location ..
.\scripts\deploy_cloud_native_interactive.ps1
Invoke-RestMethod 'http://106.75.229.61:8000/health'
```

Expected: deployment exits 0 and health returns `status=ok`, `mqtt=true`, and `influx=true`. Deployment logs must not contain MQTT, InfluxDB, or LLM secrets.

- [ ] **Step 6: Commit**

```powershell
git add cloud/backend/app/schemas.py cloud/backend/app/mqtt_bridge.py host_pc/tests/test_e1_cloud_contract.py
git commit -m "fix(cloud): reject nonnumeric device uplinks"
```

---

### Task 8: Flash COM3 and Prove Standalone End-to-End Behavior

**Files:**
- Create: `docs/e1-standalone-bringup.md`
- Modify: `firmware_esp32/README.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: E1 firmware, the deployed EMQX/FastAPI service, and MQTT device credentials entered locally.
- Produces: reproducible evidence for offline fusion/alarm and S3-direct uplink/downlink.

- [ ] **Step 1: Write the bring-up checklist before flashing**

Document these exact acceptance sections in `docs/e1-standalone-bringup.md`:

```markdown
## Secret-safe configuration
Use `idf.py menuconfig`; do not place credentials in `sdkconfig.defaults`, logs, screenshots, or Git.

## Build and flash
Record firmware SHA-256, app size, free IRAM/DRAM, COM port, and build timestamp.

## Offline acceptance
Disconnect PC after flashing, block WAN/MQTT, and verify 1 Hz local fusion continues. With E1 CSI-only input, expected level is `insufficient`; a target-side fusion fixture separately verifies warning/danger dispatch.

## Cloud acceptance
Verify the latest device record originates from `sg-0001`, contains only numeric/profile fields, and produces a bounded advice downlink.

## Privacy acceptance
Subscribe to `strokeguard/sg-0001/#` and confirm no JPEG, audio, MFCC, landmark, ROI, or raw field occurs.
```

- [ ] **Step 2: Configure without committing secrets**

```powershell
Set-Location firmware_esp32
. 'E:\esp\v5.5.3\esp-idf\export.ps1'
idf.py menuconfig
```

Set Wi-Fi, device ID `sg-0001`, broker URI, and dedicated device MQTT credentials. After saving, verify `firmware_esp32/sdkconfig` remains ignored with `git check-ignore firmware_esp32/sdkconfig`.

- [ ] **Step 3: Build, flash, and capture non-secret evidence**

```powershell
idf.py build
idf.py -p COM3 flash monitor
```

Expected serial evidence within 30 seconds:

```text
boot fw=e1-0.5.0
GOT_IP
csi started
mqtt connected
fusion seq=1 final=0 level=insufficient
uplink queued
downlink accepted
```

The logs must not contain Wi-Fi password, MQTT password, full profile JSON, or advice text. Exit monitor with `Ctrl+]`, unplug USB, power the S3 independently, and verify the device continues its local fusion/alarm loop.

- [ ] **Step 4: Verify the public cloud record**

```powershell
Invoke-RestMethod 'http://106.75.229.61:8000/health'
Invoke-RestMethod 'http://106.75.229.61:8000/devices/sg-0001/latest'
```

Expected: health has `status=ok`, `mqtt=true`, and `influx=true`; latest has `device_id=sg-0001`, a recent `last_uplink_ts`, `latest_level=insufficient` for CSI-only E1, and non-empty `last_advice.advice_text` when the LLM/fallback path responds.

- [ ] **Step 5: Run final regression and inspect repository state**

```powershell
Set-Location host_pc
.venv\Scripts\python.exe -m pytest -q
Set-Location ..\firmware_esp32
idf.py build
Set-Location ..
git diff --check
git status --short
```

Expected: full pytest suite PASS, firmware build exits 0, no diff errors, no secrets/generated outputs staged.

- [ ] **Step 6: Commit documentation and E1 evidence**

Only record non-secret measurements and pass/fail outcomes:

```powershell
git add docs/e1-standalone-bringup.md firmware_esp32/README.md README.md
git commit -m "docs: record standalone E1 bring-up"
```

---

## E1 Definition of Done

- `app_main.c` has no PC score parser/callback and no runtime path requiring USB input.
- S3 computes a fusion result periodically from local score state plus CSI; missing modalities remain unavailable.
- Local alert state updates before MQTT publication and continues while MQTT is disconnected.
- S3 directly publishes the numeric-only contract with QoS 1 and subscribes to its exact downlink topic.
- Advice parsing is bounded, strict, fragmented-message safe, and unable to alter local level.
- Cloud rejects unknown/media fields and topic/payload device mismatch.
- Legacy synthetic USB media stream is disabled by default.
- Full pytest suite and ESP-IDF build pass.
- COM3 hardware run and public cloud latest-device query are recorded without secrets.
- Each task is committed separately; the final worktree is clean except for explicitly ignored local configuration/build output.
