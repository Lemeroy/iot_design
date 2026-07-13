# StrokeGuard Demo Device Maintenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current all-purpose desktop demo with a focused real-device VPS monitor plus an isolated ESP-IDF/YAML/serial maintenance workspace.

**Architecture:** A small Python service layer owns cloud sessions, deployment configuration, and controlled ESP-IDF subprocesses. A new PyQt5 shell presents a quiet read-only demo dashboard by default and opens maintenance tools in a separate page; neither layer imports the legacy perception/simulation pipeline. The EXE uses the installed ESP-IDF v5.5.3 and never bundles credentials or simulated data.

**Tech Stack:** Python 3.11+, PyQt5, httpx, PyYAML, pyserial, ESP-IDF v5.5.3, pytest, pytest-qt, PyInstaller.

## Global Constraints

- Default cloud URL is configurable and the default device is `sg-0001`.
- Only real VPS telemetry and completed LLM advice may appear; no simulated fallback exists.
- User-visible failure labels are exactly `云端不可达`, `登录失效`, `设备离线`, and `数据未接入`; implementations must not collapse them into one generic error.
- Raw audio/video, MFCC, landmarks, ROI, credentials, and unrestricted logs never enter cloud/UI release output.
- Target firmware is ESP32-S3-WROOM-1 N16R8 with ESP-IDF v5.5.3.
- GC2145 and NMO432 stay disabled until complete user-confirmed GPIO mappings pass validation.
- NMO432 is 3.3 V I2S with SCK/BCLK, WS/LRCLK, SD/DIN, and explicit left/right channel selection.
- Every destructive erase requires an explicit checkbox plus confirmation naming the COM port.
- Each completed task receives a focused commit and push; no secrets may be committed.

## File Structure

- Create `host_pc/stroke_host/demo/cloud_client.py`: authenticated VPS session and normalized monitor states.
- Create `host_pc/stroke_host/deployment/schema.py`: deployment YAML models, environment expansion, validation, and redaction.
- Create `host_pc/stroke_host/deployment/idf_runner.py`: ESP-IDF discovery, safe command construction, staged subprocess execution, cancellation.
- Create `host_pc/stroke_host/deployment/serial_monitor.py`: COM discovery and stoppable text monitoring.
- Create `host_pc/stroke_host/demo/window.py`: dual-page PyQt5 application and worker wiring.
- Modify `host_pc/stroke_host/demo_entry.py`: launch only the new demo application.
- Create `host_pc/config/device-deployment.example.yaml`: credential-free NMO432/GC2145 template.
- Modify `.gitignore`: exclude local deployment YAML, generated sdkconfig overlay, logs, and environment files.
- Modify `host_pc/pyproject.toml`: runtime/test dependencies required by the focused app.
- Modify `scripts/build_release.ps1`: collect only required modules/assets and validate release exclusions.
- Modify `README.md`, `host_pc/README.md`, `docs/developer-handoff.md`: launch, maintenance, and safety instructions.
- Create tests under `host_pc/tests/` matching each service and UI boundary.

---

### Task 1: Real VPS Monitor Client

**Files:**
- Create: `host_pc/stroke_host/demo/__init__.py`
- Create: `host_pc/stroke_host/demo/cloud_client.py`
- Test: `host_pc/tests/test_desktop_cloud_client.py`

**Interfaces:**
- Produces: `CloudClient(base_url: str, timeout_seconds: float = 5.0)`.
- Produces: `login(username: str, password: str) -> None`, `connect(device_id: str) -> None`, `fetch_device() -> DeviceSnapshot`, `logout() -> None`.
- Produces: `CloudUnavailable`, `AuthenticationRequired`, `DeviceOffline`, and immutable `DeviceSnapshot`/`AdviceSnapshot` value objects.

- [ ] **Step 1: Write failing contract tests**

  Test real `httpx.MockTransport` request/response handling for successful login/connect/fetch, `401`, timeout, offline `404/409`, `null` modalities, and advice timestamps. Assert the returned object never synthesizes missing scores.

- [ ] **Step 2: Verify RED**

  Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_desktop_cloud_client.py`
  Expected: collection fails because `stroke_host.demo.cloud_client` does not exist.

- [ ] **Step 3: Implement the minimal cloud client**

  Use one `httpx.Client` with cookie persistence. Normalize only the existing `/demo/api/login`, `/connect`, `/device`, and `/logout` payloads. Map transport failures and HTTP states to the four explicit application states without retaining passwords.

- [ ] **Step 4: Verify GREEN and regression**

  Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_desktop_cloud_client.py host_pc\tests\test_demo_api.py`
  Expected: all selected tests pass.

- [ ] **Step 5: Commit and push**

  Commit: `feat(demo): add real VPS monitor client`

