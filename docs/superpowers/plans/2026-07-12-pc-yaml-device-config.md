# PC YAML and ESP32-S3 Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the PyQt5 PC application safely edit a strict local YAML profile and synchronize the profile whitelist to the standalone ESP32-S3 over an authenticated LAN API.

**Architecture:** The PC alone parses YAML and exposes form/YAML views over one Pydantic model. It sends strict JSON profile patches to an ESP-IDF HTTP server; firmware validates revision/authentication/bounds and atomically updates a versioned CRC-protected NVS blob. Runtime fusion remains device-authoritative and does not consume PC scores.

**Tech Stack:** Python 3.10+, Pydantic 2, PyYAML, PyQt5, `urllib.request`, keyring, pytest, ESP-IDF 5.5.3, `esp_http_server`, cJSON, NVS, FreeRTOS, Unity, ESP32-S3 N16R8.

## Global Constraints

- Raw image, audio, MFCC, landmarks, ROI, and reconstructable biometric data never enter this API, MQTT, or cloud storage.
- Wi-Fi, MQTT, VPS, LLM, and management credentials never appear in YAML, logs, tests, or Git.
- Current E1 writes only profile fields: age, gender, conditions, meds, and stroke history.
- Fusion weights, danger thresholds, veto rules, device ID, and network settings are read-only through the LAN API.
- PC failure, LAN failure, invalid YAML, and failed NVS writes cannot stop or lower local alarms.
- Use TDD for every behavior change and commit each completed task separately.
- Keep `firmware_esp32/sdkconfig`, `cloud/.env`, build output, and the unrelated user DOCX untracked.

---

## File Structure

```text
host_pc/stroke_host/config/profile_loader.py   strict models, migration, YAML parsing
host_pc/stroke_host/config/profile_store.py    atomic YAML serialization
host_pc/stroke_host/io/device_config_client.py private-LAN client and keyring token
host_pc/stroke_host/ui/config_panel.py         form/YAML editor and async sync signals
host_pc/stroke_host/ui/main_window.py          tabs/navigation only; remove score injection UI
host_pc/stroke_host/ui/theme.py                high-contrast editor/form styles
firmware_esp32/main/device_config.c/.h         v1->v2 migration, revision, locked snapshot/patch
firmware_esp32/main/sg_manager_api.c/.h        authenticated bounded HTTP JSON API
firmware_esp32/main/app_main.c                 start management server after Wi-Fi init
firmware_esp32/main/Kconfig.projbuild           local-only management token/port
```

---

### Task 1: Strict YAML Model and Atomic Store

**Files:**
- Modify: `host_pc/stroke_host/config/profile_loader.py`
- Create: `host_pc/stroke_host/config/profile_store.py`
- Modify: `host_pc/config/profile.yaml`
- Modify: `host_pc/tests/test_profile.py`
- Create: `host_pc/tests/test_profile_store.py`

**Interfaces:**
- Consumes: UTF-8 YAML path or text.
- Produces: `ProfileFile`, `load_profile(path)`, `parse_profile_yaml(text)`, `dump_profile_yaml(profile)`, and `save_profile_atomic(path, profile)`.

- [ ] **Step 1: Write failing strict-schema and migration tests**

Add tests that assert:

```python
def test_legacy_profile_migrates_to_v1(tmp_path):
    profile = load_profile(_write(tmp_path, """
        device_id: sg-test
        user: {age: 68, gender: M}
    """))
    assert profile.schema_version == 1
    assert profile.device.host == ""

def test_unknown_and_changed_medical_fields_are_rejected():
    with pytest.raises(ValueError):
        parse_profile_yaml("schema_version: 1\ndevice_id: sg\nunknown: true\nuser: {age: 1, gender: M}")
    with pytest.raises(ValueError, match="read-only"):
        parse_profile_yaml("""
        schema_version: 1
        device_id: sg
        user: {age: 68, gender: M}
        thresholds: {face_danger: 10, mouth_angle_danger_deg: 20, speech_danger: 35}
        """)

def test_public_management_host_is_rejected():
    with pytest.raises(ValueError, match="private"):
        parse_profile_yaml("""
        schema_version: 1
        device_id: sg
        device: {host: 8.8.8.8, port: 80}
        user: {age: 68, gender: M}
        """)
```

Cover 64 KiB input, invalid device ID, more than four list items, 31-character item bounds, and default release thresholds.

- [ ] **Step 2: Run the YAML tests and verify RED**

