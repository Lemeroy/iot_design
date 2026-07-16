# ESP-WHO Five-Point Face Score Design

## Goal

Add a real, locally computed FAST Face (F) risk feature to the camera
coprocessor. The feature uses the five landmarks already produced by the
ESP-WHO face detector, sends only numeric results to the N16R8 controller,
and never uploads images or landmarks.

This is a preliminary-contest engineering risk indicator. It is not a
diagnosis of facial palsy or stroke, and its thresholds require later
calibration with consented samples and K-fold evaluation.

## Scope

This increment implements F only. Speech (S), auxiliary tongue deviation
(T), and eye movement (E) remain unavailable until their own reviewed
increments. The existing face bounding-box preview and I2C register remain
available for debugging.

## Architecture

The GC2145 camera board remains the owner of all image processing. For the
largest detected face, it reads ESP-WHO's five landmarks in this order as
provided by the detector result: two eyes, nose tip, and two mouth corners.
A focused geometry module validates the landmarks, computes face asymmetry,
and feeds a five-sample temporal median. The camera I2C target exposes the
stable numeric result to the N16R8 controller.

The N16R8 polls the numeric F register, validates the response, and calls the
existing `sg_score_bus_apply_camera()` interface. It uses the absolute mouth
angle because the existing fusion veto compares angle magnitude. Invalid or
stale observations reset F to unavailable rather than substituting a healthy
score.

## Landmark Quality Gate

An observation is valid only when all of these checks pass:

- exactly five landmark pairs are available;
- the selected face width is at least 64 pixels in the 320x240 frame;
- inter-eye distance is at least 20 pixels;
- both mouth corners and the nose tip are inside the selected face box;
- the nose horizontal position lies within the middle 50% of the eye span;
- the mouth midpoint lies below the eye midpoint;
- the absolute eye-line roll is at most 25 degrees.

Failure of any check produces an unavailable F observation. These limits are
initial engineering values and must be exposed as named constants, not
presented as validated medical thresholds.

## Geometry And Score

The geometry module computes:

1. `eye_angle = atan2(right_eye.y - left_eye.y, right_eye.x - left_eye.x)`.
2. `mouth_angle = atan2(right_mouth.y - left_mouth.y,
   right_mouth.x - left_mouth.x) - eye_angle`, normalized to `[-90, 90]`.
3. `corner_asymmetry = abs(distance(nose, left_mouth) -
   distance(nose, right_mouth)) / (distance_left + distance_right)`.

The angle subscore is 100 at `abs(mouth_angle) <= 2` degrees, 0 at
`abs(mouth_angle) >= 20` degrees, and linearly interpolated in between. The
distance subscore is 100 at `corner_asymmetry <= 0.05`, 0 at
`corner_asymmetry >= 0.35`, and linearly interpolated in between.

The frame score is:

```text
F = round(0.75 * angle_subscore + 0.25 * distance_subscore)
```

The camera retains the latest five valid frame scores and signed mouth
angles. It publishes the median score and median angle only after five valid
samples. A failed quality gate clears the accumulation so samples from
different face presentations are not mixed. Score and quality are bounded to
`0..100`; signed angle is rounded and saturated to `-90..90` degrees.

## I2C Protocol

The slave address remains `0x52`.

- Register `0x01` remains the four-byte bbox response
  `[center_x, center_y, width, height]`.
- Register `0x02` is the four-byte F response
  `[status, score, signed_angle_i8, quality]`.

`status=1` means the remaining fields are valid. `status=0` means F is
unavailable and the other bytes must be ignored. `quality` is an engineering
quality score derived from face size, eye distance, and pose margins; it is
for observability and does not enter medical fusion in this increment.

All protocol structs are packed and statically asserted to four bytes. The
shared protocol parser rejects wrong lengths, unknown status values, scores
above 100, quality above 100, and angles outside `-90..90`.

## Fusion And Safety

The N16R8 applies a valid response with:

```c
sg_score_bus_apply_camera(true, score, fabsf(angle_deg),
                          false, 0, false, 0, now_us);
```

The existing fusion behavior remains authoritative: `face < 30` or absolute
mouth angle above 20 degrees can trigger the danger veto. The device must not
derive tongue or eye scores from the five face landmarks in this increment.

Five-point geometry is sensitive to natural facial asymmetry, expression,
camera pose, occlusion, and detector error. The UI and documentation continue
to describe the result as a risk prompt and care-seeking reminder. A user with
FAST symptoms should call emergency services immediately and must not wait for
or rely on the device score.

## Error Handling

- No face or failed quality gate: clear the five-frame accumulator and expose
  `status=0`.
- Malformed I2C response: N16R8 marks F unavailable and logs a bounded warning.
- Camera response older than the existing stale timeout: F becomes
  unavailable.
- I2C failure: local CSI and other available modalities continue operating.
- USB preview remains request-gated and local; no new image transport is
  introduced.

## Verification

Automated verification covers:

- level eyes and level mouth produce a high score;
- mouth-corner displacement lowers the score and reports the expected signed
  angle;
- equal head roll applied to eyes and mouth is removed by roll correction;
- side-pose, small-face, incomplete-landmark, and invalid geometry cases are
  rejected;
- five-sample median suppresses one outlier and resets after an invalid frame;
- register `0x01` remains backward compatible;
- register `0x02` encoding and parsing reject malformed values;
- N16R8 publishes a valid F score and leaves S/T/E unavailable;
- both ESP-IDF projects build and the complete host test suite passes.

Hardware acceptance uses COM4 camera logs and COM3 controller logs. With a
well-lit frontal face held steady for five valid frames, COM3 must report a
numeric F score and signed mouth angle. Removing the face must return F to
unavailable after the existing stale interval. Threshold accuracy,
sensitivity, and specificity remain pending measured evaluation.
