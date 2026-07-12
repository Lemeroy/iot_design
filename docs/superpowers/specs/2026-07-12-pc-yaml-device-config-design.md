# PC YAML and ESP32-S3 Configuration Design

## 1. Objective

StrokeGuard keeps the ESP32-S3 as the authoritative runtime device while
allowing the optional PyQt5 PC application to edit a local YAML profile and
synchronize an explicitly bounded subset to the mirror over the local network.
Closing the PC, losing the LAN, or submitting an invalid configuration must not
interrupt local sensing, fusion, display, or alarms.

This feature does not make the PC a score producer and does not restore the old
PC-to-device score injection path.

## 2. Chosen approach

The PC owns YAML parsing and editing. It converts validated YAML fields to a
strict JSON request for the device. The ESP32-S3 does not parse YAML.

This keeps YAML usability in the management application without adding a YAML
parser or arbitrary document handling to firmware. USB-CDC remains a recovery
and diagnostic interface; normal configuration uses the LAN API.

## 3. Local YAML contract

The local file remains `host_pc/config/profile.yaml` and uses this versioned
shape:

```yaml
schema_version: 1
device_id: sg-0001

device:
  host: strokeguard-sg-0001.local
  port: 80

user:
  age: 68
  gender: M
  conditions:
    - hypertension
  meds:
    - aspirin
  stroke_history: false

thresholds:
  face_danger: 30
  mouth_angle_danger_deg: 20
  speech_danger: 35
```

Rules:

- The file is UTF-8 and no larger than 64 KiB.
- Unknown fields are rejected rather than ignored.
- `device_id` is limited to `[A-Za-z0-9_-]` and 32 characters.
- `host` accepts a private/link-local IP address or a `.local` hostname. The PC
  refuses to send the management credential to a public destination.
- Age is `0..130`; gender is `M`, `F`, or `other`.
- Conditions and medications each contain at most four non-empty strings of at
  most 31 UTF-8 characters.
- `thresholds` is an optional read-only release baseline. Omitting it restores
  the release values. Any different value fails validation and is never sent
  to the device.
- Wi-Fi, MQTT, VPS, and LLM credentials never appear in YAML.
- Legacy files without `schema_version` and `device` are loaded as version 0,
  validated, migrated in memory, and written as version 1 only after an
  explicit save.

Saving is atomic: write a temporary file in the same directory, flush it,
replace the target, and leave the previous file intact on failure.

## 4. PC user interface

The main window gains an unframed `设备配置` workspace implemented as a separate
widget rather than expanding `main_window.py` further.

It contains:

- A form view for device address and user profile fields.
- A YAML view using a high-contrast monospace editor with visible line numbers,
  readable selection colors, and inline validation status.
- Commands for `从设备读取`, `保存本地`, `同步到设备`, and reverting unsaved
  edits.
- A read-only medical baseline section for fusion weights, danger thresholds,
  and veto rules.
- Capability-driven controls. Current E1 advertises only `profile_write`.
  Display or sampling controls are shown only after firmware advertises their
  corresponding capability and implements their runtime effect.

Form and YAML views share one validated model. Switching views cannot bypass
validation. Synchronization is disabled while local text is invalid or while a
request is in progress. Network work runs outside the Qt UI thread.

The management token is stored through the existing Python `keyring`
dependency under a device-specific key. The UI may set or replace it through a
masked credential dialog, but never displays or logs its value.

## 5. Device management API

The ESP32-S3 exposes the API only after Wi-Fi has an address and a non-empty
management token is provisioned locally. The development transport is HTTP on
the trusted LAN; TLS is required before production deployment.

### Read configuration

```text
GET /api/v1/config
Authorization: Bearer <management-token>
```

Response:

```json
{
  "schema_version": 1,
  "revision": 3,
  "device_id": "sg-0001",
  "profile": {
    "age": 68,
    "gender": "M",
    "conditions": ["hypertension"],
    "meds": ["aspirin"],
    "stroke_history": false
  },
  "readonly": {
    "face_danger": 30,
    "mouth_angle_danger_deg": 20,
    "speech_danger": 35
  },
  "capabilities": ["profile_write"]
}
```

### Update configuration