Run:

```powershell
cd host_pc
.venv\Scripts\python.exe -m pytest -q tests\test_profile.py tests\test_profile_store.py --basetemp=F:\iot_design\.pytest-native-root\yaml-red -p no:cacheprovider
```

Expected: failures for missing strict models, parser, and atomic store.

- [ ] **Step 3: Implement strict models and migration**

Use `ConfigDict(extra="forbid")`, `Field(default_factory=list)`, and these public types:

```python
RELEASE_THRESHOLDS = {
    "face_danger": 30,
    "mouth_angle_danger_deg": 20,
    "speech_danger": 35,
}

class DeviceEndpoint(StrictModel):
    host: str = ""
    port: int = Field(default=80, ge=1, le=65535)

class UserProfile(StrictModel):
    age: int = Field(ge=0, le=130)
    gender: Literal["M", "F", "other"]
    conditions: list[str] = Field(default_factory=list, max_length=4)
    meds: list[str] = Field(default_factory=list, max_length=4)
    stroke_history: bool = False

class Thresholds(StrictModel):
    face_danger: Literal[30] = 30
    mouth_angle_danger_deg: Literal[20] = 20
    speech_danger: Literal[35] = 35

class ProfileFile(StrictModel):
    schema_version: Literal[1] = 1
    device_id: str
    device: DeviceEndpoint = Field(default_factory=DeviceEndpoint)
    user: UserProfile
    thresholds: Thresholds = Field(default_factory=Thresholds)
```

Implement `_migrate(raw)` so a mapping without `schema_version` becomes version 1 and gains an empty `device`; reject every other version. Validate each profile item by Unicode character count and reject line breaks/control characters. Accept only private/link-local IP literals, empty host, or a hostname ending in `.local`.

- [ ] **Step 4: Implement deterministic atomic YAML save**

Expose:

```python
def dump_profile_yaml(profile: ProfileFile) -> str:
    return yaml.safe_dump(
        profile.model_dump(mode="json"),
        allow_unicode=True,
        sort_keys=False,
    )

def save_profile_atomic(path: str | Path, profile: ProfileFile) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(dump_profile_yaml(profile))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
```

Tests monkeypatch `os.replace` to fail and assert the old file is unchanged and the temporary file is removed.

- [ ] **Step 5: Update the sample YAML and run GREEN/full tests**

Update `host_pc/config/profile.yaml` to schema version 1 with an empty `device.host`; keep release thresholds unchanged and do not add credentials.

Run the targeted command, then:

```powershell
.venv\Scripts\python.exe -m pytest -q tests --basetemp=F:\iot_design\.pytest-native-root\yaml-full -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 1**

```powershell
git add host_pc/config/profile.yaml host_pc/stroke_host/config/profile_loader.py host_pc/stroke_host/config/profile_store.py host_pc/tests/test_profile.py host_pc/tests/test_profile_store.py
git commit -m "feat(host): validate and save profile YAML"
```

---

### Task 2: Configuration Workspace and Removal of PC Score Injection UI

**Files:**
- Create: `host_pc/stroke_host/ui/config_panel.py`
- Modify: `host_pc/stroke_host/ui/main_window.py`
- Modify: `host_pc/stroke_host/ui/theme.py`
- Create: `host_pc/tests/test_config_panel.py`
- Create: `host_pc/tests/test_e1_host_management_boundary.py`

**Interfaces:**
- Consumes: `ProfileFile`, YAML text, and profile path.
- Produces: `ConfigPanel.profile_saved(ProfileFile)`, `current_profile()`, `set_profile(profile)`, and `set_sync_busy(bool)`.

- [ ] **Step 1: Write failing UI and architecture-boundary tests**

Use `QT_QPA_PLATFORM=offscreen` and assert:

```python
def test_panel_round_trips_form_and_yaml(tmp_path, qt_app):
    panel = ConfigPanel(tmp_path / "profile.yaml")
    panel.age.setValue(72)
    panel.gender.setCurrentText("F")
    panel.apply_form_to_yaml()
    parsed = parse_profile_yaml(panel.yaml_editor.toPlainText())
    assert parsed.user.age == 72
    assert parsed.user.gender == "F"

def test_invalid_yaml_disables_save_and_sync(tmp_path, qt_app):
    panel = ConfigPanel(tmp_path / "profile.yaml")
    panel.yaml_editor.setPlainText("user: [")
    panel.validate_yaml()
    assert not panel.save_button.isEnabled()
    assert not panel.sync_button.isEnabled()

