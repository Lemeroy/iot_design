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

## Camera And Service Parts

| Feature | Nominal size or constraint |
| --- | ---: |
| Camera aperture | 12 mm circular |
| Supplied camera module envelope | 27 x 42 x 19 mm |
| Camera clamp maximum envelope | 38.2 x 49.2 x 22 mm |
| Controller rail | 90 x 16 x 5 mm |
| NMO432 holder | 30 x 24 x 14 mm |
| Moving fit clearance | 0.30 mm |
| Front-panel nominal clearance | 0.40 mm |

The camera drawing marks `4 mm` holes but does not provide complete mounting
coordinates. `camera_clamp.stl` therefore uses adjustable side constraints and
cable-tie slots. N16R8 and NMO432 mounts also avoid guessed board-hole spacing.

## Fasteners

| Joint | Quantity | CAD interface | Length selection |
| --- | ---: | --- | --- |
| Rear cover to shell | 4 | M3 through, 3.4 mm clearance | Measure cover, boss, and insert or nut stack |
| Mirror body to base | 2 | M3 through, 3.4 mm clearance | Measure base and lower shell stack |
| Camera module | As fitted | Side guides and cable ties | Match the supplied 27 x 42 mm board |
| N16R8 controller | As fitted | Repeated slots or cable ties | Match the actual controller board |
| NMO432 microphone | As fitted | Open holder and tie slots | Match the actual microphone module |

M3 fasteners are mechanical additions, not sensors. Board connector offsets,
print shrinkage, screw lengths, material use, and stability require physical
measurement and are not fixed by this CAD revision.
