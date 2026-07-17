# Edge Speech Screening Design

## Goal

Add a preliminary FAST Speech (`S`) risk feature to the standalone N16R8
mirror using the installed NMO432 microphone. The implementation must work
without a PC, keep raw audio local, and remain explicit that it is an
unevaluated acoustic heuristic rather than a diagnostic model.

The guided phrase is `今天的天气很好`. The device measures whether a usable
utterance was captured and derives a repeatable acoustic clarity score. It
does not perform speech-to-text, identify the speaker, diagnose dysarthria, or
claim clinical sensitivity or specificity.

## Scope

Included:

- 16 kHz mono NMO432 capture on the N16R8.
- A bounded RAM audio window associated with one guided screening session.
- Signal-quality gating and low-cost time/frequency-domain features.
- A preliminary `speech` score and `p_clear` value for the existing score bus.
- Numeric-only MQTT uplink and existing web display.
- Unit, integration, privacy, and hardware acceptance tests.

Excluded:

- PCM, MFCC, spectrogram, or other raw/derived audio upload.
- Automatic speech recognition or phrase-content verification.
- CNN inference until a versioned, evaluated INT8 model exists.
- Clinical threshold calibration and medical-performance claims.
- MAX98357A playback; the web or existing local indication provides the prompt
  during this milestone.

## Architecture

`audio_nmo432` remains the sole I2S owner. It feeds fixed 20 ms blocks to a new
`speech_screening` component through an in-process function call. The speech
component owns session state, feature accumulators, quality gates, and result
generation. It never exposes PCM outside the firmware process.

The main controller starts speech capture when the camera coprocessor reaches
`SG_STAGE_DONE`. The speech stage lasts up to four seconds and waits for an
initial voiced region before accumulating an utterance. Completion writes a
valid result through `sg_score_bus_set_speech`; invalid capture leaves S
unavailable and records a retry reason. Cancellation resets all speech state
and buffered samples.

The existing camera stage protocol is not renumbered. Speech is represented by
main-controller session state only. No new MQTT field is added: clients infer
completion from whether the authoritative `scores.speech` value is present.

## Feature Pipeline

Audio is processed in 20 ms frames. Calculations use fixed-size buffers and
bounded accumulators suitable for ESP32-S3 RAM and CPU constraints.

1. Remove frame DC offset before feature calculations.
2. Compute RMS, peak, clipping ratio, and zero-crossing rate.
3. Estimate a startup noise floor from quiet frames with a bounded adaptive
   update.
4. Mark voice-active frames using energy above the noise floor plus hysteresis.
5. For active frames, accumulate:
   - voiced-frame ratio;
   - normalized short-time energy variation;
   - zero-crossing statistics;
   - low/mid/high band energy from a small fixed FFT or equivalent filter-bank;
   - spectral change between adjacent active frames;
   - pause and longest-contiguous-voice durations.

The implementation must be deterministic and saturate intermediate integer
operations. Floating point is acceptable for final normalization because the
ESP32-S3 has hardware floating-point support, but allocation is forbidden in
the per-frame path.

## Quality Gates

No S score is produced unless all quality gates pass:

- the I2S read stream is valid;
- clipping stays below the existing five-percent block limit;
- a minimum amount of voiced audio is present;
- the utterance is neither too short nor dominated by silence;
- signal level exceeds the measured noise floor by a configurable margin;
- enough valid frames exist to calculate every required feature.

Threshold constants are engineering defaults, not medical thresholds. They
must be named, documented, and changed only from measured local recordings.
Failed quality returns one stable reason such as `no_voice`, `too_short`,
`too_quiet`, or `clipped`; it does not return zero.

## Preliminary Score

Each accepted feature is normalized to `[0, 1]` and combined into
`p_clear`. The initial weighting emphasizes capture continuity and usable
speech dynamics while assigning smaller weight to spectral distribution.
`speech = round(100 * p_clear)` and both values are clamped to their contracts.

This score means "similarity to the locally defined clear-utterance acoustic
pattern," not probability of being medically normal. Until an evaluated model
replaces it:

- heuristic S participates in the weighted fusion only after quality passes;
- heuristic S must not trigger the speech single-item danger veto;
- the firmware version and local diagnostic log must identify the preliminary
  heuristic implementation;
- UI copy uses `初赛声学筛查`, not `CNN`, `诊断`, or `构音障碍检测`.

When a versioned evaluated model is later installed, its output can use the
existing speech-veto contract only after threshold validation.

## Data And Privacy

Only these speech-derived values may cross the device boundary under the
existing contract:

- `scores.speech`;
- the existing final score and level.

`p_clear` remains inside the local fusion input and is not added to MQTT.

PCM, encoded audio, MFCC arrays, FFT bins, utterance fingerprints, and voice
embeddings are prohibited from USB production frames, MQTT, InfluxDB, logs,
and LLM requests. Diagnostic logs may contain aggregate RMS, peak, frame counts,
and non-sensitive failure codes.

## Failure Handling

- Silence or invalid capture: leave S unavailable and ask for another reading.
- I2S timeout: abort the current speech capture without affecting F/T/E/CSI.
- User cancellation: clear active accumulators and publish no partial result.
- Network outage: local scoring and fusion continue; the latest numeric result
  can be uploaded after reconnection under existing MQTT behavior.
- Insufficient available fusion weight: retain the existing `insufficient`
  level rather than inventing a normal result.

## Testing

Host-side unit tests exercise the feature logic with deterministic synthetic
PCM fixtures: silence, low-level noise, speech-like multi-tone modulation,
continuous pure tone, clipping, short utterance, and interrupted utterance.
Tests verify availability decisions, stable failure reasons, score bounds, and
that speech-like input scores above invalid controls without asserting medical
accuracy.

Static privacy tests reject PCM, MFCC, FFT arrays, or encoded audio in cloud
serialization. Integration tests verify score-bus freshness, fusion without a
heuristic speech veto, cancellation, retry, and numeric-only MQTT output.

Hardware acceptance on COM3 compares quiet, normal near-field reading, and
far-field reading of the fixed phrase. Acceptance requires repeatable quality
gating, changing aggregate features, no resets, and no raw audio leaving the
device. Exact score ranges and latency will be measured after recordings are
collected under the final enclosure and microphone placement; the project must
not state values before that measurement.

## Medical Boundary

The feature supports FAST-style risk prompting but is not a diagnostic device.
Users must call 120 immediately for sudden facial droop, unclear speech,
one-sided weakness, visual or balance changes, or altered consciousness,
regardless of the device result. Arm weakness is not independently measured by
the mirror. Tongue analysis remains auxiliary only.
