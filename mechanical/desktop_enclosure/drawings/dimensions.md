# Desktop Enclosure Dimension and Fastener Schedule

All dimensions are millimeters. Values are nominal CAD dimensions unless the
row explicitly requires a physical measurement.

## Main Envelope

| Feature | Printable | Display |
| --- | ---: | ---: |
| Overall width | 214 | 220 |
| Overall body height | 300 | 300 |
| Overall body depth | 55 | 55 |
| Upper shell nominal height | 150 | 150 |
| Lower shell height including tongue | 158 | 158 |
| Base width | 214 | 220 |
| Base depth | 110 | 110 |
| Base height | 16 | 16 |
| Body rearward lean | 7 degrees | 7 degrees |

## Split Front Panel

| Feature | Nominal dimension |
| --- | ---: |
| Assembled visible panel | 208 x 294 mm |
| Upper printed part | 208 x 146.85 x 4 mm maximum envelope |
| Lower printed part including rear lap | 208 x 154.85 x 4 mm maximum envelope |
| Visible center process gap | 0.30 mm |
| Integrated lower rear lap | 8 mm |
| Visible skin | 2.0 mm |
| Rear ribs | 6 mm wide x 2 mm high |

Print `front_panel_upper.stl` and `front_panel_lower.stl` separately. In the
slicer, orient the smooth visible face on the build plate and the rear ribs
upward. Install the lower part first; the upper part covers its rear lap while
the nominal `0.30 mm` center gap remains visible. The camera opening is present
only in the upper part.

## Openings and Fits

| Feature | Dimension |
| --- | ---: |
| Camera opening | 36 x 22 mm |
| Nominal wall | 3.0 mm |
| M3 clearance hole | 3.4 mm |
| Moving fit clearance | 0.30 mm |
| Tongue clearance | 0.25 mm per side |
| Tongue overlap | 8 mm |
| Front-panel slot | measured panel thickness + 0.40 mm |
| Camera carriage X/Y adjustment | 10 mm |
| Rear cover thickness | 2.4 mm |

The split front panel is generated directly from the OpenSCAD source and does
not require a separately cut sheet. Its camera opening is centered horizontally
and centered approximately 276 mm above the body bottom in the current source.

## Fasteners

| Joint | Quantity | CAD interface | Length selection |
| --- | ---: | --- | --- |
| Upper to lower shell | 4 | M3 through, 3.4 mm clearance | Measure printed joint and nut/insert stack |
| Upper rear cover | 4 | M3 through, 3.4 mm clearance | Measure cover plus boss engagement |
| Lower rear cover | 4 | M3 through, 3.4 mm clearance | Measure cover plus boss engagement |
| Lean support to base | 2 | M3 through, 3.4 mm clearance | Measure base recess and support stack |
| Camera carriage | As fitted | M2/M3 slots | Match actual camera board and washers |
| Controller rails | As fitted | M2/M3 slots or cable ties | Match actual N16R8 board |

M3 fasteners are mechanical additions, not sensors. Use washers where printed
surfaces would otherwise be point-loaded. Heat-set inserts or captured nuts may
be selected after the fit coupon; their dimensions are not assumed by this CAD
revision.

## Adjustable Electronics Zones

| Part | Outer CAD size | Constraint |
| --- | --- | --- |
| Camera carriage | 72 x 48 x 3 mm | No fixed camera-board hole pattern |
| Camera bezel | 44 x 30 x 2.4 mm | Replaceable aperture adapter |
| Controller rail | 126 x 18 x 5 mm | Two rails, repeated slots |
| NMO432 holder | 38 x 28 x 14 mm | Tie slots and open acoustic channel |
| USB blank | 33.4 x 15.4 x 3.3 mm | 0.30 mm nominal moving clearance |

Board outlines, connector offsets, front-panel thickness, print shrinkage, and
screw lengths require physical measurement. They are deliberately not fixed in
the source.
