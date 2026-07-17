# Fusion-gated AI advice

## Goal

Only generate and display AI advice after the device has produced a valid
fusion result. An advice remains visible for at most five minutes unless a new
guided screening starts first.

## Backend rules

- Every valid uplink is still cached and written to InfluxDB.
- An uplink with `level == "insufficient"` never schedules the advisor and
  never publishes an advice downlink.
- `normal`, `warning`, and `danger` uplinks may generate advice under the
  existing rate and newest-payload controls.
- Advice expires 300 seconds after its server generation timestamp.
- Starting screening through the web API immediately invalidates cached,
  pending, and in-flight advice from the previous screening.
- A device-originated transition into screening stage `1` applies the same
  invalidation, so the rule is not limited to the web button.
- An in-flight generation invalidated by a new screening must not be cached,
  published to MQTT, or written as current advice.

## Frontend rules

- The REST and WebSocket device responses omit expired or invalidated advice.
- When advice is omitted, the page displays `等待形成新的融合评分` and clears
  its source and generation time.
- Continuous `insufficient` uplinks do not hide an otherwise valid advice
  during its five-minute lifetime.

## Safety and privacy

The change does not alter the numeric-only cloud contract. Raw audio, images,
landmarks, MFCC arrays, and eye trajectories remain local. Advice remains a
risk reminder and does not represent a diagnosis.

## Verification

- `insufficient` uplinks perform no advisor call and no downlink publish.
- A valid fused uplink generates and exposes advice.
- The advice remains visible at 300 seconds and disappears after 300 seconds.
- Starting a new screening immediately hides old advice.
- An older in-flight generation cannot reappear after screening starts.