```text
PUT /api/v1/config
Authorization: Bearer <management-token>
Content-Type: application/json
```

Request:

```json
{
  "schema_version": 1,
  "expected_revision": 3,
  "profile": {
    "age": 69,
    "gender": "M",
    "conditions": ["hypertension"],
    "meds": ["aspirin"],
    "stroke_history": false
  }
}
```

The response returns the complete representation with an incremented revision.
The API rejects unknown fields and does not accept device ID, networking,
credentials, fusion weights, danger thresholds, or veto rules in a write.

Status behavior:

- `401`: missing or invalid management token.
- `409`: `expected_revision` differs from the stored revision.
- `413`: body exceeds the fixed request bound.
- `415`: content type is not JSON.
- `422`: schema, range, UTF-8, or whitelist validation fails.
- `500`: NVS persistence fails; the previous in-memory and stored configuration
  remains authoritative.

The server compares tokens in constant time and never logs authorization
headers, profile contents, or request bodies.

## 6. Firmware storage

The versioned `sg_device_config_t` gains a monotonic configuration revision and
the existing profile arrays remain bounded. Firmware supports migration from
the current version-1 NVS blob to the new structure before calculating the new
CRC32. An accepted update follows this order:

1. Parse into a temporary patch structure.
2. Copy the current configuration to a candidate.
3. Apply only the profile whitelist and increment revision.
4. Validate every field and calculate CRC32.
5. Persist and commit the complete candidate blob.
6. Replace the in-memory configuration only after persistence succeeds.

The fusion task snapshots profile/configuration state under a lock so an update
cannot race with MQTT payload creation. Medical release constants stay compiled
into firmware and outside `sg_device_config_t`.

## 7. Failure and safety behavior

- YAML invalid: keep the last valid in-memory model and disable save/sync.
- Local save failure: retain the old file and show a bounded error.
- Device unreachable: retain local edits and allow retry; mirror operation is
  unaffected.
- Authentication failure: do not retry automatically or reveal the token.
- Revision conflict: fetch the current device value and require the user to
  choose local or device profile before another write.
- NVS corruption at boot: use validated factory defaults and expose the new
  revision; never infer medical state from missing configuration.
- PC disconnects during PUT: the device either commits the complete candidate
  or retains the previous complete blob.
- Cloud connectivity is unrelated to this API and cannot gate local config
  reads, local fusion, or alarms.

## 8. Modules

PC additions:

```text
host_pc/stroke_host/config/profile_loader.py  strict schema and migration
host_pc/stroke_host/config/profile_store.py   atomic YAML persistence
host_pc/stroke_host/io/device_config_client.py LAN JSON client and keyring
host_pc/stroke_host/ui/config_panel.py         form/YAML configuration UI
```

Firmware additions:

```text
firmware_esp32/main/sg_manager_api.c/.h       bounded HTTP management API
firmware_esp32/main/device_config.c/.h        migration, revision, atomic patch
```

`main_window.py` only owns navigation, worker lifecycle, and signal wiring for
the configuration panel.

## 9. Verification and delivery order

1. YAML schema/migration tests reject unknown fields, public hosts, changed
   medical thresholds, oversize text, and malformed UTF-8; atomic-save failure
   preserves the previous file.
2. UI tests cover form/YAML round trips, invalid state, masked credential entry,
   and non-blocking synchronization.
3. Firmware pure-function and Unity tests cover authorization, strict JSON,
   profile bounds, revision conflict, version-1 migration, CRC, failed persist,
   and medical-field rejection.
4. PC client tests cover success, timeout, `401`, `409`, and public-host refusal.
5. COM3/LAN integration verifies GET, PUT, reboot persistence, no credential
   logging, MQTT continuity, and continued local fusion with the PC closed.
6. Each completed delivery slice is committed independently, followed by the
   complete Python regression suite and an ESP-IDF production build.

## 10. Explicit non-goals

- Editing release fusion weights, danger thresholds, or veto rules.
- Sending final scores from PC to ESP32-S3.
- Uploading YAML, raw audio, images, MFCC, landmarks, or calibration media to
  the cloud.
- Remotely changing Wi-Fi/MQTT credentials in this delivery.
- Model or firmware update through this profile API.
