# PushPlus Self Alert Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send bounded, privacy-preserving PushPlus WeChat alerts for confirmed warning and immediate danger results during an active guided screening.

**Architecture:** A thread-safe per-device coordinator owns screening alert state and emits one-shot alert decisions. The MQTT bridge turns those decisions into level-matched advice work, then submits PushPlus HTTPS delivery outside the MQTT callback thread. A focused notifier owns request formatting, response handling, rate-limit shutdown, and secret-free logging.

**Tech Stack:** Python 3.10, FastAPI, paho-mqtt, Pydantic 2, standard-library `urllib.request`, pytest, PowerShell 5.1, Bash.

## Global Constraints

- Raw audio, video, MFCC, landmarks, eye trajectories, and user profile fields must never enter PushPlus payloads.
- Alerts require an active screening; warning requires three consecutive uplinks; danger is immediate.
- Each screening allows at most one warning attempt and one danger attempt.
- PushPlus failures must not block MQTT, InfluxDB, web monitoring, or device-local alerts.
- PushPlus code `900` disables attempts until backend restart.
- Secrets remain only in untracked `cloud/.env` and must not appear in logs or command arguments.

---

### Task 1: Screening Alert State Machine

**Files:**
- Create: `cloud/backend/app/alert_policy.py`
- Test: `host_pc/tests/test_pushplus_alerts.py`

**Interfaces:**
- Produces: `AlertCoordinator.start(device_id)`, `cancel(device_id)`, `observe(device_id, level) -> str | None`, and `mark_dispatched(device_id, level)`.

- [ ] **Step 1: Write failing state-transition tests**

Cover inactive results, three consecutive warnings, reset by `normal` and `insufficient`, immediate danger, warning-to-danger escalation, duplicate suppression, new-session reset, and per-device isolation.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest host_pc/tests/test_pushplus_alerts.py -q`
Expected: FAIL because `cloud.backend.app.alert_policy` does not exist.

- [ ] **Step 3: Implement the minimal coordinator**

Use a `threading.RLock`, a private `dict[str, AlertSession]`, and a dataclass containing `active`, `warning_count`, `warning_dispatched`, `danger_dispatched`, and `pending_level`. `observe` returns `warning` only at count three and `danger` on the first danger; pending or dispatched levels return `None`.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest host_pc/tests/test_pushplus_alerts.py -q`
Expected: all state-machine tests PASS.

### Task 2: PushPlus HTTPS Notifier

**Files:**
- Create: `cloud/backend/app/pushplus.py`
- Modify: `host_pc/tests/test_pushplus_alerts.py`

**Interfaces:**
- Produces: `PushPlusNotifier.from_env()`, `enabled`, and `send(device_id, uplink, advice_text) -> bool`.
- Uses: `POST https://www.pushplus.plus/send`, `template=markdown`, `channel=wechat`, with no `topic` or `to`.

- [ ] **Step 1: Write failing notifier tests**

Inject a fake opener and assert request JSON contains only token, title, content, template, and channel; content contains device/time/F/S/T/E/CSI/final/level/advice/safety wording but excludes profile values and raw-data field names. Test disabled mode, timeout, malformed responses, code `903`, code `905`, code `900`, and secret-free logs.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest host_pc/tests/test_pushplus_alerts.py -q`
Expected: notifier tests FAIL because `PushPlusNotifier` is missing.

- [ ] **Step 3: Implement bounded delivery**

Serialize UTF-8 JSON, use an injected opener with an 8-second timeout, accept only response code `200`, and set a process-lifetime disabled flag after code `900`. Log device ID and provider code only.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest host_pc/tests/test_pushplus_alerts.py -q`
Expected: all notifier tests PASS.

### Task 3: MQTT and Advice Integration

**Files:**
- Modify: `cloud/backend/app/mqtt_bridge.py`
- Modify: `cloud/backend/app/main.py`
- Modify: `cloud/backend/app/demo_api.py`
- Modify: `host_pc/tests/test_e1_cloud_contract.py`
- Modify: `host_pc/tests/test_demo_api.py`
- Modify: `host_pc/tests/test_pushplus_alerts.py`

