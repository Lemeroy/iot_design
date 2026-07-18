# StrokeGuard Compact Desktop Enclosure Design

## Goal

Replace the oversized `214 x 300 x 55 mm` preliminary enclosure with a compact
desktop enclosure whose mirror body is no larger than `110 x 165 x 40 mm`.
The compact enclosure houses the ESP32-S3 N16R8 controller, the camera module,
and the NMO432 microphone without adding display, amplifier, LED, buzzer,
button, or other sensor provisions.

## Mechanical Authority

OpenSCAD remains the manufacturing source of truth. Generated STL and PNG
files are committed delivery artifacts. TinkerCAD is not authoritative for fit
or print dimensions. Dimensions not present in an approved drawing remain
adjustable and must not be inferred from photographs.

## Approved Envelope

| Feature | Approved nominal size |
| --- | ---: |
| Mirror body | `110 x 165 x 40 mm` maximum |
| Front panel | approximately `104 x 159 x 2 mm` |
| Camera aperture | centered circular `12 mm` diameter |
| Desktop base | `110 x 65 x 12 mm` |

The base is outside the mirror-body envelope. The assembled footprint may be
deeper than `40 mm` because the mirror leans rearward over the base. OpenSCAD
must calculate the final assembled footprint and the dimension schedule must
report it without claiming measured print performance.

## Camera Source Dimensions

The supplied module drawing defines the camera module as `27 x 42 x 19 mm` and
shows `4 mm` mounting holes. It does not provide a complete, unambiguous hole
spacing schedule. The compact camera clamp therefore uses side constraints and
cable-tie slots for a `27 x 42 mm` board and provides at least `19 mm` depth.
It must not encode guessed mounting-hole coordinates.

Only the lens is visible through the front panel. The previous `36 x 22 mm`
rectangular opening is replaced by a centered `12 mm` diameter circular
aperture. The camera board, connectors, and harness remain behind the panel.

## Printed Parts

The production export contains only these compact enclosure parts:

- `compact_shell.stl`: side, top, and bottom structure with open front and rear;
- `front_panel.stl`: one-piece front skin with the camera aperture and hidden
  lower microphone acoustic path;
- `rear_cover.stl`: removable service cover with a lower cable exit;
- `desktop_base.stl`: stable desktop foot and body locating interface;
- `camera_clamp.stl`: adjustable clamp for the documented camera envelope;
- `controller_rail.stl`: adjustable N16R8 support without guessed hole spacing;
- `microphone_holder.stl`: adjustable NMO432 support aligned to the hidden
  acoustic path.

The front panel is no longer split. Electronics are installed and serviced
from the rear. The rear cover remains removable after the body is seated in the
base.

## Removed Production Artifacts

The compact export replaces and removes these obsolete printable artifacts:

- `upper_shell.stl` and `lower_shell.stl`;
- `upper_rear_cover.stl` and `lower_rear_cover.stl`;
- `front_panel_upper.stl` and `front_panel_lower.stl`;
- the lower rear lap and center process-gap geometry;
- `camera_bezel.stl`;
- `usb_blank.stl`;
- `lean_support.stl`;
- the old `base.stl`, camera carriage, and fit coupon tied to the large model;
- old large-envelope display STL and renders, which are regenerated under the
  compact design.

Obsolete split-panel and large-enclosure handoff documents are removed after
their replacement documentation is committed. Their history remains available
in Git. Unrelated source directories are not deleted. Generated pytest caches
and mechanical temporary exports may be removed without staging them.

## Assembly

1. Print and test-fit the compact shell, front panel, rear cover, and base before
   installing electronics.
2. Seat the camera module in the adjustable clamp and align its lens with the
   `12 mm` aperture.
3. Mount the N16R8 on the adjustable controller rail while keeping its antenna
   area clear of fasteners and bundled wiring.
4. Mount NMO432 behind the hidden acoustic path and verify live microphone
   response after closing the enclosure.
5. Route camera I2C and microphone I2S separately, add strain relief, and route
   power and debug wiring through the rear lower cable exit.
6. Install the removable rear cover and seat the body in the desktop base.

## Validation

Automated mechanical tests must verify:

- the mirror body does not exceed `110 x 165 x 40 mm`;
- the camera aperture contract is circular and `12 mm` in diameter;
- the camera clamp accepts the documented `27 x 42 x 19 mm` envelope without
  relying on mounting-hole coordinates;
- every exported STL is watertight and fits a `220 x 220 mm` build plate;
- the export directory contains the compact production part list and no
  obsolete large-enclosure STL names;
- assembled and exploded renders are nonblank;
- documentation lists the exact print and assembly sequence.

Final verification consists of the complete mechanical pytest suite, the
existing 384 host tests, OpenSCAD export and render, and `git diff --check`.
Physical fit, print time, material use, dimensional shrinkage, thermal behavior,
and stability remain pending real prints and must not be presented as measured
results.

## Safety And Privacy Boundary

The enclosure does not change the product boundary: StrokeGuard is a health
risk reminder and care-seeking aid, not a diagnostic device. Raw audio and
video remain local and are not uploaded. The mechanical design adds no complex
cloud instruction execution or new sensing hardware.
