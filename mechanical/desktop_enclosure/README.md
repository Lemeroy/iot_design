# StrokeGuard Compact Desktop Enclosure

This package is the manufacturing handoff for the compact StrokeGuard
preliminary-demonstration enclosure. OpenSCAD is the source of truth for fit
and dimensions. The mirror body is limited to `110 x 165 x 40 mm`.

StrokeGuard is a risk-reminder and care-seeking aid, not a diagnostic device.
The enclosure does not establish clinical accuracy, microphone calibration,
thermal certification, ingress protection, or production safety certification.

## Production Files

The `stl/printable/` directory contains exactly these parts:

- `compact_shell.stl`;
- `front_panel.stl`;
- `rear_cover.stl`;
- `desktop_base.stl`;
- `camera_clamp.stl`;
- `controller_rail.stl`;
- `microphone_holder.stl`.

The one-piece front panel has a centered `12 mm` circular camera aperture. The
camera clamp is based on the supplied `27 x 42 x 19 mm` module envelope. It uses
side constraints and cable-tie slots because the supplied drawing does not give
complete mounting-hole spacing.

Additional delivery files:

- parameters: `scad/parameters.scad`;
- geometry modules: `scad/parts.scad`;
- command-line entry: `scad/strokeguard_enclosure.scad`;
- display STL: `stl/display/strokeguard-display.stl`;
- assembly and exploded renders: `renders/`;
- dimension schedule: `drawings/dimensions.md`.

This revision provides only the N16R8 controller rail, camera clamp, NMO432
holder, rear service cover, and desktop base. It does not add ST7789,
MAX98357A, RGB LED, buzzer, buttons, or another sensor.

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
installed on the printer. Import the seven production STL files at `100%`
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
- `compact_shell.stl`: one broad side wall on the build plate;
- `rear_cover.stl`: largest flat face on the build plate;
- `desktop_base.stl`: bottom face on the build plate;
- `camera_clamp.stl`: back plate on the build plate, guides upward;
- controller rail and microphone holder: largest flat face on the build plate.

Inspect the complete slicer preview for closed holes, unsupported rails, thin
walls, and the `12 mm` camera aperture before printing.

## Assembly Order

1. Before installing electronics, test-fit the shell, front panel, rear cover,
   and base. Do not force tight rails or fasteners.
2. Deburr the camera aperture, lower acoustic notch, cable exit, and M3 holes.
3. Seat the `27 x 42 x 19 mm` camera module in `camera_clamp.stl`, secure it
   through the cable-tie slots, and align the lens through the `12 mm` aperture.
4. Install the N16R8 on `controller_rail.stl`. Keep its antenna area clear of
   fasteners and bundled wiring.
5. Align NMO432 with the hidden lower acoustic path and verify that the live S
   value responds after the front panel is installed.
6. Route camera I2C and microphone I2S separately, add strain relief, and pass
   power and debug wiring through the lower rear cable exit.
7. Install the rear cover with four M3 fasteners and attach the body to the base
   through the two underside M3 positions.

Select screw lengths only after measuring the printed stack, washers, and any
inserts or nuts. Do not force an overlong screw into a PCB or wire path.

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