**Interfaces:**
- `MqttBridge(..., pushplus: PushPlusNotifier | None = None)` owns one `AlertCoordinator`.
- Accepted web `start` resets the coordinator; accepted `cancel` deactivates it.
- Device transition to stage `1` resets it; stage `7` deactivates it; stage `6` remains active.
- An alert decision sets a force-advice level. The advice worker bypasses 300-second retention only for that matching level, publishes downlink first, marks the alert dispatched, then schedules `pushplus.send(...)` via `asyncio.to_thread`.

- [ ] **Step 1: Write failing bridge tests**

Assert no alert outside a session, one warning only after three consecutive warning uplinks, immediate danger, warning-to-danger push, stage/new-start reset, cancel/stage-7 deactivation, no duplicate LLM work while counting, forced danger advice despite retained warning advice, and notifier failure isolation.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest host_pc/tests/test_pushplus_alerts.py host_pc/tests/test_e1_cloud_contract.py host_pc/tests/test_demo_api.py -q`
Expected: new integration tests FAIL on missing bridge behavior.

- [ ] **Step 3: Implement minimal integration**

Observe alert state while caching valid uplinks. Schedule advice only under existing eligibility rules, except set `force_advice_level` when the coordinator emits a decision. Accept generated advice only if generation barriers still permit it. After MQTT downlink acceptance, atomically consume the matching force level, mark it dispatched, and schedule PushPlus without awaiting it in the MQTT callback.

- [ ] **Step 4: Verify GREEN and regressions**

Run: `python -m pytest host_pc/tests/test_pushplus_alerts.py host_pc/tests/test_e1_cloud_contract.py host_pc/tests/test_demo_api.py -q`
Expected: all selected tests PASS with no coroutine warnings.

### Task 4: Secure Configuration and Native Deployment

**Files:**
- Modify: `cloud/.env.example`
- Modify: `cloud/native/start.sh`
- Create: `scripts/configure_pushplus_interactive.ps1`
- Create: `host_pc/tests/test_pushplus_deploy_contract.py`

**Interfaces:**
- Environment: `PUSHPLUS_ENABLED`, `PUSHPLUS_TOKEN`, optional `PUSHPLUS_DEVICE_NAME`.
- Configurator reads Token using `Read-Host -AsSecureString`, updates `cloud/.env` atomically, never prints the secret, and remains compatible with Windows PowerShell 5.1.

- [ ] **Step 1: Write failing deployment contract tests**

Assert the env template documents all settings, native startup exports them, the configurator uses masked input and atomic UTF-8 writing, and the repository ignores `cloud/.env`.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest host_pc/tests/test_pushplus_deploy_contract.py -q`
Expected: FAIL because PushPlus configuration is absent.

- [ ] **Step 3: Implement configuration plumbing**

Add disabled-by-default template entries, export values in `start_backend`, and implement the masked configurator using `SecureStringToBSTR` plus `RandomNumberGenerator.Create()`-compatible APIs only.

- [ ] **Step 4: Verify GREEN and full cloud suite**

Run: `python -m pytest host_pc/tests/test_pushplus_deploy_contract.py host_pc/tests/test_cloud_native_contract.py host_pc/tests/test_cloud_deploy_contract.py -q`
Expected: all selected tests PASS.

- [ ] **Step 5: Commit and push**

Run: `git add cloud host_pc/tests scripts docs/superpowers/plans/2026-07-17-pushplus-self-alert.md && git commit -m "feat(cloud): add PushPlus screening alerts" && git push origin codex/preliminary-demo`
Expected: commit and push succeed without adding `cloud/.env`, caches, logs, or firmware build output.

## Deployment Acceptance

1. Run `powershell -ExecutionPolicy Bypass -File scripts/configure_pushplus_interactive.ps1` and enter the token only in the masked prompt.
2. Deploy with `scripts/deploy_cloud_native_interactive.ps1` and verify `/health` remains healthy.
3. After explicit user approval, issue one PushPlus test notification.
4. Start a real guided screening and verify three warnings produce one warning message, a later danger produces one additional message, and local monitoring remains live if PushPlus is unreachable.
