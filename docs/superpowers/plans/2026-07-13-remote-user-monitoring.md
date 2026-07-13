# Remote User Monitoring Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an authenticated multi-user web and PC monitoring platform in which administrators create users, users pair one or more ESP32-S3 mirrors, and each user can remotely view only their own live and historical numeric health data.

**Architecture:** Extend the existing FastAPI process with a focused SQLite repository, session authentication, ownership-aware REST APIs, and a WebSocket snapshot hub. The MQTT bridge remains the only S3 ingestion path and writes numeric records to InfluxDB while registering devices and broadcasting authorized snapshots. Static HTML/CSS/JavaScript is served by FastAPI; the PyQt5 client consumes the same REST and WebSocket contracts.

**Tech Stack:** Python 3.10+, FastAPI, stdlib `sqlite3`, Argon2id via `argon2-cffi`, Pydantic v2, paho-mqtt, InfluxDB 2.x, vanilla HTML/CSS/JavaScript, Chart.js vendored locally, PyQt5, `websocket-client`, pytest.

## Global Constraints

- Raw image, audio, MFCC, landmarks, ROI, and reconstructable biometric data must never enter SQLite, InfluxDB, REST, WebSocket, logs, or cloud storage.
- Existing deterministic fusion, veto rules, and S3 alert level remain authoritative; LLM advice cannot reduce or replace the device level.
- A normal user can read only devices where `devices.owner_user_id == current_user.id`.
- One user may own multiple devices; one device may have at most one owner.
- Pairing codes contain exactly six decimal digits, expire after 10 minutes, are single-use, and are stored only as keyed hashes.
- WebSocket loss falls back to five-second polling and polling stops after WebSocket recovery.
- History ranges are exactly `1h`, `24h`, and `7d`; responses contain no more than 500 points.
- Missing F/S/T/E values remain `null` and display as `未接入`; no simulated score may replace a missing device value.
- Public authentication requires HTTPS/WSS. Plain HTTP is allowed only when `SG_ALLOW_INSECURE_HTTP=1` is explicitly set for local tests.
- Credentials and tokens stay in VPS `.env`, HTTP-only cookies, or the PC operating-system keyring; never in Git, YAML, query strings, or logs.
- Each task uses TDD: add a failing test, observe the expected failure, implement the minimum behavior, run focused and affected suites, then make one focused commit.

---

## File Structure

### Cloud backend

- Create `cloud/backend/app/auth_store.py`: SQLite schema, migrations, users, sessions, devices, and pairing transactions.
- Create `cloud/backend/app/security.py`: Argon2 password hashing, random session tokens, keyed pairing-code hashes, and bounded authentication errors.
- Create `cloud/backend/app/auth_api.py`: login, logout, current-user dependency, and admin user endpoints.
- Create `cloud/backend/app/device_api.py`: ownership-filtered device, latest, history, pairing, and admin ownership endpoints.
- Create `cloud/backend/app/realtime.py`: thread-safe snapshot cache and ownership-aware WebSocket fan-out.
- Create `cloud/backend/app/web.py`: static-page routes and cache headers.
- Create `cloud/backend/app/static/`: login, user dashboard, device detail, pairing page, admin page, CSS, JavaScript, and vendored Chart.js.
- Modify `cloud/backend/app/main.py`: construct dependencies in lifespan and register routers/static assets.
- Modify `cloud/backend/app/mqtt_bridge.py`: register devices, update last-seen, and publish snapshots to the realtime hub.
- Modify `cloud/backend/app/db_influx.py`: bounded history query API.
- Modify `cloud/backend/app/schemas.py`: public user/device/history/WebSocket response models.
- Modify `cloud/backend/requirements.txt`: add `argon2-cffi` and test-compatible HTTP/WebSocket dependencies.

### PC client

