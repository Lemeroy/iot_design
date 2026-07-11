# StrokeGuard Cloud Native Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Run EMQX, InfluxDB, and the existing FastAPI backend inside the restricted Ubuntu cloud container without Docker or systemd.

**Architecture:** Project-local shell scripts install pinned vendor runtimes under `cloud/native/runtime`, keep mutable data under `cloud/native/state`, and manage processes with validated PID files. A PowerShell uploader deploys the existing `cloud/` tree and invokes install, start, and health checks over interactive SSH.

**Tech Stack:** Bash, PowerShell 5.1, EMQX 5.7.2, InfluxDB 2.7.11, Python 3 venv, FastAPI, pytest.

## Global Constraints

- Raw audio and video remain local; cloud payloads contain only numeric scores and profiles.
- The service is a risk提示/就医提醒 system, not a diagnostic device.
- Do not require Docker, systemd, `CAP_SYS_ADMIN`, or `CAP_NET_ADMIN`.
- Do not print passwords, tokens, or API keys.
- Bind InfluxDB to `127.0.0.1:8086`; expose MQTT `1883`, Dashboard `18083`, and FastAPI `8000`.
- A missing LLM API key must retain the existing fallback advice path.

---

### Task 1: Native Deployment Contract

**Files:**
- Create: `host_pc/tests/test_cloud_native_contract.py`
- Modify: `cloud/.gitignore`

**Interfaces:**
- Produces: repository-level assertions for generated directories, secret handling, native port bindings, and script inventory.

- [x] Write failing tests asserting the five native shell scripts and the PowerShell deploy helper exist.
- [x] Assert `runtime/`, `state/`, `logs/`, and `run/` are ignored.
- [x] Assert scripts load `cloud/.env` without embedding credential values.
- [x] Run `python -m pytest tests/test_cloud_native_contract.py -q` and confirm failure because files are absent.
- [x] Add ignore entries and minimal script files, then confirm the contract tests pass.

### Task 2: Installer and Shared Shell Library

**Files:**
- Create: `cloud/native/lib.sh`
- Create: `cloud/native/install.sh`
- Test: `host_pc/tests/test_cloud_native_contract.py`

**Interfaces:**
- Produces: `native_root`, `cloud_root`, `load_env`, `require_env`, `is_running`, `wait_http`, and pinned runtime installation.

- [x] Add failing assertions for EMQX `5.7.2`, InfluxDB `2.7.11`, SHA256 verification, Python venv creation, and platform checks.
- [x] Run the focused test and confirm expected failure.
- [x] Implement atomic downloads into `native/downloads`, checksum validation, archive extraction, and venv dependency installation.
- [x] Run `bash -n` for both scripts and the focused pytest file.

### Task 3: Lifecycle and Initialization

**Files:**
- Create: `cloud/native/start.sh`
- Create: `cloud/native/stop.sh`
- Create: `cloud/native/status.sh`
- Create: `cloud/native/healthcheck.sh`
- Create: `cloud/native/config/emqx-base.hocon.template`
- Test: `host_pc/tests/test_cloud_native_contract.py`

**Interfaces:**
- Consumes: helpers from `lib.sh` and credentials from `cloud/.env`.
- Produces: idempotent service lifecycle, Influx setup, EMQX user bootstrap, and `/health` validation.

- [x] Add failing tests for startup order, loopback Influx binding, local backend endpoints, PID validation, and bounded health polling.
- [x] Implement Influx startup and `/api/v2/setup` initialization without exposing the token.
- [x] Implement EMQX config generation with anonymous access disabled and API-based MQTT user creation.
- [x] Implement FastAPI startup with `MQTT_HOST=127.0.0.1` and `INFLUX_URL=http://127.0.0.1:8086`.
- [x] Implement reverse-order shutdown and machine-readable health checks.
- [x] Run shell syntax checks and focused tests.

### Task 4: Interactive Native Deployment

**Files:**
- Create: `scripts/deploy_cloud_native_interactive.ps1`
- Modify: `cloud/README.md`
- Test: `host_pc/tests/test_cloud_native_contract.py`

**Interfaces:**
- Produces: upload, timestamped remote backup, install, start, status, and health invocation through SSH port 23.

- [x] Add failing tests asserting the helper targets `/opt/strokeguard/cloud`, never embeds a password, and runs native health checks.
- [x] Implement the interactive uploader with transcript logging and archive cleanup.
- [x] Add native deployment and restart instructions to the README.
- [x] Parse the PowerShell file with the PowerShell AST and run focused tests.

### Task 5: Verification and Remote Deployment

**Files:**
- Verify all changed files.

**Interfaces:**
- Consumes: completed native deployment scripts.
- Produces: running remote EMQX, InfluxDB, and FastAPI services.

- [x] Run the full host test suite with `QT_QPA_PLATFORM=offscreen`.
- [x] Run all local Bash syntax checks and PowerShell AST checks.
- [x] Upload and execute the native deployment helper; enter the SSH password only in the interactive window.
- [x] Verify remote process state and `curl http://127.0.0.1:8000/health`.
- [x] Verify external `http://106.75.229.61:8000/health`, or document the cloud port-mapping blocker and verify through the SSH tunnel.
- [x] Post a numeric MQTT uplink and verify a downlink response without any raw media fields.
