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

## Current evidence (2026-07-11)

- Production firmware was built twice successfully; the app is `0xe4470` and
  has approximately 55% free space in the 2 MB app partition.
- COM3 was identified as an ESP32-S3 N16R8 with 8 MB PSRAM and 16 MB flash.
- The production image was written with verified hashes after clearing NVS.
- Boot telemetry confirmed E1 version, local CSI score production, and the
  CSI-only `insufficient` fusion result while Wi-Fi and MQTT were unavailable.
- Cloud end-to-end acceptance remains blocked until a reachable 2.4 GHz Wi-Fi
  network and reachable VPS MQTT/FastAPI services are available.
