# StrokeGuard Five-Part Service Tray Design

## Goal

Replace the three unattached internal parts with one removable electronics
tray so the compact enclosure has a complete, reproducible assembly path.

## Production Parts

The printable delivery contains exactly five parts:

- `compact_shell.stl`;
- `front_panel.stl`;
- `electronics_tray.stl`;
- `rear_cover.stl`;
- `desktop_base.stl`.

`camera_clamp.stl`, `controller_rail.stl`, and `microphone_holder.stl` are
removed from the production export after the replacement tray passes geometry
tests. User-created slicer projects, including untracked 3MF files, are not
deleted by this change.

## Electronics Tray

The tray uses a `96 x 149 x 3 mm` vertical backplane. Its complete printable
envelope, including the integrated camera cage and microphone supports, must
not exceed `96 x 149 x 15 mm`. It prints flat with the backplane on the build
plate and all retaining features facing upward.

The tray provides three zones:

1. A top camera cage for the documented `27 x 42 x 19 mm` module. Side guides,
   a central lens opening, and cable-tie slots constrain the board without
   guessed mounting-hole coordinates. The cage projects toward the front panel
   when installed and permits final lens alignment with the `12 mm` aperture.
2. A central universal N16R8 zone with repeated horizontal and vertical
   cable-tie slots. No controller-board dimensions or hole coordinates are
   encoded.
3. A lower NMO432 zone with repeated tie slots and an open path toward the
   front panel's lower acoustic notch. No microphone-board hole spacing is
   assumed.

Raw audio and video remain local; the tray contains no cloud, profile, or
credential data.

## Tray Retention

The canonical shell receives four fused tray stop pads around the installed
tray plane. The tray is inserted through the rear opening until it contacts the
front stops. Four rear-cover pressure posts contact the tray after the cover is
installed, sandwiching it between the stops and cover without a separate tray
fastener.

The stop pads and posts must overlap their parent printed parts by at least
`1 mm`; no isolated or merely coplanar solids are allowed. The tray, shell, and
rear cover must each export as one connected watertight mesh.

## Fastening

The preliminary prototype uses M3 screws directly in printed pilot holes:

- rear-cover clearance holes remain `3.4 mm`;
- matching shell pilot holes are `2.6 mm` nominal;
- base clearance holes remain `3.4 mm`;
- matching reinforced lower-shell pilot bosses are `2.6 mm` nominal.

The `2.6 mm` pilot is a starting CAD value for prototype plastic fastening, not
a measured guarantee. Screw length and pilot behavior must be checked on the
actual print and material. Do not force a screw toward a PCB or cable path.
Repeated production servicing may replace the pilot scheme with measured
heat-set inserts in a later hardware revision.

## Assembly

1. Insert `front_panel.stl` from the rear with the smooth face outward and the
   `12 mm` camera aperture at the top.
2. Secure the camera module, N16R8, and NMO432 to `electronics_tray.stl` with
   cable ties. Route camera I2C and microphone I2S separately and add strain
   relief.
3. Insert the populated tray from the rear until it seats against all four shell
   stops. Confirm lens and microphone alignment before closing the case.
4. Attach `compact_shell.stl` to `desktop_base.stl` with two M3 screws from the
   underside into the reinforced shell pilots.
5. Route power and debug cables through the lower rear exit.
6. Install `rear_cover.stl` with four M3 screws. Its pressure posts retain the
   electronics tray against the shell stops.

## Validation

Automated tests must verify:

- the export list and STL directory contain exactly the five production parts;
- the old three internal-part entry modes and STL files are absent;
- shell stops, rear-cover posts, and lower pilot bosses are present in source;
- the tray envelope is at most `96 x 149 x 15 mm`;
- tray, shell, rear cover, base, and front panel are watertight single-component
  meshes;
- printable orientation places each part on Z zero;
- no production STL contains a downward unsupported area larger than the
  documented test tolerance;
- assembled and exploded renders show the tray installed and separated;
- current README and dimension documents provide the exact five-part hardware
  relationship and no longer instruct users to assemble the three old parts.

Final verification requires OpenSCAD export and render, the complete mechanical
pytest suite, all 384 host tests, and `git diff --check`.

## Safety Boundary

StrokeGuard remains a risk-reminder and care-seeking aid, not a diagnostic
device. The mechanical redesign does not add hardware, make clinical claims,
or enable complex cloud instruction execution.
