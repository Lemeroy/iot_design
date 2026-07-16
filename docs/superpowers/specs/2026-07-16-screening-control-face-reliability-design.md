# Screening Control and Face Reliability Design

## Goal

Make guided screening start reliably under continuous I2C polling and make the
F stage tolerant of ordinary detection jitter without inventing a healthy
score. This is an initial-competition reliability change, not a diagnostic
performance claim.

## Confirmed Failure

The public web command reached the N16R8 as an MQTT control downlink, but the
camera stage remained idle. The camera target currently sends register-select,
read-request, and screening-control events through the same eight-item queue.
Continuous polling can fill that queue, and callback enqueue failures are not
reported. A start command can therefore be lost before face processing begins.

## I2C Control Design

The camera I2C receive callback handles a valid two-byte control write as a
separate bounded latch. It does not enqueue that write with ordinary register
traffic. The latch stores only the latest `start` or `cancel` action and is
consumed by the camera application loop. Register selection and read requests
retain their existing queue and response protocol.

The N16R8 records a pending control after a successful I2C write. It confirms
success only after the polled stage changes to the expected state:

- `start` expects `FACE`;
- `cancel` expects `IDLE`;
- confirmation is bounded and retried a small fixed number of times;
- failure leaves scores unavailable and logs an error without credentials or
  biometric data.

The MQTT, I2C register, and numeric uplink contracts remain unchanged.

## Face Stage Design

F remains based on ESP-WHO five-point landmarks and a volatile personal neutral
baseline. A frame is eligible only when it has one selected face, valid five
points, acceptable geometry quality, and a sufficiently large frontal face.

The detector uses balanced proposal/landmark thresholds of `0.40` and `0.45`.
The stage requires at least two eligible samples in the latest five sampled
frames rather than merely elapsed wall time. Its overall deadline is 20 seconds
so an absent face cannot leave screening running indefinitely. Stable
eligible samples feed the existing median/baseline path; invalid or stale input
clears F instead of emitting `100`.

The preview may retain the last bbox for at most two missed frames to avoid
visual flicker. A retained bbox is display-only and never makes landmarks,
baseline input, or F valid.

The F result must continue to change with measured relative mouth geometry.
No score is produced from a bounding box alone, and no fallback constant is
allowed.

## Status and Diagnostics

The camera logs bounded, non-biometric reason counters for rejected F samples:
no face, invalid landmarks, geometry quality, or baseline pending. It logs
control receipt and stage transitions. The N16R8 logs control confirmation or
bounded failure.

The existing public stage value remains the wire contract. The web UI maps
active F progress to concise prompts such as detecting face, aligning face, and
building baseline when that information is locally available; otherwise it
uses the existing F-stage prompt. A terminal error never displays a numeric F.

## Privacy and Medical Boundaries

Images, bounding boxes, landmarks, baseline geometry, and rejection details
remain on the camera/N16R8. MQTT, InfluxDB, the VPS, and the LLM receive only
numeric scores, availability, stage, level, profile fields already permitted by
the contract, and advice text. F is a risk-screening signal, not a diagnosis.

## Tests

Host tests cover:

- control writes bypass the ordinary event queue and latest action wins;
- start/cancel confirmation retries are bounded;
- F requires two eligible samples in a five-frame window;
- intermittent invalid frames do not create a score;
- no face reaches error at the overall deadline;
- stale F is cleared and never defaults to `100`;
- cloud payloads remain numeric-only.

Target verification builds both firmware projects, flashes COM4 then COM3, and
checks: MQTT control reception, camera `FACE` acknowledgement, visible stage
progress, changing F from real landmarks, failure with the lens obscured, and
continued CSI/MQTT operation.