def test_main_window_has_no_pc_score_injection_path():
    source = Path("stroke_host/ui/main_window.py").read_text(encoding="utf-8")
    assert "S3 Fusion" not in source
    assert "S3Bridge" not in source
    assert "chk_s3" not in source
```

Also assert the editor stylesheet contains high-contrast text, selection, line-number, and disabled colors.

- [ ] **Step 2: Run UI tests and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest -q tests\test_config_panel.py tests\test_e1_host_management_boundary.py --basetemp=F:\iot_design\.pytest-native-root\ui-config-red -p no:cacheprovider
```

Expected: missing `ConfigPanel` and legacy injection assertions fail.

- [ ] **Step 3: Implement `ConfigPanel` as a focused widget**

Build an unframed `QWidget` with a `QTabWidget` for form and YAML modes. Use `QSpinBox` for age/port, `QComboBox` for gender, `QCheckBox` for stroke history, and one line per condition/medication. Use `QPlainTextEdit` for YAML with a monospace font and a narrow line-number gutter. Expose named controls used by tests and buttons:

```python
class ConfigPanel(QWidget):
    profile_saved = pyqtSignal(object)
    pull_requested = pyqtSignal()
    push_requested = pyqtSignal(object)

    def current_profile(self) -> ProfileFile:
        return parse_profile_yaml(self.yaml_editor.toPlainText())

    def validate_yaml(self) -> bool:
        try:
            self._valid_profile = self.current_profile()
        except ValueError as exc:
            self._valid_profile = None
            self.validation_label.setText(str(exc).splitlines()[0])
        valid = self._valid_profile is not None
        self.save_button.setEnabled(valid and not self._sync_busy)
        self.sync_button.setEnabled(valid and not self._sync_busy)
        return valid
```

Read-only threshold controls are labels, not inputs. Do not put explanatory product prose inside the workspace.

- [ ] **Step 4: Integrate monitor/config tabs and remove injection UI**

Wrap the existing monitor body in a `QWidget`, then add it and `ConfigPanel(args.profile)` to a top-level `QTabWidget` named `workspace_tabs`. Remove the `S3 Fusion` checkbox, `S3Bridge` import/member/start/stop wiring, and `s3_bridge` argument from `BackendWorker`. Preserve USB telemetry sources and legacy `io/s3_bridge.py` tests without exposing score injection in the production UI.

- [ ] **Step 5: Apply accessible high-contrast styles and run tests**

Add styles for `QPlainTextEdit`, `QSpinBox`, tabs, form labels, error text, disabled buttons, selection text, and scrollbars using the existing green/teal/red status palette. Keep card radii at 8 px or below and verify controls fit at 1220x820 and 1024x720 offscreen sizes.

Run targeted tests and full pytest. Expected: all pass without Qt warnings that indicate deleted-thread or cross-thread UI access.

- [ ] **Step 6: Commit Task 2**

```powershell
git add host_pc/stroke_host/ui/config_panel.py host_pc/stroke_host/ui/main_window.py host_pc/stroke_host/ui/theme.py host_pc/tests/test_config_panel.py host_pc/tests/test_e1_host_management_boundary.py
git commit -m "feat(ui): add profile YAML configuration workspace"
```

---

### Task 3: Version-2 Device Configuration and Atomic Profile Patch

**Files:**
- Modify: `firmware_esp32/main/device_config.h`
- Modify: `firmware_esp32/main/device_config.c`
- Modify: `firmware_esp32/main/Kconfig.projbuild`
- Modify: `firmware_esp32/sdkconfig.defaults`
- Modify: `firmware_esp32/test_apps/e1_core/main/test_e1_core.c`
- Modify: `host_pc/tests/test_e1_standalone_firmware.py`

**Interfaces:**
- Consumes: current version-1 NVS blob and bounded `sg_profile_patch_t`.
- Produces: `sg_device_config_snapshot`, `sg_device_config_apply_profile`, `sg_device_config_manager_ready`, and migration to version 2.

- [ ] **Step 1: Write failing source-boundary and Unity tests**

Require these declarations:

