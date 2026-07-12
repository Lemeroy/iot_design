# E1 Standalone Mirror Bring-up

## Scope and safety boundary

E1 runs deterministic fusion, local risk prompts, and MQTT directly on the
ESP32-S3. A PC is optional for flashing and observation; disconnecting it must
not stop the mirror's local fusion loop. The device is a risk prompt and
care-seeking reminder, not a diagnostic device.

Only numeric scores, fusion level, limited profile fields, timestamps, and
advice text may leave the device. JPEG, audio, MFCC, landmarks, ROIs, and any
other reconstructable biometric data must never be published to MQTT.

## Required configuration

1. Use a WPA2-capable **2.4 GHz** Wi-Fi network. ESP32-S3 cannot join a 5 GHz
   SSID. A 20 MHz channel is preferred for CSI repeatability.
2. In `idf.py menuconfig`, set `StrokeGuard M1a/M1b Config` values for Wi-Fi,
   device ID, broker URI, device MQTT username/password, and the limited
   profile defaults. Do not commit `firmware_esp32/sdkconfig`.
3. For the controlled-development deployment use `mqtt://<public-ip>:1883`.
   TLS, device-specific ACLs, and port 8883 are E6 production requirements.
4. Keep `STROKEGUARD_LEGACY_USB_STREAM` disabled. USB is diagnostic telemetry,
   not a runtime score input.
5. Set a random `STROKEGUARD_MANAGER_TOKEN` only in the ignored local
   `sdkconfig`. The PC stores the matching value in the operating-system
   credential store, never in YAML.

Before flashing a changed factory configuration, clear only the NVS partition
(`0x9000`, length `0x6000`) or provision a valid updated NVS blob. E1 validates
the stored configuration with a schema version and CRC, so old valid NVS data
takes precedence over newly compiled defaults.

## Build and flash

Target board: ESP32-S3-WROOM-1 N16R8 on `COM3`.

```powershell
cd firmware_esp32
idf.py build
idf.py -p COM3 flash monitor
```

The local Espressif installation may require its v5.5.3 Python virtual
environment instead of a system Python. Verify the final build reports an app
binary within the 2 MB factory partition before flashing.

## Acceptance checklist

### Offline path

1. Boot the board and confirm `boot fw=e1-0.5.0`.
2. Confirm periodic `fusion` telemetry continues with no PC score input.
3. With CSI as the only available modality, expect `level=insufficient` and
   `avail weight sum 0.08 < 0.50`. This is the honest E1 result, not a normal
   health result.
4. Disconnect the PC or block the WAN. Fusion and local alert logic must
   continue; failed MQTT connection attempts must not block the loop.
5. The Unity target tests verify that a face veto produces `danger` and cloud
   advice cannot lower a local `danger` level.

### Cloud path

1. Confirm the mirror receives a 2.4 GHz IP address, then wait for
   `mqtt connected`.
2. Confirm an uplink on `strokeguard/<device_id>/uplink` contains only the
   versioned numeric contract: `schema_version`, `seq`, `scores`, `level`,
   `profile`, `reasons`, `veto_by`, `device_id`, and `ts`.
3. Confirm FastAPI `/health` reports `status=ok`, `mqtt=true`, and
   `influx=true`.
4. Confirm `/devices/<device_id>/latest` contains a recent numeric uplink and
   a downlink with `schema_version=1`, a bounded `advice_text`, timestamp, and
   source.
5. Confirm an LLM failure sends the fixed fallback safety text rather than a
   provider error. Cloud advice cannot override the device's authoritative
   fusion level.

### LAN management path

1. Confirm serial output includes `GOT_IP address=<S3_LAN_IP>` and
   `manager API started`.
2. A GET without Bearer authorization must return `401`; an authenticated GET
   must return `200` without MQTT or management credentials.
3. PUT the current profile with the returned revision. It must return `200`
   and increment revision exactly once. Replaying the old request must return
   `409`.
4. Reboot the S3 and GET again. The accepted profile and revision must persist.
5. During all requests, confirm CSI/fusion telemetry continues. Closing the PC
   must not affect local fusion or alerts.

## Current evidence (2026-07-12)

- Production firmware built successfully at `0xee600`, with 53% free in the
  2 MB app partition. Values are build output, not estimated runtime usage.
- COM3 was identified as an ESP32-S3 N16R8 with 8 MB PSRAM and 16 MB flash.
- The production image was written with verified hashes after clearing NVS.
- Ten on-device Unity cases passed, covering local danger authority, fusion
  vetoes, NVS migration, revision updates, strict JSON parsing, Token matching,
  and credential-free responses.
- LAN black-box acceptance returned `401/200/200/409`; revision incremented,
  no credential fields appeared, and fusion continued during requests.
- The PC client/UI pulled and pushed a real profile through a separate QThread;
  full host regression passed 194 tests and visual QA covered 1220x820 and
  1024x720.
- The S3 joined 2.4 GHz Wi-Fi and produced local CSI/fusion continuously.
- Cloud acceptance is not complete: MQTT port 1883 accepted TCP but did not
  return CONNACK, while public FastAPI port 8000 timed out. Do not claim the
  VPS/LLM path as passing until remote services are repaired and retested.
