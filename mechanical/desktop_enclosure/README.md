# StrokeGuard Desktop Enclosure

This package contains the desktop preliminary-demonstration enclosure for
StrokeGuard. OpenSCAD is the manufacturing source of truth. TinkerCAD is a
presentation copy and is not authoritative for fit or print dimensions.

StrokeGuard is a risk-reminder and care-seeking aid, not a diagnostic device.
The enclosure does not establish clinical accuracy, microphone calibration,
thermal certification, ingress protection, or production safety certification.

## Deliverables

- Printable assembly envelope: `214 x 300 x 55 mm`.
- TinkerCAD/display envelope: `220 x 300 x 55 mm`.
- Parameter source: `scad/parameters.scad`.
- Part modules: `scad/parts.scad`.
- Command-line entry point: `scad/strokeguard_enclosure.scad`.
- Printable STL files: `stl/printable/`.
- Watertight display STL: `stl/display/strokeguard-display.stl`.
- Assembly and exploded renders: `renders/`.
- TinkerCAD identity: `tinkercad-design.json`.
- Dimension and fastener schedule: `drawings/dimensions.md`.

The TinkerCAD presentation is available at:

https://www.tinkercad.com/things/kai4l0KkMBD/edit

## Included Hardware Provisions

This revision provides adjustable mounting for:

- ESP32-S3-WROOM-1 N16R8 main controller;
- camera coprocessor and centered camera opening;
- NMO432 microphone with a hidden lower-edge acoustic path.

It does not add ST7789, MAX98357A, RGB LED, buzzer, buttons, or another sensor.
Board outlines, mounting-hole spacing, and USB offsets remain adjustable rather
than being inferred from unmeasured development boards.

## Tool Setup

Install OpenSCAD on Windows:

```powershell
winget install --id OpenSCAD.OpenSCAD --exact `
  --accept-package-agreements --accept-source-agreements
```

Create the isolated mechanical environment:

```powershell
cd F:\iot_design
python -m venv mechanical\desktop_enclosure\.venv
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pip install `
  -r mechanical\desktop_enclosure\requirements-dev.txt
```

The export script discovers OpenSCAD from `OPENSCAD_EXE`, PATH, or the standard
`C:\Program Files\OpenSCAD` installation. It does not use or modify the PC
application environment.

## Change Parameters

Edit `scad/parameters.scad` for approved envelope and fit values. Pass measured
front-panel thickness without editing source:

```powershell
& 'C:\Program Files\OpenSCAD\openscad.com' `
  -D 'part=\"fit_coupon\"' `
  -D 'variant=\"printable\"' `
  -D 'panel_thickness=2.0' `
  -o fit_coupon.stl `
  mechanical\desktop_enclosure\scad\strokeguard_enclosure.scad
```

Do not encode guessed board dimensions into the model. Use the camera carriage,
controller rails, M2/M3 slots, and cable-tie slots until actual boards have been
measured.

## Export and Test

Regenerate all committed STL and PNG outputs:

```powershell
powershell -ExecutionPolicy Bypass -File `
  mechanical\desktop_enclosure\scripts\export_models.ps1 -Export -Render
```

Run geometry and handoff tests:

```powershell
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pytest `
  mechanical\desktop_enclosure\tests\test_enclosure.py -v
```

The tests load every STL through trimesh, require watertight meshes, enforce the
`220 x 220 mm` printable XY limit, validate nonblank renders, and reject
credentials in the TinkerCAD manifest.

## Print Order

1. Print `fit_coupon.stl` first.
2. Test the locating tongue, panel slot, M3 clearance hole, and panel material.
3. Adjust only the documented clearance parameters if the coupon does not fit.
4. Print camera bezel, USB blank, controller rail, and microphone holder.
5. Print rear covers, base, lean support, and the upper/lower shells.

Initial FDM settings are `0.20 mm` layer height, three perimeters, and about
`20%` infill. They are first-print settings, not measured guarantees. Use the
printer and filament profile recommended by the material supplier.

Suggested orientation:

- upper and lower shells: rear face on the build plate, front opening upward;
- rear covers, camera carriage, bezel, rail, USB blank, and fit coupon: largest
  flat face on the build plate;
- base and microphone holder: bottom face on the build plate;
- lean support: broad side face on the build plate.

Inspect slicer previews for unsupported bridges and screw-hole closure before
printing full shells.

## Assembly Order

1. Deburr the camera window, side USB windows, acoustic path, and M3 holes.
2. Install the camera on the adjustable carriage and align it through the
   replaceable bezel.
3. Install the N16R8 on the two slotted controller rails. Keep its antenna area
   clear of fasteners and bundled wiring.
4. Attach NMO432 to the adjustable holder with its acoustic port aligned to the
   lower-edge channel. Verify microphone response after enclosure assembly.
5. Route camera I2C and microphone I2S harnesses separately and add strain
   relief before closing the case.
6. Join upper and lower shells with four M3 fasteners through the rear-accessible
   joint bosses.
7. Seat the lean support in the base recess and secure it with two M3 fasteners.
8. Insert the measured front panel and verify the `36 x 22 mm` camera opening is
   unobstructed.
9. Install each rear cover with four M3 fasteners.
10. Fit or remove the USB blanking plates according to demonstration needs.

Select screw length after printing the fit coupon and measuring the actual boss,
washer, insert, and nut stack. Do not force an overlong screw into a PCB or wire
path.

## Physical Acceptance

The repository tests validate digital geometry only. Before presentation:

- confirm the base remains stable with both USB cables connected;
- confirm shell joints and rear covers seat without stress cracking;
- confirm USB plugs can be inserted without removing a main shell;
- verify camera framing at the intended screening distance;
- speak near NMO432 and verify the live S signal changes;
- verify Wi-Fi connectivity with the final panel and wiring installed;
- record enclosure surface temperature as a measured observation.

Raw audio and video remain local to the device. Mechanical files and TinkerCAD
contain no user profile, sensor capture, cloud credential, or device secret.
