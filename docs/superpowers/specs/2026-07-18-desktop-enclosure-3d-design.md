# StrokeGuard Desktop Demonstrator Enclosure 3D Design

## 1. Goal and scope

Design a compact desktop enclosure for the StrokeGuard preliminary-round
demonstrator. The enclosure presents the device as a self-contained health
screening mirror while keeping the installed ESP32-S3 boards and NMO432
accessible for development.

The deliverable has two representations:

- a TinkerCAD assembly for online presentation, visual inspection, and an
  exploded view;
- a parameter-driven OpenSCAD model and separated STL files suitable for an
  initial FDM print and later mechanical transfer.

The enclosure contains only the hardware currently needed for the preliminary
demonstration: the N16R8 main controller, the camera coprocessor, and the
NMO432 microphone. ST7789, MAX98357A, RGB LED, buzzer, and buttons are outside
this enclosure revision.

## 2. Chosen direction

The selected form is the straight-edged "medical instrument" direction. It
prioritizes a stable base, restrained appearance, usable internal volume, and
low-risk FDM parts over decorative curves.

Three modeling approaches were considered:

1. TinkerCAD presentation plus OpenSCAD/STL manufacturing files.
2. TinkerCAD-only construction.
3. FreeCAD parametric construction plus TinkerCAD presentation.

Approach 1 is selected. The current TinkerCAD MCP supports useful online shape
and assembly operations but is not a dependable source of truth for all
boolean holes, fit clearances, and repeatable parameters. OpenSCAD is therefore
the manufacturing source of truth, while TinkerCAD remains the review and
presentation surface.

## 3. Envelope and appearance

The TinkerCAD display assembly uses a nominal envelope of 220 mm wide, 300 mm
high, and 55 mm deep. The printable assembly is 214 mm wide, 300 mm high, and
55 mm deep so that every body section has margin on a common 220 by 220 mm
build plate. Both variants use the same proportions and component layout.

The front is a removable flat panel retained from behind. Its material is not
fixed in this revision. The surrounding slot is parameterized from measured
panel thickness rather than assuming acrylic, glass, or printed sheet stock.

The only visible front opening is a centered 36 by 22 mm camera window. A small
replaceable bezel adapts that window to the final camera lens position without
requiring the full upper shell to be printed again. The front face has no
visible microphone perforation; the acoustic path enters through the lower
edge.

Outer corners use a restrained 3 mm radius. An optional narrow status accent
may be represented in the display model but does not require lighting or an
additional electronic component.

## 4. Printed parts and assembly

The body is divided horizontally into upper and lower shells, each no more
than approximately 150 mm high. Their joint uses an internal 8 mm locating
tongue with hidden rear fasteners. Four M3 screws secure the body joint without
exposing fasteners on the front face.

The initial part set is:

- upper shell;
- lower shell;
- upper rear service cover;
- lower rear service cover;
- base;
- 7-degree rear-lean support;
- adjustable camera carriage;
- replaceable camera bezel;
- two adjustable main-controller rails;
- NMO432 acoustic holder;
- left and right USB-window blanking plates.

The base is approximately 214 mm wide, 110 mm deep, and 16 mm high in the
printable variant. The assembled body leans rearward by approximately 7
degrees. The base and support are mechanically fastened so a damaged or revised
support can be replaced independently.

Rear covers are independently removable. Routine board adjustment, USB access,
and wiring inspection do not require separating the upper and lower shells.

## 5. Internal layout

The camera coprocessor occupies the upper compartment. Its carriage provides
approximately 10 mm of horizontal and vertical lens adjustment and adjustable
front-panel setback. This supports final alignment without relying on an
unverified development-board outline or mounting-hole pattern.

The N16R8 main controller occupies the lower compartment on two slotted rails.
The rails accept M2/M3 fasteners and cable ties. Board outlines and mounting
holes therefore remain adjustable until the installed boards are measured.