```c
#define SG_DEVICE_CONFIG_VERSION 2U
#define SG_MANAGER_TOKEN_MAX 64

typedef struct {
    uint8_t age;
    char gender[8];
    char conditions[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1];
    uint8_t condition_count;
    char meds[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1];
    uint8_t med_count;
    bool stroke_history;
} sg_profile_patch_t;

esp_err_t sg_device_config_snapshot(sg_device_config_t *out);
esp_err_t sg_device_config_apply_profile(uint32_t expected_revision,
                                         const sg_profile_patch_t *patch,
                                         sg_device_config_t *updated);
bool sg_device_config_manager_ready(const sg_device_config_t *cfg);
```

Unity tests cover valid revision increment, stale revision rejection with `ESP_ERR_INVALID_STATE`, invalid profile rejection, and unchanged snapshot after a rejected patch. Source tests require a private v1 storage struct and explicit migration path.

- [ ] **Step 2: Run tests and verify RED**

Run the relevant Python tests; build the Unity app. Expected: declarations and Unity cases are missing.

- [ ] **Step 3: Implement v2 struct, migration, and lock**

Add `revision`, `manager_port`, and `manager_token` before `crc32` in v2. Keep the exact v1 field order in a private `sg_device_config_v1_t` for migration. On a valid v1 blob, copy every field, set `revision=1`, take manager defaults from Kconfig, recalculate CRC, and persist v2 once.

Create a mutex during first load. `snapshot` copies under the mutex. `apply_profile` validates a candidate, persists it, and only then replaces the shared configuration. To keep `app_main` synchronized, change it to use snapshots rather than retaining an unlocked mutable global copy.

- [ ] **Step 4: Add safe manager Kconfig defaults**

```kconfig
config STROKEGUARD_MANAGER_PORT
    int "LAN management HTTP port"
    range 1 65535
    default 80

config STROKEGUARD_MANAGER_TOKEN
    string "LAN management token (local provisioning only)"
    default ""
```

Keep both values non-secret/empty in `sdkconfig.defaults`; the real token exists only in ignored local `sdkconfig` and PC keyring.

- [ ] **Step 5: Run Unity on COM3 and production build**

Run Python source tests, build/flash the Unity app, and verify all old and new cases pass. Rebuild production firmware and record binary size. Do not flash production until Task 4 adds the API.

- [ ] **Step 6: Commit Task 3**

```powershell
git add firmware_esp32/main/device_config.h firmware_esp32/main/device_config.c firmware_esp32/main/Kconfig.projbuild firmware_esp32/sdkconfig.defaults firmware_esp32/test_apps/e1_core/main/test_e1_core.c host_pc/tests/test_e1_standalone_firmware.py
git commit -m "feat(firmware): apply versioned profile updates"
```

---

### Task 4: Authenticated ESP32-S3 LAN Management API

**Files:**
- Create: `firmware_esp32/main/sg_manager_api.h`
- Create: `firmware_esp32/main/sg_manager_api.c`
- Modify: `firmware_esp32/main/app_main.c`
- Modify: `firmware_esp32/main/CMakeLists.txt`
- Modify: `firmware_esp32/main/app_config.h`
- Modify: `firmware_esp32/test_apps/e1_core/main/CMakeLists.txt`
- Modify: `firmware_esp32/test_apps/e1_core/main/test_e1_core.c`
- Modify: `host_pc/tests/test_e1_standalone_firmware.py`

**Interfaces:**
- Consumes: `sg_device_config_snapshot` and `sg_device_config_apply_profile`.
- Produces: `sg_manager_api_start()` and strict GET/PUT `/api/v1/config`.

- [ ] **Step 1: Write failing contract and parser tests**

Require fixed bounds and a pure parser:

```c
#define SG_MANAGER_BODY_MAX 1024
#define SG_MANAGER_AUTH_MAX 80

typedef enum {
    SG_MANAGER_OK = 0,
    SG_MANAGER_BAD_JSON,
    SG_MANAGER_INVALID_FIELD,
    SG_MANAGER_TOO_LARGE,
} sg_manager_parse_err_t;

sg_manager_parse_err_t sg_manager_parse_profile_patch(
    const char *json, size_t len, uint32_t *expected_revision,
    sg_profile_patch_t *patch);
bool sg_manager_token_equal(const char *expected, const char *provided);
esp_err_t sg_manager_api_start(void);
```

Unity cases reject unknown/root/profile fields, duplicate keys, wrong version,
oversized lists/text, malformed UTF-8, fractional revision, and medical/network
fields. Token tests compare equal, unequal, prefix, and length mismatch values.

- [ ] **Step 2: Run tests and verify RED**