### Task 2: Deployment YAML Contract

**Files:**
- Create: `host_pc/stroke_host/deployment/__init__.py`
- Create: `host_pc/stroke_host/deployment/schema.py`
- Create: `host_pc/config/device-deployment.example.yaml`
- Modify: `.gitignore`
- Test: `host_pc/tests/test_deployment_schema.py`

**Interfaces:**
- Produces: `load_deployment(path: Path, environ: Mapping[str, str]) -> DeploymentConfig`.
- Produces: `validate_deployment(data: object, environ: Mapping[str, str]) -> DeploymentConfig`.
- Produces: `redact_text(text: str, config: DeploymentConfig) -> str`.
- `DeploymentConfig` exposes a whitelist mapping to current `CONFIG_STROKEGUARD_*` keys; it never exposes a shell command string.

- [ ] **Step 1: Write failing YAML validation tests**

  Cover the approved schema, environment substitution, unknown keys, malformed IDs/URIs, missing secrets, unsupported hardware models, incomplete GC2145/NMO432 pins, duplicate GPIOs, invalid channel, and redaction of every secret.

- [ ] **Step 2: Verify RED**

  Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_deployment_schema.py`
  Expected: collection fails because the deployment package is absent.

- [ ] **Step 3: Implement strict parsing and template**

  Parse with `yaml.safe_load`; reject unknown fields. Resolve only `${UPPER_CASE_NAME}` placeholders from the supplied environment. Keep camera/microphone disabled with empty pins in the tracked example. Map NMO432 pins to the existing audio Kconfig keys while presenting the corrected module name in YAML/UI.

- [ ] **Step 4: Verify GREEN**

  Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_deployment_schema.py`
  Expected: all tests pass and the fixture output contains no literal secret.

- [ ] **Step 5: Commit and push**

  Commit: `feat(device): add secure deployment YAML contract`

### Task 3: Controlled ESP-IDF and Serial Services

**Files:**
- Create: `host_pc/stroke_host/deployment/idf_runner.py`
- Create: `host_pc/stroke_host/deployment/serial_monitor.py`
- Test: `host_pc/tests/test_idf_runner.py`
- Test: `host_pc/tests/test_serial_monitor.py`

**Interfaces:**
- Produces: `IdfInstallation.discover(preferred: Path | None) -> IdfInstallation` with exact v5.5.3 validation.
- Produces: `IdfRunner.prepare(config)`, `build()`, `erase(port, confirmed)`, `flash(port)`, `cancel()` and stage events.
- Produces: `list_serial_ports() -> list[SerialPortInfo]` and `SerialMonitor.start(port, baud, on_line)`, `stop()`.

- [ ] **Step 1: Write failing safe-runner tests**

  Inject a fake process launcher and assert argument arrays, stage transitions, cancellation, non-zero exit behavior, no free-form shell invocation, no secrets in events, confirmation enforcement, and generated config cleanup. Test serial enumeration and port release with an injected serial factory.

- [ ] **Step 2: Verify RED**

  Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_idf_runner.py host_pc\tests\test_serial_monitor.py`
  Expected: collection fails because runner modules do not exist.

- [ ] **Step 3: Implement staged services**

  Launch the IDF export environment through a fixed PowerShell script path and pass commands as argument arrays. Generate a local ignored sdkconfig defaults overlay from the YAML whitelist. Stream decoded output through `redact_text`; terminate child processes on cancellation and always close serial handles.

- [ ] **Step 4: Verify GREEN**

  Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_idf_runner.py host_pc\tests\test_serial_monitor.py`
  Expected: all tests pass.

- [ ] **Step 5: Commit and push**

  Commit: `feat(device): add controlled IDF flashing services`

### Task 4: Focused Dual-Mode PyQt Application

**Files:**
- Create: `host_pc/stroke_host/demo/window.py`
- Modify: `host_pc/stroke_host/demo_entry.py`
- Modify: `host_pc/stroke_host/ui/theme.py`
- Test: `host_pc/tests/test_focused_demo_window.py`
- Test: `host_pc/tests/test_release_packaging.py`

**Interfaces:**
- Consumes: `CloudClient`, `DeploymentConfig`, `IdfRunner`, and `SerialMonitor` from Tasks 1-3.
- Produces: `DemoWindow` and `main()`; `demo_entry.py` imports only `stroke_host.demo.window.main`.

- [ ] **Step 1: Write failing UI structure tests**

  Use `pytest-qt` to assert login-first behavior, automatic `sg-0001` connection, six metric values, explicit cloud/auth/device/missing-data states, stale timestamp, advice panel, maintenance navigation, destructive confirmation, disabled conflicting actions, and cleanup on close. Assert no simulation/source/FPS/record/perception controls exist.

