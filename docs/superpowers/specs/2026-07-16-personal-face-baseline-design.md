# Personal Face Baseline Design

## Goal

Make the camera-side FAST Face risk feature respond to visible mouth changes
in real time by comparing each user with a short-lived neutral baseline. The
baseline and all landmarks remain in camera RAM and are never uploaded.

This is a personalized engineering change indicator, not a diagnosis or a
validated probability of stroke.

## State Machine

The camera owns three states:

1. `WAITING`: no usable face; F is unavailable.
2. `CALIBRATING`: collect five consecutive high-quality neutral samples; F is
   unavailable and does not enter fusion.
3. `READY`: score each valid frame relative to the stored baseline and publish
   a rolling three-frame median.

Any failed geometry gate during calibration clears the calibration window.
In `READY`, short invalid gaps retain the baseline but do not publish new F.
Ten continuous seconds without valid geometry clears the baseline and returns
to `WAITING`, so a new user receives a new baseline.

## Baseline Acceptance

Every calibration sample must have geometry quality at least 70. Five samples
are accepted only when their mouth-angle range is at most 2 degrees and their
corner-asymmetry range is at most 0.03. The baseline is the median mouth angle
and median corner asymmetry of those samples.

The baseline is volatile. It is not written to flash, NVS, logs, MQTT,
InfluxDB, or the LLM request.

## Relative Score

For each valid frame in `READY`:

```text
angle_delta = abs(frame_angle - baseline_angle)
asymmetry_delta = abs(frame_asymmetry - baseline_asymmetry)
```

The angle subscore is 100 at `angle_delta <= 0.5` degrees, 0 at
`angle_delta >= 8` degrees, and linear between those limits. The distance
subscore is 100 at `asymmetry_delta <= 0.01`, 0 at
`asymmetry_delta >= 0.15`, and linear between those limits.

```text
F = round(0.75 * angle_subscore + 0.25 * distance_subscore)
```

The published result is the median of the latest three valid relative scores,
signed absolute mouth angles, and quality values. The existing absolute mouth
angle remains on the wire so the `abs(angle) > 20` danger veto is unchanged.
The expected response time is approximately 1–2 seconds and must be reported
as measured rather than guaranteed.

## Interfaces

The four-byte I2C register `0x02` remains unchanged:

```text
[status, relative_F_score, signed_absolute_mouth_angle, quality]
```

`status=0` covers waiting, calibration, invalid geometry, and stale output.
`status=1` means a stable relative score is available. No raw baseline or
landmark values cross I2C.

The cloud numeric contract remains unchanged. Before readiness, `face` is
`null`; after readiness, it is the relative score. Speech, tongue, and eye
remain unavailable in this increment.

## Safety And Limitations

- The user must look naturally at the camera during initial calibration.
- Starting with a deliberately asymmetric expression can create a misleading
  baseline; the mirror must prompt the user to relax and face forward.
- Five-point landmarks are designed primarily for alignment and remain less
  sensitive than an evaluated dense-landmark model.
- Lighting, expression, pose, occlusion, and natural asymmetry can affect the
  score.
- A user with FAST symptoms should call emergency services immediately and
  must not wait for calibration or rely on the score.

## Verification

Automated tests cover baseline sample count, quality rejection, stability
range rejection, median baseline values, relative score boundaries,
three-frame median behavior, brief invalid gaps, and ten-second reset.

Hardware acceptance has three measured phases with one user and fixed camera
position:

1. Natural frontal face until baseline becomes ready.
2. Deliberately lower one mouth corner and verify F changes materially within
   the measured response interval.
3. Return to the natural expression and verify F moves back toward its
   baseline range.

COM3 and VPS must report numeric values from the same phase. No target score
range is claimed before measured behavior is observed.