Expected: manager module and parser do not exist.

- [ ] **Step 3: Implement strict parser and response builder**

Use cJSON but iterate every object key through allowlists before reading values. Parse into a zeroed temporary patch and return no partial result on failure. Build GET/PUT responses from a configuration snapshot and compile-time medical constants. Cap output with `SG_MANAGER_RESPONSE_MAX`; never include manager token or MQTT credentials.

Implement token comparison over the full fixed maximum without early return:

```c
bool sg_manager_token_equal(const char *expected, const char *provided)
{
    size_t a = strnlen(expected, SG_MANAGER_TOKEN_MAX + 1);
    size_t b = strnlen(provided, SG_MANAGER_TOKEN_MAX + 1);
    unsigned diff = (unsigned)(a ^ b);
    for (size_t i = 0; i < SG_MANAGER_TOKEN_MAX; ++i) {
        unsigned char x = i < a ? (unsigned char)expected[i] : 0;
        unsigned char y = i < b ? (unsigned char)provided[i] : 0;
        diff |= x ^ y;
    }
    return diff == 0 && a > 0;
}
```

- [ ] **Step 4: Implement bounded HTTP handlers**

Start `esp_http_server` on configured port with two URI handlers. Require exact `Content-Type: application/json` for PUT, parse `Authorization: Bearer ` into a fixed buffer, reject chunked/oversized requests, read exactly `content_len`, and map errors to `401/409/413/415/422/500`. Set `Cache-Control: no-store`. Log only method, status, and device ID.

- [ ] **Step 5: Integrate startup without coupling fusion**

Register `esp_http_server` in `REQUIRES`. Start the manager independently after Wi-Fi start when a token is configured. A start failure logs one bounded warning and leaves fusion/MQTT running. Stop/restart is not needed for E1 because Wi-Fi reconnect keeps the netif/server alive.

- [ ] **Step 6: Run Unity, build, flash production, and probe LAN**

After Unity passes, configure a random local management token in ignored `sdkconfig`, rebuild, clear/migrate NVS as required, and flash COM3. Probe GET with the token and verify `401` without it. Confirm serial output still shows local fusion while requests are made and contains no token/profile body.

- [ ] **Step 7: Commit Task 4**

```powershell
git add firmware_esp32/main/sg_manager_api.h firmware_esp32/main/sg_manager_api.c firmware_esp32/main/app_main.c firmware_esp32/main/CMakeLists.txt firmware_esp32/main/app_config.h firmware_esp32/test_apps/e1_core/main/CMakeLists.txt firmware_esp32/test_apps/e1_core/main/test_e1_core.c host_pc/tests/test_e1_standalone_firmware.py
git commit -m "feat(firmware): expose authenticated profile API"
```

---

### Task 5: PC Device Client and Asynchronous UI Synchronization

**Files:**
- Create: `host_pc/stroke_host/io/device_config_client.py`
- Modify: `host_pc/stroke_host/ui/config_panel.py`
- Modify: `host_pc/stroke_host/ui/main_window.py`
- Create: `host_pc/tests/test_device_config_client.py`
- Modify: `host_pc/tests/test_config_panel.py`

**Interfaces:**
- Consumes: validated private endpoint, device ID, keyring token, and `ProfileFile`.
- Produces: `DeviceConfigClient.get_config()`, `put_profile()`, and queued Qt success/failure signals.

- [ ] **Step 1: Write failing client tests with a local fake HTTP server**

Test exact request method/path/header/body, response validation, 2-second timeout, `401`, `409`, malformed JSON, device-ID mismatch, public-host refusal, and absence of token from exception messages.

Public API:

```python
class DeviceConfigError(RuntimeError):
    def __init__(self, kind: str, message: str, current: dict | None = None): ...

class DeviceConfigClient:
    def __init__(self, device_id: str, endpoint: DeviceEndpoint,
                 timeout: float = 2.0): ...
    def set_token(self, token: str) -> None: ...
    def get_config(self) -> DeviceConfigResponse: ...
    def put_profile(self, profile: UserProfile,
                    expected_revision: int) -> DeviceConfigResponse: ...
```

- [ ] **Step 2: Run client tests and verify RED**

Expected: module and classes are missing.

- [ ] **Step 3: Implement keyring and strict HTTP client**

