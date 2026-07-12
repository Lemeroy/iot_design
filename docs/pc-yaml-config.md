# PC YAML and Mirror Profile Management

## Purpose

The PyQt5 application is an optional same-LAN observer and configuration tool.
The ESP32-S3 remains authoritative for sensing, deterministic fusion, alerts,
display, and MQTT. Closing the PC does not stop the mirror.

The management feature changes only the limited user profile. It cannot change
medical thresholds, veto rules, fusion weights, Wi-Fi, MQTT, device identity,
firmware, or models.

## YAML schema

`host_pc/config/profile.yaml` contains no credentials:

```yaml
schema_version: 1
device_id: sg-0001
device:
  host: <S3_LAN_IP>
  port: 80
user:
  age: 68
  gender: M
  conditions: [hypertension]
  meds: [aspirin]
  stroke_history: false
thresholds:
  face_danger: 30
  mouth_angle_danger_deg: 20
  speech_danger: 35
```

Bounds:

- `device_id`: 1 to 32 characters from `A-Z`, `a-z`, `0-9`, `_`, `-`.
- `device.host`: private/link-local IP or `.local` hostname only.
- `device.port`: 1 to 65535.
- `age`: 0 to 130; `gender`: `M`, `F`, or `other`.
- `conditions` and `meds`: at most four items each; each item is 1 to 31
  characters without control characters.
- `thresholds`: fixed release values shown read-only. Any YAML change is
  rejected.

YAML saves use validation followed by atomic replacement. Wi-Fi, MQTT, VPS,
LLM, and management credentials must never be added to this file.

## First use

1. Connect the PC and S3 to the same 2.4 GHz LAN.
2. Read `GOT_IP address=...` from the S3 serial log or router DHCP list.
3. Enter that private address and port in the form, then click `更新 YAML` and
   `保存本地`.
4. Enter the management Token in the masked field and click `保存密钥`. The
   value is stored by Python Keyring under service `StrokeGuard Manager` and
   account equal to the device ID. The field is cleared after saving.
5. Click `从设备读取`. A successful response populates the form/YAML and shows
   the device revision.
6. Edit the profile, update YAML, then click `同步到设备`.

The sync button remains disabled until a device revision has been read. If the
device ID, host, or port changes, the remembered revision is cleared and a new
pull is required.

## Revision conflicts

PUT uses `expected_revision`. If another operation changed the device first,
the server returns `409` and the PC fetches the current version.

- `使用本地`: retry the visible local profile against the newly fetched
  revision.
- `使用设备`: discard the visible local profile and load the device version.

There is no silent overwrite.

## Security behavior

- The client resolves the destination before every request and refuses any
  public address result.
- System HTTP proxies are disabled for management requests.
- Bearer Tokens, authorization headers, request bodies, and profile contents
  are not logged.
- HTTP is permitted only for controlled development on a trusted LAN. Use TLS
  or a secure tunnel before production deployment.
- API errors are bounded UI messages. Server bodies, backend details, and
  credentials are not included in exceptions.

## Run and test

```powershell
cd F:\iot_design\host_pc
.venv\Scripts\python.exe -m stroke_host.ui.main_window `
  --profile config\profile.yaml --source cdc --port COM3
```

```powershell
.venv\Scripts\python.exe -m pytest tests `
  --basetemp=F:\iot_design\.pytest-native-root\pc-yaml-final `
  -p no:cacheprovider
```

## Medical boundary

This product provides risk prompts and care-seeking reminders, not diagnosis.
Arm weakness is not measured separately because of the mirror field of view;
an external wearable would be required to add it. Tongue deviation is an
auxiliary observation and has no single-item veto. If sudden FAST/BE-FAST
symptoms occur, call 120 immediately regardless of the displayed score or
cloud availability.
