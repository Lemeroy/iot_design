# Face Asymmetry and Tongue Incomplete Design

## Goal

Improve the ESP-WHO five-point face score for an upright face with one-sided
mouth-corner droop, and make an uncompleted tongue action explicit without
inventing a tongue score.

## Face F

The camera keeps the existing five-point order: left eye, left mouth corner,
nose, right eye, right mouth corner. Geometry derives three independent
signals normalized by eye distance: mouth-line angle relative to the eye line,
left/right mouth-corner height difference after eye-line compensation, and
nose-to-corner distance asymmetry. Each signal is converted to a descending
0..100 score. The frame F score is the minimum of these scores, then the
existing baseline/output median is applied. This keeps a focal mouth droop
visible even when one geometric signal is weak.

The algorithm remains a screening prompt, not a diagnosis. Head roll remains a
quality/repositioning failure, and no clinical accuracy is claimed.

## Tongue T

During the tongue stage, no tongue component remains `valid=false` after the
stage times out. The camera publishes `stage=error`; N16R8 keeps T unavailable,
so fusion excludes T instead of treating it as zero or a random value. The web
monitor displays `舌部动作未完成，T 未计入融合` for that incomplete result.

## Verification

- Add face regression coverage for a one-sided mouth-corner drop that lowers F.
- Add source/firmware coverage proving tongue timeout keeps T unavailable.
- Run focused tests, the full host suite, both ESP-IDF production builds, and
  real-device checks on camera COM9 and main COM3.