Store tokens under service `StrokeGuard Manager` and account equal to device ID. Resolve host before every request; all returned addresses must be private/link-local/loopback for tests. Use `urllib.request`, `json.dumps(..., separators=(",", ":"))`, and Pydantic response models with `extra="forbid"`. Convert HTTP/network errors into bounded Chinese UI messages without embedding response bodies or credentials.

- [ ] **Step 4: Wire async pull/push and revision conflict handling**

Create a `QObject` worker moved to a short-lived `QThread`; it emits result/error and always quits/deletes cleanly. `ConfigPanel` stores the last device revision. Pull updates the form/YAML only after response validation. Push sends only `profile`; on `409`, fetch current config and emit a conflict signal so the panel presents explicit `使用本地` and `使用设备` commands rather than silently overwriting.

- [ ] **Step 5: Run UI/client/full tests and manual visual QA**

Run targeted and full pytest. Launch the PyQt5 application, inspect the panel at 1220x820 and 1024x720, expand YAML view, and verify text/selection/error colors are readable with no overlap. Test invalid YAML, missing token, wrong token, pull, push, and conflict actions against the fake server.

- [ ] **Step 6: Commit Task 5**

```powershell
git add host_pc/stroke_host/io/device_config_client.py host_pc/stroke_host/ui/config_panel.py host_pc/stroke_host/ui/main_window.py host_pc/tests/test_device_config_client.py host_pc/tests/test_config_panel.py
git commit -m "feat(host): synchronize profiles with the mirror"
```

---

### Task 6: LAN/VPS Integration, Documentation, and Final Verification

**Files:**
- Modify: `README.md`
- Modify: `firmware_esp32/README.md`
- Modify: `docs/e1-standalone-bringup.md`
- Create: `docs/pc-yaml-config.md`

**Interfaces:**
- Consumes: completed PC client/UI, production firmware API, LAN, and deployed VPS.
- Produces: reproducible operator workflow and final evidence.

- [ ] **Step 1: Verify device configuration end to end**

Determine the S3 private IP from router/DHCP or serial `GOT_IP` diagnostics and put only that non-secret address in local YAML. Through the PC UI: save YAML, set the masked keyring token, pull profile, modify age, push, reboot S3, and pull again. Verify the revision increments exactly once and the new profile persists.

- [ ] **Step 2: Verify safety and independence**

Attempt YAML threshold changes, public host, wrong token, stale revision, unknown JSON field, and oversized body; verify rejection. Close the PC and confirm local CSI/fusion telemetry continues. Confirm cloud advice cannot lower a local danger using Unity evidence and no PC score injection control exists.

- [ ] **Step 3: Redeploy and verify VPS/cloud path**

Deploy commit state using the existing interactive script. Verify public `/health`, numeric MQTT uplink from S3, strict storage, advice downlink, and `/devices/sg-0001/latest`. Confirm no raw media field appears and no secrets appear in deployment/backend/device logs.

- [ ] **Step 4: Write operator documentation**

Document YAML fields/bounds, local-only credential storage, form/YAML workflow, private-host restriction, conflict resolution, LAN API statuses, NVS migration, 2.4 GHz requirement, and medical read-only boundary. Include exact launch/test commands but no real addresses or credentials.

- [ ] **Step 5: Run final verification**

```powershell
cd F:\iot_design\host_pc
.venv\Scripts\python.exe -m pytest -q tests --basetemp=F:\iot_design\.pytest-native-root\pc-yaml-final -p no:cacheprovider
```

Then build production firmware, rerun the COM3 Unity suite, inspect `git diff --check`, and verify `git status` contains only the unrelated user DOCX.

- [ ] **Step 6: Commit Task 6**

```powershell
git add README.md firmware_esp32/README.md docs/e1-standalone-bringup.md docs/pc-yaml-config.md
git commit -m "docs: document PC-managed mirror profiles"
```

---

## Definition of Done

- PC form and YAML modes round-trip one strict versioned profile.
- YAML saves atomically and excludes every credential.
- The PC refuses public management destinations and stores the token in keyring.
- ESP32-S3 GET/PUT accepts only authenticated bounded profile operations.
- Revision conflict and NVS failure preserve the previous device configuration.
- Medical thresholds and veto rules remain compiled/read-only.
- Production UI has no PC-to-S3 score injection path.
- PC closed and LAN/cloud unavailable do not stop local fusion or alarms.
- COM3 reboot proves profile persistence; MQTT remains numeric-only.
- Full Python tests, Unity tests, and production firmware build pass.
- Every task has its own focused Git commit.
