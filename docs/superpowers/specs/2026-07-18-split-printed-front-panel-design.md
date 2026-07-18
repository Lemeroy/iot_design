# StrokeGuard Split Printed Front Panel Design

## Goal

Add a printable front panel to the existing StrokeGuard desktop demonstrator
enclosure. The panel must fit a common 220 by 220 mm FDM build area, preserve
the centered camera opening, fit the existing enclosure rails, and avoid fixed
development-board dimensions.

## Selected approach

The front panel is divided horizontally into upper and lower printed parts. The
joint aligns with the enclosure's existing upper/lower shell split. This keeps
both panel parts near 208 by 147 mm and avoids requiring a 300 mm printer axis.

Alternatives considered were a one-piece printed panel requiring a larger
printer and a laser-cut DXF/SVG panel. The split FDM approach is selected because
it uses the same printer and transfer package as the enclosure while requiring
no additional fabrication process.

## Geometry

The assembled front panel uses the printable body width and existing retention
space. Its nominal visible envelope is approximately 208 mm wide by 294 mm
high. Exact dimensions remain derived from `body_width`, `body_height`, and
`wall` in OpenSCAD rather than being duplicated as unrelated constants.

The panel is split at the 150 mm shell boundary:

- `front_panel_lower` covers the lower half;
- `front_panel_upper` covers the upper half;
- the visible horizontal process gap is 0.30 mm;
- both outer edges remain 2.0 mm thick so they fit the existing nominal 2.4 mm
  panel slot.

The lower panel includes an integrated rear lap extending 8 mm behind the upper
panel. The lap stops short of both side retention rails. It prevents front/back
misalignment while leaving both front faces coplanar. The enclosure rails and
rear lap retain the parts without an exposed decorative strip or front-facing
fastener.

The upper panel retains the centered 36 by 22 mm camera opening at the existing
global position, approximately 276 mm above the body bottom. It remains
compatible with the replaceable camera bezel and adjustable camera carriage.

## Stiffening

Both parts use a 2.0 mm front skin plus rear ribs approximately 6 mm wide and
2 mm high. Ribs are located away from:

- the camera opening, bezel, and carriage adjustment area;
- side panel-retention rails;
- the shell joint fasteners;
- the lower NMO432 acoustic path;
- USB service windows and wiring routes.

The ribs improve flatness without increasing the edge thickness inserted into
the shell rails. They are not treated as a guarantee against warping; print
orientation, material, bed adhesion, and cooling still require a physical
trial.

## Model and export interfaces

OpenSCAD adds these manufacturing modules:

- `front_panel_upper_printable()`;
- `front_panel_lower_printable()`;
- `front_panel_assembled()`.

The entry point adds `part` values `front_panel_upper` and
`front_panel_lower`. The export script adds:

```text
stl/printable/front_panel_upper.stl
stl/printable/front_panel_lower.stl
```

The assembled and exploded renders include both parts. The display STL may use
the assembled front-panel silhouette, but printable geometry remains the
manufacturing authority.

## Verification

Automated checks require:

1. Both STL files exist, are non-empty, and are watertight.
2. Each part fits within the 220 by 220 mm XY build envelope.
3. Each rail-engaging edge is 2.0 mm thick.
4. The assembled width and height match the enclosure's derived front opening.
5. The camera opening remains 36 by 22 mm and centered horizontally.
6. The split aligns with the shell boundary and retains a 0.30 mm process gap.
7. The rear lap is 8 mm high and does not extend into the side rail zones.
8. Ribs do not cross the camera or NMO432 exclusion areas.
9. Assembled and exploded renders remain nonblank and show coherent placement.

Physical acceptance requires printing the existing fit coupon before either
full panel. Print the lower part first, verify slot fit and lap orientation,
then print the upper part and test the camera opening with the real bezel and
camera framing. Any shrinkage correction must be recorded as a measured
printer/material adjustment rather than changing the approved nominal envelope
without explanation.

## Boundaries

- The panel material is printed polymer; no mirror or optical claim is made.
- The front exposes only the camera opening. NMO432 continues to use the hidden
  lower-edge acoustic path.
- The change adds no sensor, display, amplifier, light, buzzer, or button.
- Mechanical fit does not establish medical accuracy or turn StrokeGuard into
  a diagnostic device.