- Create `host_pc/stroke_host/io/remote_monitor_client.py`: HTTPS login, keyring token storage, REST access, and WebSocket reconnect.
- Create `host_pc/stroke_host/ui/remote_monitor_panel.py`: login, device list, connection state, and remote snapshot signals.
- Modify `host_pc/stroke_host/ui/main_window.py`: add a remote-monitor tab/data source without changing LAN YAML configuration.
- Modify `host_pc/pyproject.toml`: add `websocket-client`.

### Deployment and tests

- Create `host_pc/tests/test_cloud_auth_store.py`.
- Create `host_pc/tests/test_cloud_auth_api.py`.
- Create `host_pc/tests/test_cloud_device_api.py`.
- Create `host_pc/tests/test_cloud_realtime.py`.
- Create `host_pc/tests/test_cloud_history.py`.
- Create `host_pc/tests/test_remote_web_assets.py`.
- Create `host_pc/tests/test_remote_monitor_client.py`.
- Create `cloud/native/e2e_remote_monitor.py`.
- Modify `cloud/.env.example`, `cloud/native/start.sh`, `cloud/native/deploy_remote.sh`, `cloud/README.md`, and root `README.md`.

---

### Task 1: SQLite Repository and Security Primitives

**Files:**
- Create: `cloud/backend/app/auth_store.py`
- Create: `cloud/backend/app/security.py`
- Create: `host_pc/tests/test_cloud_auth_store.py`
- Modify: `cloud/backend/requirements.txt`

**Interfaces:**
- Produces: `AuthStore(db_path: Path)`, `AuthStore.initialize()`, `create_user()`, `verify_login()`, `create_session()`, `authenticate_session()`, `revoke_session()`, `register_device()`, `create_pairing_code()`, and `consume_pairing_code()`.
- Produces: `hash_password()`, `verify_password()`, `new_session_token()`, `hash_session_token()`, and `hash_pairing_code()`.

- [ ] **Step 1: Add the dependency and write failing schema/security tests**

```python
def test_initialize_creates_versioned_schema(tmp_path):
    store = AuthStore(tmp_path / "auth.db", pairing_secret=b"p" * 32)
    store.initialize()
    assert store.schema_version() == 1

def test_pairing_code_is_single_use_and_never_stored_plaintext(tmp_path):
    store = make_store(tmp_path)
    admin = store.create_user("admin", hash_password("StrongPass123!"), "admin")
    store.register_device("sg-0001", now=100)
    code = store.create_pairing_code("sg-0001", admin.id, now=100)
    raw_db = (tmp_path / "auth.db").read_bytes()
    assert code.encode() not in raw_db
    user = store.create_user("user1", hash_password("StrongPass123!"), "user")
    assert store.consume_pairing_code(code, user.id, now=101) == "sg-0001"
    with pytest.raises(PairingError):
        store.consume_pairing_code(code, user.id, now=102)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_cloud_auth_store.py`

Expected: collection fails because `cloud.backend.app.auth_store` does not exist.

- [ ] **Step 3: Implement SQLite migrations and security primitives**

```python
class AuthStore:
    def initialize(self) -> None:
        with self._connect() as db:
            db.executescript(SCHEMA_V1)
            db.execute("INSERT OR IGNORE INTO schema_meta(version) VALUES (1)")

def hash_pairing_code(secret: bytes, code: str) -> str:
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("pairing code must contain six digits")
    return hmac.new(secret, code.encode("ascii"), hashlib.sha256).hexdigest()
```

