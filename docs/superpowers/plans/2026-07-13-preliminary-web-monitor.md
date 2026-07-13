# Preliminary Web Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add a single-account external web page that connects to an MQTT-observed S3 by device ID and polls its numeric monitoring data and LLM advice every five seconds.

**Architecture:** FastAPI keeps the existing MQTT bridge as the source of truth. A stateless HMAC-signed demo session stores the selected device ID; no database, ownership model, WebSocket, history query, or remote configuration is added. Static HTML/CSS/JavaScript uses authenticated REST polling.

**Tech Stack:** FastAPI, Pydantic v2, Python standard-library scrypt/HMAC, paho-mqtt, vanilla HTML/CSS/JavaScript, pytest.

## Global Constraints

- Only numeric scores, device level/reasons, online timestamps, and LLM advice may reach the page.
- Raw image, audio, MFCC, landmarks, ROI, profile details, Wi-Fi/MQTT credentials, and API keys must never enter the demo API or logs.
- Missing F/S/T/E stays `null` and renders as `未接入`; no default score 80.
- Device online status uses VPS receive time and a fixed 30-second threshold.
- Polling interval is exactly five seconds.
- The page is read-only and cannot change S3 configuration, profile, fusion, or alert rules.
- S3 level remains authoritative; advice cannot replace it.
- Existing `/health`, MQTT, InfluxDB, LLM advice, and S3 downlink behavior must remain.
- Plain HTTP is allowed only with `SG_ALLOW_INSECURE_HTTP=1`; production cookies otherwise require HTTPS.

---

### Task 1: Single Demo Account and Signed Session

**Files:**
- Create: `cloud/backend/app/demo_auth.py`
- Create: `host_pc/tests/test_demo_auth.py`

**Interfaces:**
- Produces: `DemoAuth.from_env()`, `verify_login()`, `issue_session(device_id=None)`, and `verify_session()`.

- [ ] Write failing tests for missing configuration, successful/failed login, expiry, signature tampering, device selection, secure cookie mode, and password environment cleanup.
- [ ] Run `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_demo_auth.py` and verify missing-module RED.
- [ ] Implement scrypt password verification and HMAC-SHA256 URL-safe session tokens. Remove `SG_DEMO_PASSWORD` in a top-level `finally` during initialization.
- [ ] Run the focused tests warning-free.
- [ ] Commit with `feat(cloud): add preliminary demo session`.

---

### Task 2: MQTT Device Connection and Read-Only API

**Files:**
- Create: `cloud/backend/app/demo_api.py`
- Create: `host_pc/tests/test_demo_api.py`
- Modify: `cloud/backend/app/mqtt_bridge.py`
- Modify: `cloud/backend/app/main.py`
- Modify: `cloud/backend/app/schemas.py`

**Interfaces:**
- Consumes: `DemoAuth` and `MqttBridge.latest`.
- Produces: `/demo/api/login`, `/logout`, `/session`, `/connect`, `/disconnect`, and `/device`.

- [ ] Write failing tests for 401 access, generic login failure, valid login, invalid device IDs, unknown/offline devices, successful connect, disconnect, and privacy-safe device responses.
- [ ] Add a bridge test proving `received_at` is set only after JSON/schema/topic-device validation.
- [ ] Implement API dependencies and store VPS receipt time in the bridge cache. Use receipt time, not S3 timestamp, for the 30-second online decision.
- [ ] Verify advice text/source/time and nullable scores are returned without profile/media fields.
- [ ] Run focused cloud tests and the full `host_pc/tests` suite warning-free.
- [ ] Commit with `feat(cloud): connect demo page to mqtt devices`.

---

### Task 3: Responsive Preliminary Dashboard

**Files:**
- Create: `cloud/backend/app/demo_web.py`
- Create: `cloud/backend/app/static/demo/index.html`
- Create: `cloud/backend/app/static/demo/app.css`
- Create: `cloud/backend/app/static/demo/app.js`
- Create: `host_pc/tests/test_demo_web.py`
- Modify: `cloud/backend/app/main.py`

**Interfaces:**
- Consumes: Task 2 REST API.
- Produces: `/demo` and local static assets.

- [ ] Write failing asset-contract tests for five-second polling, no simulated 80, `未接入`, danger `立即拨打 120`, login/connect/monitor states, logout, and no external media URLs.
- [ ] Implement a quiet medical-monitor UI with stable score tiles, clear online/offline state, connection form, reasons, and advice panel.
- [ ] Keep all controls feature-complete: login, connect, refresh, disconnect, logout, and automatic polling.
- [ ] Run unit tests, start FastAPI locally with fake cache data, and inspect Playwright screenshots at 1440x900, 1024x768, and 390x844 for overlap and text fit.
- [ ] Commit with `feat(web): add preliminary remote monitor`.

---

### Task 4: Deployment and S3 Acceptance

**Files:**
- Modify: `cloud/.env.example`
- Modify: `cloud/native/start.sh`
- Modify: `cloud/README.md`
- Modify: `README.md`
- Modify: `scripts/package_release.ps1`
- Create: `host_pc/tests/test_demo_deploy_contract.py`

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: configured VPS demo and updated final artifacts.

- [ ] Add deployment-contract tests for the four demo environment settings and no credential echo.
- [ ] Export demo settings in `native/start.sh`; auth remains disabled without complete settings so the existing cloud chain still starts.
- [ ] Run the full local suite warning-free and scan tracked changes for credentials/raw-media fields.
- [ ] Deploy to the VPS and verify `/health`, login, device connection, polling, advice, and 30-second offline transition.
- [ ] Power `sg-0001` without PC USB and confirm the page shows real CSI, missing F/S/T/E, device level, and Doubao advice.
- [ ] Rebuild `StrokeGuard-Demo.exe` and `StrokeGuard-Developer-Handoff.zip`; verify secret/cache exclusions and artifact launch.
- [ ] Commit and push with `feat(release): deliver preliminary web monitor`.