- [ ] **Step 2: Verify RED**

  Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_focused_demo_window.py host_pc\tests\test_release_packaging.py`
  Expected: tests fail because the focused window is absent and entry point still imports the legacy window.

- [ ] **Step 3: Build the presentation dashboard**

  Implement a restrained clinical operations aesthetic: off-white content surface, charcoal text, green/amber/red only for state, compact status dots, large readable metric numerals, and one advice region. Poll every five seconds on a worker thread; never block the Qt event loop. Keep the last snapshot visible but visibly stale after failure.

- [ ] **Step 4: Build the maintenance page**

  Add structured YAML fields, masked secret status, COM/IDF selectors, five-stage progress, explicit erase acknowledgement, start/cancel controls, and a readable redacted log. Hardware toggles reveal GPIO fields only when enabled; incomplete pin sets block execution with field-level errors.

- [ ] **Step 5: Verify GREEN and visual behavior**

  Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_focused_demo_window.py host_pc\tests\test_release_packaging.py host_pc\tests\test_ui_theme.py`
  Expected: all selected tests pass.

- [ ] **Step 6: Commit and push**

  Commit: `feat(demo): replace desktop tool with focused presentation app`

### Task 5: Documentation and Release Packaging

**Files:**
- Modify: `host_pc/pyproject.toml`
- Modify: `scripts/build_release.ps1`
- Modify: `README.md`
- Modify: `host_pc/README.md`
- Modify: `docs/developer-handoff.md`
- Modify: `host_pc/tests/test_demo_deploy_contract.py`
- Modify: `host_pc/tests/test_release_packaging.py`

**Interfaces:**
- Produces: rebuilt `dist/StrokeGuard-Demo.exe` and `dist/StrokeGuard-Developer-Handoff.zip`.

- [ ] **Step 1: Write failing release contract tests**

  Require the new entry point/modules/example YAML in handoff, forbid local deployment files/generated sdkconfig/secrets/logs, and assert the release script excludes legacy heavyweight perception dependencies from the demo entry graph where PyInstaller permits.

- [ ] **Step 2: Verify RED**

  Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_demo_deploy_contract.py host_pc\tests\test_release_packaging.py`
  Expected: at least one new release assertion fails.

- [ ] **Step 3: Update dependencies, packaging, and operator docs**

  Document prerequisites, login, default real-device behavior, YAML environment variables, IDF discovery, COM workflow, erase warning, NMO432 wiring labels, and the limitation that GC2145/NMO432 drivers remain pending until GPIOs and drivers are completed.

- [ ] **Step 4: Run full verification**

  Run: `host_pc\.venv\Scripts\python.exe -m pytest -q`
  Expected: all tests pass with zero failures.

- [ ] **Step 5: Build artifacts**

  Run: `powershell -ExecutionPolicy Bypass -File scripts\build_release.ps1`
  Expected: exactly `StrokeGuard-Demo.exe` and `StrokeGuard-Developer-Handoff.zip` in `dist`, each with SHA-256 output.

- [ ] **Step 6: Smoke-test EXE**

  Launch the EXE, verify the login window appears, confirm no simulation controls, close it, and verify no orphan process remains. Open the ZIP and repeat the forbidden-entry scan.

- [ ] **Step 7: Commit and push**

  Commit: `feat(release): deliver focused StrokeGuard demo app`

### Task 6: Real Hardware Acceptance

**Files:**
- Create: `docs/demo-acceptance-checklist.md`
- Update tests only if a real-device defect is reproduced.

**Interfaces:**
- Consumes: installed EXE, VPS, `sg-0001`, COM port, N16R8 board, approved local deployment YAML.
- Produces: evidence-backed acceptance record without invented accuracy claims.

- [ ] **Step 1: Run cloud acceptance**

  Log in, verify `sg-0001` online, confirm changing real CSI, `null` F/S/T/E shown as “未接入”, S3 level preserved, and completed Doubao advice shown with source/time.

- [ ] **Step 2: Run failure acceptance**

  Disconnect network and then stop S3 uplink separately. Verify the UI distinguishes cloud unreachable from device offline and never creates replacement scores.

- [ ] **Step 3: Run maintenance dry run**

  Load the credential-resolved local YAML, detect the actual COM port and IDF v5.5.3, validate N16R8, and build without enabling unconfirmed GC2145/NMO432 pins.

- [ ] **Step 4: Run destructive flow only with user confirmation**

  After explicit approval, erase, flash, monitor boot, and verify the board resumes independent MQTT uplink. If approval is not given, record erase/flash as not executed rather than claiming success.

- [ ] **Step 5: Record artifact hashes and commit**

  Commit: `test(demo): record focused app acceptance`
