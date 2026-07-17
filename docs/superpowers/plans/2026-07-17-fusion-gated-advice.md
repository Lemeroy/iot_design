# Fusion-gated AI Advice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate AI advice only for valid fusion results, invalidate it on a new screening, and expose it for at most five minutes.

**Architecture:** The MQTT bridge owns advice generation eligibility and a per-device screening generation barrier. The demo API owns presentation-time expiry so REST and WebSocket responses agree; the browser renders a clear waiting state when advice is absent.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, asyncio, paho-mqtt, vanilla JavaScript, pytest.

## Global Constraints

- `level == "insufficient"` must never invoke the advisor or publish advice.
- Advice lifetime is exactly `300` seconds from server generation time.
- Starting screening invalidates cached, pending, and in-flight prior advice.
- Numeric monitoring uplinks continue to be cached and written to InfluxDB.
- No raw audio, image, MFCC, landmark, or eye trajectory data may enter cloud payloads.

---

### Task 1: MQTT advice generation gate

**Files:**
- Modify: `cloud/backend/app/mqtt_bridge.py`
- Test: `host_pc/tests/test_e1_cloud_contract.py`

**Interfaces:**
- Produces: `MqttBridge.invalidate_advice(device_id: str) -> None`
- Consumes: `UplinkPayload.level`, `UplinkPayload.screening_stage`, cache `generation`

- [ ] Add failing tests proving insufficient uplinks do not schedule a worker, stage `1` clears old advice, and an invalidated in-flight result is neither published nor stored.
- [ ] Run `pytest host_pc/tests/test_e1_cloud_contract.py -q -p no:cacheprovider` and confirm the new assertions fail.
- [ ] Add a per-device `advice_barrier_generation`; clear advice/pending state on explicit start or transition into stage `1`; only enqueue non-insufficient uplinks.
- [ ] Before cache, publish, and Influx advice writes, reject generations older than the barrier.
- [ ] Re-run the focused test and confirm it passes.

### Task 2: Five-minute API visibility

**Files:**
- Modify: `cloud/backend/app/demo_api.py`
- Modify: `cloud/backend/app/main.py`
- Test: `host_pc/tests/test_demo_api.py`

**Interfaces:**
- Produces: `_visible_advice(cache: dict, now: float | None = None) -> DownlinkPayload | None`
- Consumes: cached `DownlinkPayload.ts`; exact maximum age `300` seconds

- [ ] Add failing REST and WebSocket-oriented tests for visible advice at age `300` and hidden advice at age `301`.
- [ ] Run `pytest host_pc/tests/test_demo_api.py -q -p no:cacheprovider` and confirm failure.
- [ ] Use `_visible_advice` in demo device serialization and legacy latest response construction.
- [ ] Make the screening endpoint call `invalidate_advice` before publishing a `start` command, while leaving `cancel` unchanged.
- [ ] Re-run focused API tests and confirm they pass.

### Task 3: Browser waiting state and regression

**Files:**
- Modify: `cloud/backend/app/static/demo/app.js`
- Test: `host_pc/tests/test_demo_web.py`

**Interfaces:**
- Consumes: nullable `DemoDeviceResp.advice`
- Produces: waiting copy `等待形成新的融合评分`

- [ ] Add a failing source contract assertion for the waiting copy and clearing source/time when advice is absent.
- [ ] Replace the old generic empty copy while preserving valid advice rendering.
- [ ] Run `pytest host_pc/tests/test_demo_web.py -q -p no:cacheprovider`.
- [ ] Run all cloud contract/API/web tests with `PYTHONPATH=F:\iot_design\host_pc`.
- [ ] Commit, push, deploy the changed cloud files, restart native services, and verify `/health` plus `/demo/` externally.