The NMO432 sits behind the lower front edge in a small retaining clip and
acoustic chamber. A hidden lower-edge opening provides an unobstructed sound
path. The chamber does not imply an acoustic calibration claim; microphone
response must be checked on the assembled device.

The N16R8 antenna region faces a non-metallic side wall. Fasteners, board
ground planes, and bundled wiring must be kept away from that region. Camera
I2C and microphone I2S harnesses use separate cable paths, retaining bridges,
and strain-relief points.

Both side walls include elongated USB service windows. Their blanking plates
can be omitted during development and installed for presentation. The slots
are deliberately adjustable because COM3 and COM4 connector locations have not
been treated as fixed mechanical references.

Lower rear louvers and a lower-edge inlet provide passive airflow. This design
does not add a fan.

## 6. Manufacturing parameters

The OpenSCAD source exposes at least these parameters:

- display or printable body width;
- overall height and depth;
- wall thickness;
- front-panel measured thickness;
- panel-slot clearance;
- shell-joint clearance;
- camera-window width and height;
- USB-window position and dimensions;
- camera-carriage adjustment range;
- body lean angle.

Initial FDM values are:

- 3.0 mm nominal enclosure wall;
- 0.30 mm moving-fit clearance;
- 0.25 mm clearance per side at the locating tongue;
- 3.4 mm M3 clearance holes;
- measured panel thickness plus 0.40 mm for the front-panel slot;
- 0.20 mm layer height, three perimeters, and approximately 20 percent infill.

These are first-print starting values, not measured guarantees. A fit coupon
containing the tongue joint, front-panel slot, M3 nut capture, and USB blanking
plate must be printed before the complete enclosure. Clearances are adjusted
from that coupon while preserving the nominal external envelope.

## 7. Model organization

The manufacturing model will live under `mechanical/desktop_enclosure/` with
this intended organization:

```text
mechanical/desktop_enclosure/
|-- README.md
|-- scad/
|   |-- strokeguard_enclosure.scad
|   |-- parameters.scad
|   `-- parts.scad
|-- stl/
|   |-- printable/
|   `-- display/
|-- drawings/
|   `-- dimensions.md
`-- renders/
```

The TinkerCAD design name will be `StrokeGuard Desktop Demonstrator`. The
online assembly shows both an assembled unit and a separated exploded layout.
The repository remains the authoritative handoff location for dimensions and
printable geometry.

## 8. Verification and acceptance

Before the model is declared printable:

1. Every exported STL must be a closed, manifold solid with consistent normals.
2. Every printable part must fit within a 220 by 220 mm XY build envelope.
3. Nominal enclosure walls must be at least 3.0 mm except for documented fit
   features.
4. The assembled model must pass interference checks for shell joints, rear
   covers, base, support, rails, camera carriage, bezel, and blanking plates.
5. M3 screws and nuts must remain reachable with the rear covers removed.
6. USB plugs must be insertable without removing either main shell.
7. The camera opening and bezel must not obstruct the verified camera field of
   view at the selected carriage position.
8. The NMO432 lower-edge acoustic path must remain open after final assembly.
9. A physical fit coupon must be accepted before full-shell printing.
10. The TinkerCAD assembly and OpenSCAD display assembly must have matching
    nominal envelopes and visible part layout.

The first assembled print also requires practical checks for desk stability,
USB cable strain, Wi-Fi connectivity, camera framing, microphone response, and
surface temperature. Those results are recorded as measured observations and
are not inferred from the CAD model.

## 9. Explicit limitations

- Development-board dimensions and connector offsets are intentionally not
  invented. Adjustable mounts remain part of this revision.
- Front-panel material and thickness remain user-selected inputs to the model.
- This enclosure design does not add sensors or change the product's medical
  boundary: StrokeGuard provides risk reminders and care-seeking prompts, not
  a diagnosis.
- Mechanical modeling does not establish clinical accuracy, microphone
  calibration, thermal certification, ingress protection, or production safety
  certification.
