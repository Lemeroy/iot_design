# Preliminary Demo Task 2 Report

## Status

Implemented MQTT-observed device selection and the authenticated, read-only
demo API on the current branch.

## Evidence

### RED

Command:

```text
F:\iot_design> .\host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_demo_api.py host_pc\tests\test_e1_cloud_contract.py --basetemp=F:\iot_design\.pytest-native-root\prelim-task-2-red -p no:cacheprovider
```

Result: collection failed with `ModuleNotFoundError: No module named
'cloud.backend.app.demo_api'`. This was the expected missing-module RED before
the API implementation existed.

### Focused GREEN

Command:

```text
F:\iot_design> .\host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_demo_api.py host_pc\tests\test_e1_cloud_contract.py --basetemp=F:\iot_design\.pytest-native-root\prelim-task-2-focused -p no:cacheprovider
```

Result: `18 passed in 3.44s`, with no warnings.

The focused coverage verifies unauthenticated access, generic login failure,
successful login and secure cookie flags, strict device IDs, unknown and stale
devices, connection/disconnection, response allowlisting, nullable scores,
latest advice projection, and receipt-time creation only after topic, JSON,
schema, and topic-device validation.

### Full Host Suite

Command:

```text
F:\iot_design> .\host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests --basetemp=F:\iot_design\.pytest-native-root\prelim-task-2-full -p no:cacheprovider
```

Result: `224 passed in 19.04s`, with no warnings.

### Self-Review

- `DemoDeviceResp` and `DemoAdviceResp` form an explicit response allowlist:
  device ID, online state, receipt time, F/S/T/E/CSI/final, S3 level/reasons/
  veto, and advice text/source/time. Profile, media, schema metadata, and
  arbitrary cache entries cannot be serialized.
- The bridge records `received_at` immediately after all accepted-uplink
  validation. The API uses only that VPS receipt timestamp and a fixed
  30-second window for online state; it does not use the device `ts`.
- Device level is sourced exclusively from the validated uplink. Advice is
  projected without a level field, so it cannot overwrite the S3 level.
- The demo routes do not publish MQTT messages or invoke S3/profile/network/
  fusion/threshold/veto/remote-control mutation paths. Existing health,
  bridge, Influx, advice, and downlink paths remain unchanged.
- Session cookies are HttpOnly and SameSite strict, with the existing auth
  configuration deciding Secure mode. Login responses use one generic error
  and the routes do not log request credentials.
- `git diff --check` completed with exit code 0. Git emitted only local
  LF-to-CRLF conversion notices, not whitespace errors.

## Concerns

No known implementation concerns. The response contract deliberately exposes
monitoring data and LLM advice only; dashboard rendering and deployment remain
outside this task.

## Independent Review Fixes

### RED

Command:

```text
F:\iot_design> .\host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_demo_api.py host_pc\tests\test_e1_cloud_contract.py --basetemp=F:\iot_design\.pytest-native-root\prelim-task-2-review-red -p no:cacheprovider
```

Result: `4 failed, 21 passed in 6.41s`, as expected before the fixes. Empty
and malformed login bodies raised `JSONDecodeError`; the demo API directly
read `bridge.latest`; and `MqttBridge.cache_snapshot` did not exist.

### GREEN

Command:

```text
F:\iot_design> .\host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests\test_demo_api.py host_pc\tests\test_e1_cloud_contract.py --basetemp=F:\iot_design\.pytest-native-root\prelim-task-2-review-focused -p no:cacheprovider
```

Result: `25 passed in 4.12s`, with no warnings.

The regression coverage verifies that empty, malformed, and non-object login
JSON receive the existing generic 401 response without reflecting the body;
that the API reads only the bridge snapshot; and that snapshots are isolated
from the mutable cache dictionary.

### Full Host Suite

Command:

```text
F:\iot_design> .\host_pc\.venv\Scripts\python.exe -m pytest -q host_pc\tests --basetemp=F:\iot_design\.pytest-native-root\prelim-task-2-review-full -p no:cacheprovider
```

Result: `231 passed in 19.56s`, with no warnings.

`git diff --check` completed with exit code 0. Git emitted only local
LF-to-CRLF conversion notices, not whitespace errors.

### Residual Scope Concern

The pre-existing non-demo `/devices/{device_id}/latest` endpoint in
`cloud/backend/app/main.py` still reads `MqttBridge.latest` directly. It is
outside this review fix's assigned file ownership; the new demo API uses only
the lock-protected snapshot interface.

## Remaining Review Fixes

### RED

Command:

```text
F:\iot_design> host_pc\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-native-root\task-2-review-find-red host_pc\tests\test_e1_cloud_contract.py::test_bridge_discards_advice_when_a_newer_uplink_arrives_during_generation host_pc\tests\test_demo_api.py::test_legacy_latest_endpoint_reads_the_bridge_snapshot
```

Result: `2 failed in 2.22s`, as expected. The blocked advisor result was
stored after a newer uplink had replaced the cache, and the legacy latest
endpoint dereferenced `bridge.latest` instead of the lock-protected snapshot.

### GREEN

Direct regressions:

```text
F:\iot_design> host_pc\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-native-root\task-2-review-green2 host_pc\tests\test_e1_cloud_contract.py::test_bridge_discards_advice_when_a_newer_uplink_arrives_during_generation host_pc\tests\test_demo_api.py::test_legacy_latest_endpoint_reads_the_bridge_snapshot
```

Result: `2 passed in 1.60s`.

Assigned focused files:

```text
F:\iot_design> host_pc\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-native-root\task-2-review-focused-final host_pc\tests\test_demo_api.py host_pc\tests\test_e1_cloud_contract.py
```

Result: `27 passed in 3.75s`.

The bridge assigns a monotonically increasing per-device generation while
accepting each valid uplink. Advice tasks capture that generation, take a
locked throttling snapshot, and recheck the generation before cache storage,
MQTT publish, and Influx persistence. A new uplink clears the advice attached
to the superseded uplink snapshot while retaining the private advice timestamp
used for normal-level throttling. `GET /devices/{device_id}/latest` now reads
only `cache_snapshot`.

### Controller Full Host Suite

The controller ran the full host suite without rerun by this task:

```text
host_pc\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-native-root\task-2-review-full-final host_pc\tests
```

Result: `233 passed in 19.60s`.

The controller also ran `git diff --check` with exit code 0. Git emitted only
LF-to-CRLF conversion notices, not whitespace errors.

### Final Self-Review

- No lock is held while generating advice, publishing MQTT, or writing Influx.
- The deterministic blocked-advisor test proves a result from an older
  generation cannot store, publish, or persist after the newer uplink is
  accepted.
- Both demo and legacy latest endpoints use the bridge's lock-protected
  snapshot API; the earlier residual scope concern is resolved.

### Remaining Concern

Generation checks occur immediately before each external side effect. An
uplink that arrives after a publish has started cannot cancel that already
started MQTT call without holding the cache lock across network I/O, which is
intentionally prohibited. The cache cannot retain a mixed old-advice/new-
uplink snapshot because each accepted uplink clears the superseded advice.
