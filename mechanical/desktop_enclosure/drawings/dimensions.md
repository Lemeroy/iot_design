# Compact Desktop Enclosure Dimension Schedule

All dimensions are millimeters and nominal CAD values unless explicitly marked
as requiring a physical measurement.

## Main Envelope

| Feature | Nominal size |
| --- | ---: |
| Mirror body maximum | 110 x 165 x 40 mm |
| One-piece front panel | 104 x 159 x 2 mm |
| Rear cover | 102 x 157 x 2.4 mm |
| Desktop base slab | 110 x 65 x 12 mm |
| Rearward lean | 7 degrees |
| Nominal wall | 3.0 mm |

The base is outside the mirror-body envelope. The final assembled footprint
depends on the body angle and must be checked in the slicer and on the real
print.

## Camera And Electronics Tray

| Feature | Nominal size or constraint |
| --- | ---: |
| Camera aperture | 12 mm circular |
| Supplied camera module envelope | 27 x 42 x 19 mm |
| Tray backplane | 96 x 149 x 3 mm |
| Tray total maximum envelope | 96 x 149 x 15 mm |
| Moving fit clearance | 0.30 mm |
| Front-panel nominal clearance | 0.40 mm |

The camera drawing marks `4 mm` holes but does not provide complete mounting
coordinates. `electronics_tray.stl` therefore combines adjustable camera side
guides with cable-tie slots. N16R8 and NMO432 slots also avoid guessed board-hole
spacing. Shell stop pads set the tray's forward position; rear-cover pressure
posts retain it after the cover is installed.

## Fasteners

| Joint | Quantity | CAD interface | Length selection |
| --- | ---: | --- | --- |
| Rear cover to shell | 4 | 3.4 mm cover clearance into 2.6 mm printed pilot | Select after measuring the physical print |
| Mirror body to base | 2 | 3.4 mm base clearance into 2.6 mm reinforced pilot | Select after measuring the physical print |
| Camera module | As fitted | Tray side guides and cable ties | Match the supplied 27 x 42 mm board |
| N16R8 controller | As fitted | Repeated tray slots and cable ties | Match the actual controller board |
| NMO432 microphone | As fitted | Tray slots and cable ties | Match the actual microphone module |

M3 fasteners are mechanical additions, not sensors. The `2.6 mm` pilot is a CAD
starting point for thread-forming into printed plastic, not a guaranteed fit.
Board connector offsets, pilot/screw fit, print shrinkage, screw lengths,
material use, and stability require a physical print and measurement.