Use one connection per operation, `PRAGMA foreign_keys=ON`, WAL mode, a five-second busy timeout, unique indexes for usernames/device IDs/session hashes, and `BEGIN IMMEDIATE` for pairing consumption.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_cloud_auth_store.py`

Expected: all repository tests pass, including concurrent pairing consumption with exactly one winner.

- [ ] **Step 5: Commit**

```powershell
git add cloud/backend/requirements.txt cloud/backend/app/auth_store.py cloud/backend/app/security.py host_pc/tests/test_cloud_auth_store.py
git commit -m "feat(cloud): add authenticated device registry"
```

---

### Task 2: Login, Sessions, and Administrator User Management

**Files:**
- Create: `cloud/backend/app/auth_api.py`
- Create: `host_pc/tests/test_cloud_auth_api.py`
- Modify: `cloud/backend/app/schemas.py`
- Modify: `cloud/backend/app/main.py`

**Interfaces:**
- Consumes: `AuthStore`, password helpers, and session-token helpers from Task 1.
- Produces: `get_current_user()`, `require_admin()`, `/api/auth/*`, and `/api/admin/users`.

- [ ] **Step 1: Write failing API tests**

```python
def test_admin_creates_user_and_user_cannot_call_admin_api(client, admin_cookie):
    created = client.post("/api/admin/users", cookies=admin_cookie,
                          json={"username": "family1", "password": "StrongPass123!"})
    assert created.status_code == 201
    user_cookie = login(client, "family1", "StrongPass123!")
    assert client.get("/api/admin/users", cookies=user_cookie).status_code == 403

def test_login_failure_is_generic_and_rate_limited(client):
    responses = [client.post("/api/auth/login", json={"username": "missing", "password": "bad"})
                 for _ in range(6)]
    assert responses[0].json()["detail"] == "账号或密码错误"
    assert responses[-1].status_code == 429
```

- [ ] **Step 2: Run tests and verify RED**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_cloud_auth_api.py`

Expected: 404 for the new routes.

- [ ] **Step 3: Implement session and admin APIs**

```python
@router.post("/api/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response, request: Request):
    limiter.check(request.client.host, normalize_username(payload.username))
    user = store.verify_login(payload.username, payload.password)
    if user is None:
        raise HTTPException(401, "账号或密码错误")
    raw_token = store.create_session(user.id, expires_at=utc_now() + SESSION_TTL)
    response.set_cookie("sg_session", raw_token, httponly=True, secure=secure_cookie,
                        samesite="strict", max_age=SESSION_TTL_SECONDS)
    return LoginResponse(user=user.public(), access_token=raw_token if payload.client == "pc" else None)
```

Require `SG_AUTH_DB`, `SG_PAIRING_SECRET`, `SG_INITIAL_ADMIN_USER`, and `SG_INITIAL_ADMIN_PASSWORD` during first initialization. Clear the initial password from the process environment after bootstrap and never log it.

- [ ] **Step 4: Run auth tests and affected cloud tests**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_cloud_auth_api.py host_pc\tests\test_cloud_llm_optional.py host_pc\tests\test_e1_cloud_contract.py`

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add cloud/backend/app/auth_api.py cloud/backend/app/schemas.py cloud/backend/app/main.py host_pc/tests/test_cloud_auth_api.py
git commit -m "feat(cloud): add user sessions and admin accounts"
```

---

### Task 3: Device Ownership and One-Time Pairing

**Files:**
- Create: `cloud/backend/app/device_api.py`
- Create: `host_pc/tests/test_cloud_device_api.py`
- Modify: `cloud/backend/app/schemas.py`
- Modify: `cloud/backend/app/main.py`

**Interfaces:**
- Consumes: `get_current_user()`, `require_admin()`, and pairing transactions.
- Produces: ownership-filtered `/api/devices`, `/api/devices/pair`, and `/api/admin/devices/*` routes.

- [ ] **Step 1: Write failing ownership and pairing tests**

```python
def test_users_see_only_owned_devices(client, user_a, user_b, store):
    store.assign_device("sg-a", user_a.id)
    store.assign_device("sg-b", user_b.id)
    assert ids(client.get("/api/devices", cookies=session(user_a))) == ["sg-a"]
    assert client.get("/api/devices/sg-b/latest", cookies=session(user_a)).status_code == 404

def test_pairing_code_expires_after_ten_minutes(client, user_a, admin, store):
    code = store.create_pairing_code("sg-a", admin.id, now=100)
    freeze_time(701)
    response = client.post("/api/devices/pair", cookies=session(user_a), json={"code": code})
    assert response.status_code == 422
    assert response.json()["detail"] == "绑定码无效或已过期"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_cloud_device_api.py`

Expected: 404 for device routes.

- [ ] **Step 3: Implement ownership-filtered routes**

```python
def require_device_access(device_id: str, user: UserRecord) -> DeviceRecord:
    device = store.get_device(device_id)
    if device is None or (user.role != "admin" and device.owner_user_id != user.id):
        raise HTTPException(404, "设备不存在")
    return device
```

Return pairing-code plaintext only in the immediate admin creation response. Never include it in list routes, logs, SQLite rows, or WebSocket events.

- [ ] **Step 4: Run focused tests**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_cloud_device_api.py host_pc\tests\test_cloud_auth_api.py`

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add cloud/backend/app/device_api.py cloud/backend/app/schemas.py cloud/backend/app/main.py host_pc/tests/test_cloud_device_api.py
git commit -m "feat(cloud): pair users with owned mirrors"
```

---

### Task 4: MQTT Device Registration and Privacy-Safe Snapshots

**Files:**
- Create: `cloud/backend/app/realtime.py`
- Create: `host_pc/tests/test_cloud_realtime.py`
- Modify: `cloud/backend/app/mqtt_bridge.py`
- Modify: `cloud/backend/app/main.py`
- Modify: `host_pc/tests/test_e1_cloud_contract.py`

**Interfaces:**
- Consumes: `AuthStore.register_device()` and `RealtimeHub.publish_threadsafe()`.
- Produces: `DeviceSnapshot` containing only `device_id`, nullable scores, final level, reasons, `last_seen_at`, and bounded advice metadata.

- [ ] **Step 1: Write failing registration/privacy tests**

```python
def test_valid_uplink_registers_device_before_broadcast(bridge, store, hub):
    bridge._on_message(None, None, mqtt_message("sg-0001", valid_payload()))
    assert store.get_device("sg-0001") is not None
    assert hub.last_snapshot("sg-0001").scores.csi == 80

@pytest.mark.parametrize("forbidden", ["jpeg_b64", "mfcc", "landmarks", "roi"])
def test_snapshot_never_contains_raw_fields(snapshot, forbidden):
    assert forbidden not in snapshot.model_dump(mode="json")
```

- [ ] **Step 2: Run tests and verify RED**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_cloud_realtime.py host_pc\tests\test_e1_cloud_contract.py`

Expected: constructor/signature failures because registry and hub are not wired.

- [ ] **Step 3: Wire bridge to registry and hub**

```python
self._store.register_device(up.device_id, now=up.ts)
snapshot = DeviceSnapshot.from_uplink(up, last_seen_at=up.ts)
self._hub.publish_threadsafe(snapshot)
```

Perform schema and topic/device matching before any SQLite, InfluxDB, cache, or WebSocket operation. The Paho thread must schedule coroutine work with `asyncio.run_coroutine_threadsafe` and must not call a WebSocket directly.

- [ ] **Step 4: Run focused tests**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_cloud_realtime.py host_pc\tests\test_e1_cloud_contract.py`

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add cloud/backend/app/realtime.py cloud/backend/app/mqtt_bridge.py cloud/backend/app/main.py host_pc/tests/test_cloud_realtime.py host_pc/tests/test_e1_cloud_contract.py
git commit -m "feat(cloud): register and broadcast mirror snapshots"
```

---

### Task 5: Bounded InfluxDB History and Authorized WebSocket

**Files:**
- Create: `host_pc/tests/test_cloud_history.py`
- Modify: `cloud/backend/app/db_influx.py`
- Modify: `cloud/backend/app/device_api.py`
- Modify: `cloud/backend/app/realtime.py`
- Modify: `cloud/backend/app/schemas.py`

**Interfaces:**
- Produces: `InfluxWriter.query_history(device_id: str, range_name: Literal["1h", "24h", "7d"]) -> list[HistoryPoint]`.
- Produces: authenticated `/ws/devices` and bounded history REST responses.

- [ ] **Step 1: Write failing range, limit, and WebSocket authorization tests**

```python
@pytest.mark.parametrize("range_name", ["1h", "24h", "7d"])
def test_history_is_bounded(range_name, influx):
    points = influx.query_history("sg-0001", range_name)
    assert len(points) <= 500

def test_websocket_filters_snapshots_by_owner(app, user_a, user_b, hub):
    with websocket(app, user_a) as ws:
        hub.publish_threadsafe(snapshot("sg-b"))
        hub.publish_threadsafe(snapshot("sg-a"))
        assert ws.receive_json()["device_id"] == "sg-a"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_cloud_history.py host_pc\tests\test_cloud_realtime.py`

Expected: missing history query and WebSocket route failures.

- [ ] **Step 3: Implement fixed Flux templates and WebSocket filtering**

```python
RANGES = {
    "1h": ("-1h", "10s"),
    "24h": ("-24h", "3m"),
    "7d": ("-7d", "21m"),
}

query = f'''from(bucket: {json.dumps(self.bucket)})
  |> range(start: {start})
  |> filter(fn: (r) => r._measurement == "stroke_uplink")
  |> filter(fn: (r) => r.device_id == {json.dumps(device_id)})
  |> aggregateWindow(every: {window}, fn: last, createEmpty: false)
  |> limit(n: 500)'''
```

Do not accept arbitrary Flux fragments, start timestamps, bucket names, or aggregation functions from clients.

- [ ] **Step 4: Run focused tests**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_cloud_history.py host_pc\tests\test_cloud_realtime.py host_pc\tests\test_cloud_device_api.py`

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add cloud/backend/app/db_influx.py cloud/backend/app/device_api.py cloud/backend/app/realtime.py cloud/backend/app/schemas.py host_pc/tests/test_cloud_history.py host_pc/tests/test_cloud_realtime.py
git commit -m "feat(cloud): stream authorized device history"
```

---

### Task 6: User Web Experience

**Files:**
- Create: `cloud/backend/app/web.py`
- Create: `cloud/backend/app/static/login.html`
- Create: `cloud/backend/app/static/dashboard.html`
- Create: `cloud/backend/app/static/device.html`
- Create: `cloud/backend/app/static/pair.html`
- Create: `cloud/backend/app/static/css/app.css`
- Create: `cloud/backend/app/static/js/auth.js`
- Create: `cloud/backend/app/static/js/dashboard.js`
- Create: `cloud/backend/app/static/js/device.js`
- Create: `cloud/backend/app/static/js/pair.js`
- Create: `cloud/backend/app/static/vendor/chart.umd.min.js`
- Create: `host_pc/tests/test_remote_web_assets.py`
- Modify: `cloud/backend/app/main.py`

**Interfaces:**
- Consumes: Tasks 2-5 REST/WebSocket APIs.
- Produces: responsive login, owned-device dashboard, pairing, detail, and trend views.

- [ ] **Step 1: Write failing asset and UI-contract tests**

```python
def test_device_page_marks_missing_modalities_unavailable():
    js = read("cloud/backend/app/static/js/device.js")
    assert 'score == null ? "未接入"' in js
    assert "|| 80" not in js

def test_websocket_has_five_second_polling_fallback():
    js = read("cloud/backend/app/static/js/dashboard.js")
    assert "5000" in js
    assert "clearInterval" in js
```

- [ ] **Step 2: Run tests and verify RED**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_remote_web_assets.py`

Expected: asset files are missing.

- [ ] **Step 3: Implement the user pages**

```javascript
function renderScore(value) {
  return value == null
    ? { text: "未接入", className: "score-unavailable" }
    : { text: String(value), className: scoreClass(value) };
}

function enterPolling() {
  if (pollTimer) return;
  pollTimer = window.setInterval(refreshSnapshot, 5000);
}

function leavePolling() {
  window.clearInterval(pollTimer);
  pollTimer = null;
}
```

Use stable responsive grid tracks, no nested cards, no decorative gradients/orbs, familiar icons with tooltips, visible focus states, and a restrained neutral/green/yellow/red palette. The danger state always contains `立即拨打 120`; the medical disclaimer remains visible without obscuring live data.

- [ ] **Step 4: Run unit tests and Playwright visual checks**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_remote_web_assets.py host_pc\tests\test_cloud_auth_api.py host_pc\tests\test_cloud_device_api.py`

Then run Playwright at 1440x900, 1024x768, and 390x844. Verify no overlap, missing-score labels fit, login errors are visible, and WebSocket status does not shift layout.

- [ ] **Step 5: Commit**

```powershell
git add cloud/backend/app/web.py cloud/backend/app/static cloud/backend/app/main.py host_pc/tests/test_remote_web_assets.py
git commit -m "feat(web): add remote mirror monitoring dashboard"
```

---

### Task 7: Administrator Console

**Files:**
- Create: `cloud/backend/app/static/admin.html`
- Create: `cloud/backend/app/static/js/admin.js`
- Modify: `cloud/backend/app/static/css/app.css`
- Modify: `host_pc/tests/test_remote_web_assets.py`

**Interfaces:**
- Consumes: admin user/device/pairing APIs.
- Produces: user creation/deactivation, device ownership, pairing-code generation, unbind, and service-health UI.

- [ ] **Step 1: Write failing admin-view tests**

```python
def test_admin_page_never_renders_secret_fields():
    combined = read("admin.html") + read("js/admin.js")
    for forbidden in ("MQTT_PASS", "INFLUX_TOKEN", "VOLC_ARK_API_KEY", "manager_token"):
        assert forbidden not in combined

def test_pairing_code_is_removed_after_ten_minutes():
    js = read("cloud/backend/app/static/js/admin.js")
    assert "600000" in js
    assert "textContent = \"\"" in js
```

- [ ] **Step 2: Run tests and verify RED**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_remote_web_assets.py`

Expected: admin assets are missing.

- [ ] **Step 3: Implement the admin console**

Render user state, device ownership, last seen, and health only. Require an explicit confirmation dialog before deactivation or unbinding. Keep a generated pairing code only in DOM memory and clear its text after 600 seconds or navigation.

- [ ] **Step 4: Run tests and visual checks**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_remote_web_assets.py host_pc\tests\test_cloud_auth_api.py host_pc\tests\test_cloud_device_api.py`

Expected: all pass; mobile admin tables use horizontal scrolling without text overlap.

- [ ] **Step 5: Commit**

```powershell
git add cloud/backend/app/static/admin.html cloud/backend/app/static/js/admin.js cloud/backend/app/static/css/app.css host_pc/tests/test_remote_web_assets.py
git commit -m "feat(web): add remote monitoring administration"
```

---

### Task 8: PC Client Remote Monitoring Source

**Files:**
- Create: `host_pc/stroke_host/io/remote_monitor_client.py`
- Create: `host_pc/stroke_host/ui/remote_monitor_panel.py`
- Create: `host_pc/tests/test_remote_monitor_client.py`
- Modify: `host_pc/stroke_host/ui/main_window.py`
- Modify: `host_pc/pyproject.toml`

**Interfaces:**
- Consumes: login, devices, latest, history, and `/ws/devices` contracts.
- Produces: `RemoteMonitorClient`, `RemoteSnapshotWorker`, and a PyQt5 remote-monitor tab.

- [ ] **Step 1: Write failing HTTPS, keyring, and fallback tests**

```python
def test_client_rejects_plain_http_except_loopback():
    with pytest.raises(ValueError):
        RemoteMonitorClient("http://example.com")

def test_pc_token_is_saved_to_keyring_not_yaml(fake_server):
    client = RemoteMonitorClient(fake_server.url)
    client.login("family1", "StrongPass123!")
    assert keyring.get_password("StrokeGuard Remote", fake_server.url)
    assert "StrongPass123!" not in Path("profile.yaml").read_text()

def test_worker_polls_every_five_seconds_after_socket_failure(clock):
    worker = make_worker(websocket_fails=True, clock=clock)
    worker.run_steps(3)
    assert worker.poll_intervals == [5, 5]
```

- [ ] **Step 2: Run tests and verify RED**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_remote_monitor_client.py`

Expected: remote client module is missing.

- [ ] **Step 3: Implement remote REST/WebSocket client and Qt panel**

```python
class RemoteMonitorClient:
    def login(self, username: str, password: str) -> UserInfo:
        response = self._json("POST", "/api/auth/login",
                              {"username": username, "password": password, "client": "pc"})
        save_remote_token(self.base_url, response["access_token"])
        return UserInfo.model_validate(response["user"])
```

Use `Authorization: Bearer` for PC calls, certificate verification enabled by default, a 64 KiB response cap, bounded UI-safe errors, and `websocket-client` for WSS. Keep LAN YAML configuration in the existing `ConfigPanel`; remote mode is read-only.

- [ ] **Step 4: Run PC tests and package import check**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_remote_monitor_client.py host_pc\tests\test_config_panel.py host_pc\tests\test_gui_worker.py`

Run: `host_pc\.venv\Scripts\python.exe -c "from stroke_host.ui.main_window import MainWindow; from stroke_host.io.remote_monitor_client import RemoteMonitorClient"`

Expected: all pass and imports exit 0.

- [ ] **Step 5: Commit**

```powershell
git add host_pc/pyproject.toml host_pc/stroke_host/io/remote_monitor_client.py host_pc/stroke_host/ui/remote_monitor_panel.py host_pc/stroke_host/ui/main_window.py host_pc/tests/test_remote_monitor_client.py
git commit -m "feat(pc): monitor owned mirrors over the internet"
```

---

### Task 9: Deployment, HTTPS Guardrails, End-to-End Acceptance, and Packaging

**Files:**
- Create: `cloud/native/e2e_remote_monitor.py`
- Create: `host_pc/tests/test_remote_monitor_e2e_contract.py`
- Modify: `cloud/.env.example`
- Modify: `cloud/native/start.sh`
- Modify: `cloud/native/deploy_remote.sh`
- Modify: `cloud/README.md`
- Modify: `README.md`
- Modify: `scripts/run_cloud_e2e_interactive.ps1`
- Modify: `scripts/package_release.ps1`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: persistent SQLite deployment, secure startup validation, repeatable E2E evidence, updated EXE, and developer handoff ZIP.

- [ ] **Step 1: Write failing deployment-contract tests**

```python
def test_production_requires_secure_public_origin():
    start = read("cloud/native/start.sh")
    assert "SG_PUBLIC_ORIGIN" in start
    assert "SG_ALLOW_INSECURE_HTTP" in start
    assert "https://" in start

def test_remote_e2e_proves_tenant_isolation_and_no_media():
    probe = read("cloud/native/e2e_remote_monitor.py")
    assert "TENANT_ISOLATION_OK" in probe
    for forbidden in ("jpeg_b64", "mfcc", "landmarks", "roi"):
        assert forbidden not in probe
```

- [ ] **Step 2: Run tests and verify RED**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_remote_monitor_e2e_contract.py host_pc\tests\test_cloud_native_contract.py`

Expected: missing secure startup variables and E2E probe.

- [ ] **Step 3: Implement persistent deployment and secure startup checks**

```bash
case "${SG_PUBLIC_ORIGIN:-}" in
  https://*) ;;
  http://127.0.0.1*|http://localhost*)
    [ "${SG_ALLOW_INSECURE_HTTP:-0}" = "1" ] || exit 1
    ;;
  *) echo "SG_PUBLIC_ORIGIN must use HTTPS" >&2; exit 1 ;;
esac

export SG_AUTH_DB="$state_dir/auth/strokeguard.sqlite3"
mkdir -p "$state_dir/auth"
chmod 700 "$state_dir/auth"
```

The VPS ingress or reverse proxy must terminate HTTPS and WSS before public login is enabled. Keep FastAPI on its private/upstream port when TLS termination is external. Preserve `native/state/auth` across deployments exactly like InfluxDB state.

- [ ] **Step 4: Run full local verification**

Run: `host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests --basetemp=$env:TEMP\strokeguard-remote-final -p no:cacheprovider`

Expected: all tests pass with no warnings containing credentials.

- [ ] **Step 5: Deploy and run remote E2E**

Run: `powershell -ExecutionPolicy Bypass -File scripts\deploy_cloud_native_interactive.ps1 -HostIp $env:SG_VPS_HOST`

Run: `powershell -ExecutionPolicy Bypass -File scripts\run_cloud_e2e_interactive.ps1 -HostIp $env:SG_VPS_HOST`

Update `scripts/run_cloud_e2e_interactive.ps1` to upload and execute both `e2e_mqtt.py` and `e2e_remote_monitor.py` in one authenticated SSH session. The remote E2E must create two temporary users and two temporary devices, prove cross-tenant REST and WebSocket access is denied, consume a pairing code once, verify a second use fails, publish numeric MQTT data, query no more than 500 history points, and print `TENANT_ISOLATION_OK` without printing credentials.

- [ ] **Step 6: Run S3 and browser acceptance**

With `sg-0001` powered independently and PC USB disconnected:

1. Confirm S3 publishes numeric uplinks directly to VPS.
2. Confirm the bound user sees the real CSI value and F/S/T/E as `未接入`.
3. Confirm WebSocket updates the browser and PC client; block WebSocket and verify five-second polling.
4. Confirm another user receives 404 for `sg-0001` REST and no `sg-0001` WebSocket event.
5. Confirm danger copy says `立即拨打 120` and advice cannot change the device level.
6. Scan browser, backend, MQTT, and PC logs for passwords, tokens, API keys, and raw media fields; expected zero matches.

- [ ] **Step 7: Rebuild final deliverables**

Run: `powershell -ExecutionPolicy Bypass -File scripts\package_release.ps1`

Verify `dist\StrokeGuard-Demo.exe` launches, remote login renders without overlap at 1024x720 and 1220x820, and `dist\StrokeGuard-Developer-Handoff.zip` excludes `.env`, SQLite state, tokens, logs, caches, recordings, and build directories.

- [ ] **Step 8: Commit and push**

```powershell
git add cloud/.env.example cloud/native cloud/README.md README.md scripts/run_cloud_e2e_interactive.ps1 scripts/package_release.ps1 host_pc/tests/test_remote_monitor_e2e_contract.py
git commit -m "feat(release): deliver secure remote monitoring"
git push origin codex/standalone-e1
```

---

## Final Verification Matrix

| Requirement | Evidence |
|---|---|
| Admin-created accounts | Auth API tests and admin UI acceptance |
| Multi-device ownership | Device API and two-tenant E2E tests |
| Six-digit, 10-minute, single-use pairing | Repository concurrency tests and E2E probe |
| Browser and PC external access | HTTPS/WSS acceptance on both clients |
| WebSocket with five-second fallback | Browser/PC unit tests and blocked-socket acceptance |
| 1h/24h/7d, max 500 points | Flux query tests and E2E history query |
| Real CSI and missing F/S/T/E | Independent S3 acceptance with USB disconnected |
| Medical boundary | Danger-copy test and immutable device level |
| No raw media or secrets | Schema rejection, asset scan, log scan, and release ZIP scan |
| Offline mirror behavior unchanged | Existing firmware/Unity tests and unplugged-PC run |
