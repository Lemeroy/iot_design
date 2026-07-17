# Continuous F/S/E Monitoring Design

## Goal

Make face (`F`), preliminary speech (`S`), and eye movement (`E`) continuously
available when their physical inputs are usable. Guided screening remains for
the higher-confidence center/left/right eye sequence and tongue extension.
The mirror continues to work without a PC, and raw audio/video remains local.

## User Experience

The authenticated web monitor defaults to `持续监测中`. F, S, and E update
without pressing Start. A missing or expired measurement displays `待采集`, not
zero. Start launches the existing guided F/E/T sequence; it does not start or
stop continuous S.

During a guided sequence the page retains the existing face, gaze, and tongue
instructions. A completed guided E result takes priority for 30 seconds. T is
still measured only during the tongue prompt. Cancel stops only the guided
camera sequence; continuous F/S/E continues.

## Face F

The camera coprocessor continues to produce F from ESP-WHO five-point geometry
whenever bbox and landmarks pass quality checks. The N16R8 stores the latest
valid F and mouth angle for five seconds after face loss. A new valid face
refreshes this timer.

After five seconds without a valid face, F becomes unavailable. A camera I2C
failure clears F immediately because transport failure cannot be treated as a
brief detector miss. The retained value is never presented as a new sample.

## Speech S

NMO432 capture and the preliminary acoustic engine run continuously after
audio initialization. The engine processes consecutive, non-overlapping
four-second windows. This keeps CPU and RAM bounded and produces a new result
often enough for the existing five-second score freshness limit.

Each window starts with local noise-floor estimation, then applies the existing
quality gates and heuristic features. A valid voiced window writes S with
`speech_veto_eligible=false`. A silent, too-short, too-quiet, clipped, or I/O
failed window clears the previous S instead of writing zero. The next window
starts automatically.

Continuous capture does not mean continuous storage. PCM blocks are consumed
in RAM and discarded. PCM, encoded audio, MFCC, FFT bins, voice embeddings,
and utterance fingerprints are prohibited from USB production frames, MQTT,
InfluxDB, logs, and LLM requests. Diagnostic logs contain only aggregate
quality values and bounded reason codes.

## Eye E

Whenever the camera has a current bbox and valid five-point landmarks, it runs
the existing pupil measurement for both eyes, independent of guided stage.
A bounded rolling tracker consumes valid measurements and estimates:

- average per-eye measurement quality;
- bilateral movement coherence;
- disagreement between left/right normalized displacement;
- temporal stability with brief blink tolerance;
- usable-sample ratio.

The continuous score is an initial tracking/coordination feature. It does not
measure visual fields and does not diagnose gaze palsy. Invalid landmarks,
implausible pupil regions, prolonged eye dropout, or insufficient rolling
samples make continuous E unavailable rather than healthy.

The existing center/left/right sequence remains the guided E algorithm. After
successful completion, its result overrides continuous E for 30 seconds. The
camera then returns to the rolling continuous result. Starting a new guided
session clears the previous guided override.

## Fusion Safety

Continuous F uses the existing face veto only while its five-second retained
sample is fresh. Preliminary S contributes to weighted fusion but cannot use
the speech single-item veto.

Continuous natural-eye E contributes to weighted fusion but cannot by itself
upgrade a normal result to warning. Guided E is also treated as an unevaluated
initial feature until measured validation exists; no sensitivity, specificity,
or clinical threshold claim is made. The existing final weighted formula is
unchanged.

T remains auxiliary and guided only. Arm weakness remains unmeasured by the
mirror.

## State And Interfaces

No raw-media or new cloud payload is introduced. The existing nullable numeric
fields remain authoritative:

```json
{"scores":{"face":null,"speech":null,"tongue":null,"eye":null,"csi":52,"final":0}}
```

The camera I2C score registers keep their existing sizes. Source precedence is
resolved on the camera board before E is encoded: a fresh guided result wins;
otherwise the continuous rolling result is returned. The N16R8 does not need a
new wire field to distinguish them because neither source is currently allowed
to trigger an E-only warning.

## Timing

- Camera polling remains 500 ms on the N16R8.
- F retention changes from two seconds to five seconds.
- S uses four-second non-overlapping windows and the existing five-second score
  freshness rule.
- Continuous E uses a bounded rolling window sized in valid samples, not
  unbounded history.
- Guided E overrides continuous E for 30 seconds.

These are engineering timing choices. End-to-end latency and score ranges are
reported only after hardware measurement.

## Failure Handling

- Camera transport failure: clear F/E/T immediately; S and CSI continue.
- Face detector miss under five seconds: retain F, but continuous E follows its
  own valid-sample/dropout rules.
- No speech in a four-second window: clear S and immediately begin the next
  window.
- Audio I/O failure: clear S, log a reason code, and retry capture without
  affecting camera or CSI tasks.
- Guided E/T failure: publish the existing screening error while continuous
  F/S/E continues; no failed guided value replaces a valid rolling result.
- Network outage: all local sensing and fusion continues; only numeric results
  are uploaded after MQTT reconnection.

## Testing

Unit tests cover five-second F retention and immediate transport clearing;
continuous speech auto-restart, valid update, and clearing after invalid
windows; rolling E quality, coherent motion, discordant motion, blink dropout,
and insufficient samples; guided E 30-second priority and expiry.

Integration tests verify continuous sensing without a start command, guided
camera controls do not stop S, no E-only warning is produced, score freshness
expires correctly, and cloud serialization remains numeric-only. Hardware
acceptance uses COM3/COM4 plus the VPS page to observe face enter/leave, quiet
and spoken audio windows, natural eye movement with bbox present, guided gaze,
and camera/audio disconnection.

## Medical Boundary

This product provides risk prompts and medical-attention reminders, not a
diagnosis. Sudden facial droop, unclear speech, one-sided weakness, visual or
balance changes, or altered consciousness requires calling 120 immediately,
regardless of device output. Continuous monitoring must not delay emergency
care or be described as clinical surveillance.
