# Guided Eye And Tongue Screening Design

## Goal

Add a guided preliminary-contest screening flow that computes eye-movement (E)
and auxiliary tongue-deviation (T) scores locally on the GC2145 camera board.
The web demo starts the flow and displays progress, numeric results, and cloud
advice. Raw images, image regions, and landmarks never leave the local device.

This feature provides risk prompts only. It is not a diagnosis. Tongue
observation is an auxiliary reference and never acts as a single-item veto.

## User Flow

The user starts a screening from the authenticated VPS demo page. The VPS sends
a small MQTT control message to the N16R8. The N16R8 writes a start command to
the camera board over I2C. The camera board advances through these stages:

1. Neutral frontal face and F baseline: approximately 3 seconds.
2. E center gaze: approximately 2 seconds.
3. E left gaze: approximately 2 seconds.
4. E right gaze: approximately 2 seconds.
5. T mouth open with tongue extended: approximately 3 seconds.
6. Complete or retry.

The total target duration is about 12 seconds. These durations are preliminary
engineering defaults and must be measured on the real device. Each stage needs
three consecutive quality-accepted samples. A timeout or invalid image produces
a retry state, not a healthy score.

## Architecture

### Camera coprocessor

The camera board retains ESP-WHO five-point face detection and the volatile F
baseline. It uses the RGB888 frame already produced for face detection to run
two bounded, fixed-storage image algorithms:

- Eye ROI pupil-centroid tracking for E.
- Lower-face color segmentation and connected-component geometry for T.

No additional model or training weight is required. The camera board owns the
screening state machine and exposes progress and numeric results through I2C.

### N16R8 main controller

The N16R8 receives a screening start/cancel command through its existing MQTT
connection, forwards the command to the camera board over I2C, polls stage and
F/E/T values, performs the existing local fusion, and uploads numeric values and
stage only. Offline local fusion remains available. Missing modalities remain
missing and are never replaced with 100.

### VPS web application

The authenticated demo page provides one Start Screening command, displays the
current guided stage, and shows resulting F/E/T values. Existing WebSocket
delivery with five-second polling fallback remains in place. The cloud and LLM
receive only numeric scores, stage, and the permitted user profile.

## I2C Contract

Existing register `0x02` remains unchanged:

| Register | Direction | Four-byte payload |
|---|---|---|
| `0x02` | Camera to N16R8 | F: `[valid, score, signed_angle, quality]` |
| `0x03` | Camera to N16R8 | E: `[valid, score, gaze_diff, quality]` |
| `0x04` | Camera to N16R8 | T: `[valid, score, signed_offset, quality]` |
| `0x10` | N16R8 to camera | Control: `start` or `cancel` |
| `0x11` | Camera to N16R8 | Stage: `idle/F/E-center/E-left/E-right/T/done/error` |

All scores and quality values use `0..100`. Signed offset is a bounded signed
percentage of face width. `valid=0` means the remaining score fields must not be
used. Exact command and stage byte constants are defined once in the shared
camera protocol header and consumed by both firmware projects.

## MQTT Extension

The downlink accepts this additional message without changing the existing LLM
advice payload:

```json
{"type":"screening_control","action":"start"}
```

Cancel uses `"action":"cancel"`. Uplink messages retain the existing numeric
scores and add a bounded screening stage field. No image, audio, ROI, landmark,
or personal F baseline data is permitted in either direction.

## E Algorithm

The five ESP-WHO landmarks do not include iris landmarks. E therefore uses
local image evidence rather than treating eye centers as gaze:

1. Derive left and right eye ROIs from detected eye centers and inter-eye
   distance, corrected for eye-line roll.
2. Convert each ROI to intensity and apply an adaptive dark-pixel threshold.
3. Reject ROIs with insufficient contrast, implausible dark area, closure, or
   strong reflection contamination.
4. Compute each pupil candidate's horizontal centroid relative to its eye ROI.
5. Establish the center stage baseline.
6. During left and right stages, require both pupils to move in the expected
   common direction with sufficient travel.
7. Score from binocular movement disagreement, travel adequacy, and temporal
   stability. Publish only after three accepted samples per stage.

This is a guided ocular-movement risk prompt inspired by BE-FAST Eyes. It does
not measure visual-field loss or diagnose ocular palsy. Glasses, eyelid closure,
head rotation, and poor illumination can make the result unavailable.

## T Algorithm

T is evaluated only during the explicit tongue stage:

1. Correct the face coordinate system using eye-line roll.
2. Derive a lower-face ROI from the nose, mouth corners, and face box.
3. Select pixels using configurable red-dominance and saturation thresholds.
4. Find the largest plausible connected component and reject insufficient area,
   border contact, implausible aspect ratio, or unstable masks.
5. Estimate the tongue centerline and tip-side centroid relative to the
   roll-corrected facial midline.
6. Convert the signed offset ratio to an auxiliary `0..100` score and publish
   only after three accepted samples.

Lipstick, warm lighting, skin tone, mouth interior, and partial tongue exposure
can affect segmentation. Thresholds are engineering defaults pending real-device
calibration. T never triggers danger by itself.

## State And Error Handling

- Start clears prior E/T samples and begins a new RAM-only session.
- Cancel immediately returns to idle and invalidates incomplete E/T results.
- Loss of a valid face pauses the current stage briefly; stage timeout produces
  error/retry and invalid scores.
- A new start command recovers from complete or error without rebooting.
- I2C or MQTT failure does not invent results. N16R8 retains local operation and
  reports unavailable cloud connectivity separately.
- Only one screening session runs at a time. Duplicate start commands restart
  the guided sequence deterministically.

## Testing And Acceptance

### Automated tests

- Pure image-kernel tests use synthetic RGB fixtures for centered, conjugate,
  and discordant pupil positions.
- Tongue tests cover centered, left/right offset, insufficient area, and absent
  tongue masks.
- State-machine tests cover stage order, three-sample gating, timeout, cancel,
  duplicate start, and invalid-result behavior.
- Shared protocol tests verify all register payload sizes and constants.
- Host tests verify MQTT and web payloads contain numeric data only.

### Hardware acceptance

- COM4 completes the guided sequence and publishes measured F/E/T values.
- COM3 reads all camera registers and uploads the same numeric values through
  MQTT.
- The VPS page starts a session, shows each stage in real time, displays retry
  on invalid capture, and shows the resulting Doubao advice.
- Disconnecting or obscuring the camera produces unavailable/retry, never an
  automatic score of 100.

No sensitivity, specificity, latency, or medical accuracy claim is accepted
until measured with an explicitly documented evaluation set.
