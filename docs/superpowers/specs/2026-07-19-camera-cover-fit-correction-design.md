# Camera And Rear-Cover Fit Correction Design

## Problem

The first physical print exposes two reproducible interferences:

- the camera module cannot enter the two side guides because their current
  `28.2 mm` nominal opening is too narrow for the real `27 mm` board after
  printing tolerance;
- the installed `19 mm` deep camera module reaches the front-panel retention
  area, while the rear-cover pressure posts extend about `4.8 mm` farther than
  the intended tray plane and prevent the cover from seating.

## Approved Geometry

- Set the camera-guide clear opening to `30 mm`.
- Continue using cable ties as the positive camera restraint; the guides only
  locate the module and do not rely on a press fit.
- Move the complete electronics tray from `Y=0 mm` to `Y=2 mm`, toward the rear
  cover, to recover front-panel clearance for the `19 mm` module depth.
- Recompute pressure-post length from the installed rear-cover inner face to
  the shifted tray plane and leave a nominal `0.5 mm` assembly gap.
- Keep the five-part production structure and all external dimensions.

## Validation

Tests must lock the `30 mm`, `2 mm`, and `0.5 mm` parameters, verify that the
pressure-post endpoint is derived from both rear-cover thicknesses, and retain
all existing watertightness, component-count, envelope, and unsupported-area
checks. OpenSCAD outputs and assembly renders must be regenerated.

Physical fit remains the final authority. The updated clearances are prototype
CAD values based on the reported first print and are not production tolerances.

