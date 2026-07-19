# StrokeGuard Compact Desktop Enclosure

This package is the manufacturing handoff for the compact StrokeGuard
preliminary-demonstration enclosure. OpenSCAD is the source of truth for fit
and dimensions. The mirror body is limited to `110 x 165 x 40 mm`.

StrokeGuard is a risk-reminder and care-seeking aid, not a diagnostic device.
The enclosure does not establish clinical accuracy, microphone calibration,
thermal certification, ingress protection, or production safety certification.

## Production Files

The `stl/printable/` directory contains exactly five production parts:

- `compact_shell.stl`;
- `front_panel.stl`;
- `electronics_tray.stl`;
- `rear_cover.stl`;
- `desktop_base.stl`.

The one-piece front panel has a centered `12 mm` circular camera aperture. The
removable electronics tray provides a camera cage sized from the supplied
`27 x 42 x 19 mm` module envelope, repeated N16R8 slots, NMO432 slots, and cable
routing. All three modules use cable ties because the supplied drawings do not
give complete mounting-hole coordinates.

The first-print correction uses a `30 mm camera-guide opening`, moves the tray
`2 mm rearward`, and leaves a nominal `0.5 mm assembly gap` between the tray and
rear-cover posts. These are prototype clearances derived from physical fit
feedback, not production tolerances.

Additional delivery files:

- parameters: `scad/parameters.scad`;
- geometry modules: `scad/parts.scad`;
- command-line entry: `scad/strokeguard_enclosure.scad`;
- display STL: `stl/display/strokeguard-display.stl`;
- assembly and exploded renders: `renders/`;
- dimension schedule: `drawings/dimensions.md`.

This revision provides only the integrated electronics tray, rear service
cover, and desktop base needed by the N16R8, camera module, and NMO432. It does
not add ST7789, MAX98357A, RGB LED, buzzer, buttons, or another sensor.

## Tool Setup

Install OpenSCAD on Windows:

```powershell
winget install --id OpenSCAD.OpenSCAD --exact `
  --accept-package-agreements --accept-source-agreements
```

Create the isolated mechanical test environment:

```powershell
cd F:\iot_design
python -m venv mechanical\desktop_enclosure\.venv
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pip install `
  -r mechanical\desktop_enclosure\requirements-dev.txt
```

Regenerate all committed STL and PNG outputs:

```powershell
powershell -ExecutionPolicy Bypass -File `
  mechanical\desktop_enclosure\scripts\export_models.ps1 -Export -Render
```

Run the geometry and handoff tests:

```powershell
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pytest `
  mechanical\desktop_enclosure\tests\test_enclosure.py -v
```

## Bambu Studio

Select the built-in Bambu Lab H2S printer profile and the nozzle actually
installed on the printer. Import the five production STL files at `100%`
scale. For a first PLA print with a `0.4 mm` nozzle, use these starting values:

- `0.20 mm` standard layer profile;
- three walls;
- `15-20%` infill;
- support disabled initially, then enabled only where the slicer preview shows
  unsupported geometry.

These are starting settings, not measured guarantees. Use the filament and
build-plate profiles recommended by their manufacturers.

Suggested orientation:

- `front_panel.stl`: smooth visible face on the build plate;
- `compact_shell.stl`: already exported with one broad side wall on the build
  plate; keep the default imported orientation;
- `rear_cover.stl`: largest flat face on the build plate;
- `desktop_base.stl`: bottom face on the build plate;
- `electronics_tray.stl`: broad backplane on the build plate, guides upward.

Inspect the complete slicer preview for closed holes, unsupported rails, thin
walls, and the `12 mm` camera aperture before printing.

## Assembly Order

1. Before installing electronics, test-fit all five printed parts. Slide the
   empty tray in from the rear and confirm that it reaches the shell stop pads
   without binding. Do not force tight rails or fasteners.
2. Deburr the camera aperture, lower acoustic notch, cable exit, and M3 holes.
3. Populate the electronics tray first. Secure the `27 x 42 x 19 mm` camera
   module in the upper cage with cable ties, then align the N16R8 and NMO432 on
   their adjustable slots. Keep the N16R8 antenna area clear of fasteners and
   bundled wiring.
4. Route camera I2C and microphone I2S separately on the tray, add strain
   relief, and leave enough cable for the lower rear exit.
5. Insert the populated tray from the rear until it rests against the shell
   stop pads. Confirm the camera lens is centered in the `12 mm` aperture and
   NMO432 faces the hidden lower acoustic path.
6. Fit the rear cover. Its rear-cover pressure posts retain the tray against the
   shell stops; they are not screw bosses and must not crush a PCB or cable.
7. Install four M3 screws through the rear cover's `3.4 mm` clearance holes into
   the shell's `2.6 mm` printed pilot holes. Attach the body to the base with two
   M3 screws through its `3.4 mm` clearance holes into the reinforced `2.6 mm`
   shell pilots.

When replacing the earlier tight-fitting revision, reprint the shell,
electronics tray, and rear cover. The shell contains the shifted tray stops,
the tray contains the wider camera guides, and the rear cover contains the
shortened posts. The front panel and desktop base do not need reprinting for
this correction unless their physical parts are damaged or out of tolerance.

Select screw lengths only after measuring the printed stack, washers, and any
inserts or nuts. Pilot-hole and screw fit is pending a physical print; drill or
ream cautiously if material shrinkage makes a pilot too tight. Do not force an
overlong screw into a PCB or wire path.

## Physical Acceptance

Repository tests validate digital geometry only. Before presentation:

- verify front-panel and rear-cover fit on the real print;
- verify the camera module clears the rear cover and frames the intended user;
- verify NMO432 response with the enclosure closed;
- verify the base remains stable with final power and debug cables attached;
- verify Wi-Fi operation with the final enclosure and wiring;
- record print time, material use, shrinkage, and surface temperature only as
  measured observations.

Raw audio and video remain local. Mechanical files contain no user profile,
sensor capture, cloud credential, or device secret.
