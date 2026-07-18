# Compact Desktop Enclosure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the large split StrokeGuard enclosure with a minimal `110 x 165 x 40 mm` mirror body, one-piece front panel, `12 mm` camera aperture, and only the mounts needed for the camera, N16R8, and NMO432.

**Architecture:** Keep OpenSCAD as the manufacturing authority, but replace the split-shell module graph with seven compact production modules. A strict pytest contract controls dimensions, part names, obsolete-file removal, mesh validity, documentation, and generated renders before each commit.

**Tech Stack:** OpenSCAD 2021.01, PowerShell 5.1, Python 3.14, pytest, trimesh, Pillow, Git.

## Global Constraints

- Mirror-body maximum: `110 x 165 x 40 mm`.
- Front panel: one printable part, approximately `104 x 159 x 2 mm`.
- Camera opening: centered circular `12 mm` diameter.
- Camera source envelope: `27 x 42 x 19 mm`; do not invent mounting-hole spacing.
- Desktop base slab: `110 x 65 x 12 mm`, with an angled body slot rather than a separate lean support.
- Production exports contain exactly seven printable STL files.
- No ST7789, MAX98357A, RGB LED, buzzer, button, or extra sensor provisions.
- Raw audio and video remain local; mechanical files contain no credentials.
- Do not claim unmeasured print time, fit, stability, shrinkage, or thermal performance.

---

### Task 1: Lock The Compact Production Contract

**Files:**
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`
- Modify: `mechanical/desktop_enclosure/scad/parameters.scad`
- Modify: `mechanical/desktop_enclosure/scad/strokeguard_enclosure.scad`
- Modify: `mechanical/desktop_enclosure/scripts/export_models.ps1`

**Interfaces:**
- Produces SCAD entry modes: `compact_shell`, `front_panel`, `rear_cover`, `desktop_base`, `camera_clamp`, `controller_rail`, and `microphone_holder`.
- Produces parameter symbols consumed by Task 2: `body_width`, `body_height`, `body_depth`, `camera_aperture_diameter`, `camera_board`, `base_width`, `base_depth`, and `base_height`.

- [ ] **Step 1: Replace old contract assertions with failing compact assertions**

Set the production list in `test_enclosure.py` to:

```python
PRINTABLE_PARTS = (
    "compact_shell",
    "front_panel",
    "rear_cover",
    "desktop_base",
    "camera_clamp",
    "controller_rail",
    "microphone_holder",
)

OBSOLETE_PARTS = {
    "upper_shell", "lower_shell", "upper_rear_cover", "lower_rear_cover",
    "base", "lean_support", "camera_carriage", "camera_bezel", "usb_blank",
    "fit_coupon", "front_panel_upper", "front_panel_lower",
}
```

Add assertions for these exact declarations:

```python
def test_compact_parameter_contract():
    parameters = scad_text("parameters.scad")
    for declaration in (
        "body_width = 110", "body_height = 165", "body_depth = 40",
        "camera_aperture_diameter = 12", "camera_board = [27, 42, 19]",
        "base_width = 110", "base_depth = 65", "base_height = 12",
    ):
        assert declaration in parameters


def test_only_compact_part_modes_are_exported():
    entry = scad_text("strokeguard_enclosure.scad")
    script = (ROOT / "scripts" / "export_models.ps1").read_text(encoding="utf-8")
    for name in PRINTABLE_PARTS:
        assert f'"{name}"' in entry
        assert f"'{name}'" in script
    for name in OBSOLETE_PARTS:
        assert f'"{name}"' not in entry
        assert f"'{name}'" not in script
```

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pytest `
  mechanical\desktop_enclosure\tests\test_enclosure.py::test_compact_parameter_contract `
  mechanical\desktop_enclosure\tests\test_enclosure.py::test_only_compact_part_modes_are_exported -v
```

Expected: failures showing the old large dimensions and old production names.

- [ ] **Step 3: Replace the parameter and entry contracts**

Use this compact parameter core in `parameters.scad`:

```openscad
$fn = 48;
body_width = 110;
body_height = 165;
body_depth = 40;
wall = 3;
corner_radius = 4;
front_panel_thickness = 2;
panel_clearance = 0.4;
moving_clearance = 0.3;
camera_aperture_diameter = 12;
camera_board = [27, 42, 19];
camera_clearance = 0.6;
m3_clearance = 3.4;
lean_angle = 7;
rear_cover_thickness = 2.4;
base_width = 110;
base_depth = 65;
base_height = 12;
epsilon = 0.2;
```

Change the SCAD entry dispatch and `$PrintableParts` to the seven names in
`PRINTABLE_PARTS`. Keep `assembled`, `exploded`, and `display_stl` as render and
display-only modes.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the command from Step 2. Expected: both tests pass.

- [ ] **Step 5: Commit the compact contract**

```powershell
git add mechanical/desktop_enclosure/tests/test_enclosure.py `
  mechanical/desktop_enclosure/scad/parameters.scad `
  mechanical/desktop_enclosure/scad/strokeguard_enclosure.scad `
  mechanical/desktop_enclosure/scripts/export_models.ps1
git commit -m "refactor(mechanical): define compact enclosure contract"
git push origin codex/preliminary-demo
```

---

### Task 2: Replace The Large Geometry With Compact Modules

**Files:**
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`
- Rewrite: `mechanical/desktop_enclosure/scad/parts.scad`

**Interfaces:**
- Consumes the parameters and part names from Task 1.
- Produces seven printable modules plus `assembled_view()`, `exploded_view()`, and `display_stl_model()`.

- [ ] **Step 1: Add failing source-geometry tests**

```python
def test_compact_modules_and_camera_contract():
    parts = scad_text("parts.scad")
    for module in (
        "module compact_shell(", "module front_panel(",
        "module rear_cover(", "module desktop_base(",
        "module camera_clamp(", "module controller_rail(",
        "module microphone_holder(",
    ):
        assert module in parts
    assert "camera_aperture_diameter" in parts
    assert "camera_board[0] + 2 * camera_clearance" in parts
    assert "camera_board_hole_spacing" not in parts


def test_large_geometry_modules_are_removed():
    parts = scad_text("parts.scad")
    for obsolete in (
        "upper_shell", "lower_shell", "joint_tongue", "lean_support",
        "front_panel_upper_printable", "front_panel_lower_printable",
        "camera_bezel", "usb_blank",
    ):
        assert f"module {obsolete}(" not in parts
```

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pytest `
  mechanical\desktop_enclosure\tests\test_enclosure.py::test_compact_modules_and_camera_contract `
  mechanical\desktop_enclosure\tests\test_enclosure.py::test_large_geometry_modules_are_removed -v
```

Expected: failures because only the large split geometry exists.

- [ ] **Step 3: Rewrite `parts.scad` around the compact module graph**

Implement these exact responsibilities:

```openscad
module compact_shell() {
    // Rounded outer body, hollow interior, open front/rear, front-panel rails,
    // four rear-cover bosses, and two underside M3 base fasteners.
}

module front_panel() {
    difference() {
        rounded_plate(body_width - 2 * wall, body_height - 2 * wall,
                      front_panel_thickness, 3);
        translate([0, body_height / 2 - 24, -epsilon])
            cylinder(h = front_panel_thickness + 2 * epsilon,
                     d = camera_aperture_diameter);
        translate([0, -body_height / 2 + 8, -epsilon])
            cube([8, 2, front_panel_thickness + 2 * epsilon], center = true);
    }
}

module camera_clamp() {
    clamp_inner = [
        camera_board[0] + 2 * camera_clearance,
        camera_board[1] + 2 * camera_clearance,
        camera_board[2]
    ];
    // Back plate, side guides, open lens area, and cable-tie slots only.
}

module desktop_base() {
    // 110 x 65 x 12 slab with a 7-degree body slot and two underside M3 holes.
}
```

The rear cover receives four M3 clearance holes, ventilation slots, and one
lower cable exit. The controller rail must fit inside the `104 mm` inner width
and use repeated slots/cable-tie openings. The microphone holder retains an open
acoustic path. `assembled_view()` and `exploded_view()` must place every
production part without adding decorative hardware.

- [ ] **Step 4: Verify OpenSCAD can compile every mode**

```powershell
powershell -ExecutionPolicy Bypass -File `
  mechanical\desktop_enclosure\scripts\export_models.ps1 -Export -Render
```

Expected: exit code 0 for seven printable parts, display STL, and two renders.

- [ ] **Step 5: Run the focused and full mechanical tests**

```powershell
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pytest `
  mechanical\desktop_enclosure\tests\test_enclosure.py -v
```

Expected: all compact-contract and geometry tests pass.

- [ ] **Step 6: Commit compact geometry**

```powershell
git add mechanical/desktop_enclosure/scad/parts.scad `
  mechanical/desktop_enclosure/tests/test_enclosure.py
git commit -m "feat(mechanical): model compact desktop enclosure"
git push origin codex/preliminary-demo
```

---

### Task 3: Replace Generated Assets And Reject Obsolete Outputs

**Files:**
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`
- Replace contents: `mechanical/desktop_enclosure/stl/printable/`
- Replace: `mechanical/desktop_enclosure/stl/display/strokeguard-display.stl`
- Replace: `mechanical/desktop_enclosure/renders/assembled.png`
- Replace: `mechanical/desktop_enclosure/renders/exploded.png`

**Interfaces:**
- Consumes the export modes from Tasks 1-2.
- Produces the exact production STL set used by Bambu Studio.

- [ ] **Step 1: Add failing output-set and envelope tests**

```python
def test_printable_directory_contains_only_compact_parts():
    actual = {path.stem for path in (ROOT / "stl" / "printable").glob("*.stl")}
    assert actual == set(PRINTABLE_PARTS)


def test_compact_mesh_envelopes():
    shell = load_mesh(ROOT / "stl" / "printable" / "compact_shell.stl")
    assert all(shell.extents <= np.array([110.01, 40.01, 165.01]))
    panel = load_mesh(ROOT / "stl" / "printable" / "front_panel.stl")
    assert sorted(panel.extents) == pytest.approx(sorted([104, 159, 2]), abs=1.0)
```

Import `pytest` in the test module for the approximate comparison.

- [ ] **Step 2: Run the tests and verify RED**

Expected: the output-set test lists old split-shell STL names.

- [ ] **Step 3: Remove only obsolete mechanical outputs and re-export**

Resolve and verify that the target is
`F:\iot_design\mechanical\desktop_enclosure\stl\printable`, then remove its
old STL files with native PowerShell `Remove-Item -LiteralPath`. Do not touch
`firmware_camera`, `host_pc`, `cloud`, or `TinkercadMPC`. Run the Task 2 export
command to regenerate the compact set.

- [ ] **Step 4: Run mesh tests and inspect both renders**

Run the complete mechanical suite, then inspect `assembled.png` and
`exploded.png`. Confirm the front aperture is circular, the rear cover is
serviceable, and no part overlaps incoherently.

- [ ] **Step 5: Commit generated assets**

```powershell
git add mechanical/desktop_enclosure/stl `
  mechanical/desktop_enclosure/renders `
  mechanical/desktop_enclosure/tests/test_enclosure.py
git commit -m "build(mechanical): export compact enclosure models"
git push origin codex/preliminary-demo
```

---

### Task 4: Replace Handoff Documentation And Finish Verification

**Files:**
- Modify: `README.md`
- Rewrite: `mechanical/desktop_enclosure/README.md`
- Rewrite: `mechanical/desktop_enclosure/drawings/dimensions.md`
- Modify: `docs/developer-handoff.md`
- Delete: `docs/superpowers/specs/2026-07-18-split-printed-front-panel-design.md`
- Delete: `docs/superpowers/specs/2026-07-18-desktop-enclosure-3d-design.md`
- Delete: `docs/superpowers/plans/2026-07-18-split-printed-front-panel.md`
- Delete: `docs/superpowers/plans/2026-07-18-desktop-enclosure-3d-modeling.md`
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`

**Interfaces:**
- Documents the seven STL files and Bambu Studio print workflow.
- Preserves medical and privacy boundaries for handoff.

- [ ] **Step 1: Add failing handoff assertions**

Require the combined README and dimensions text to contain:

```python
for phrase in (
    "110 x 165 x 40 mm", "12 mm", "27 x 42 x 19 mm",
    "compact_shell.stl", "front_panel.stl", "desktop_base.stl",
    "smooth visible face", "before installing electronics",
    "not a diagnostic device",
):
    assert phrase.lower() in combined_handoff.lower()
```

Also assert that `214 x 300`, `front_panel_upper.stl`, `rear lap`, and
`36 x 22 mm` do not appear in current mechanical handoff documents.

- [ ] **Step 2: Run the handoff test and verify RED**

Expected: failures report old dimensions and split-panel instructions.

- [ ] **Step 3: Rewrite current handoff documents and remove obsolete design files**

Document Bambu Studio at 100% scale, `0.20 mm` initial layer profile guidance,
three walls, `15-20%` infill, smooth front face on the build plate, and slicer
preview checks. State that these are starting settings, not measured guarantees.
List camera-first alignment, N16R8 antenna clearance, NMO432 acoustic-path
verification, strain relief, rear-cover installation, and base attachment.

- [ ] **Step 4: Remove generated cache directories within the approved scope**

Resolve each `.pytest-*` target under `F:\iot_design`, verify that it is a child
of the workspace, and remove it with PowerShell. Do not delete the untracked
`TinkercadMPC` source directory or firmware build directories in this task.

- [ ] **Step 5: Run final verification**

```powershell
powershell -ExecutionPolicy Bypass -File `
  mechanical\desktop_enclosure\scripts\export_models.ps1 -Export -Render
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pytest `
  mechanical\desktop_enclosure\tests\test_enclosure.py -q
host_pc\.venv\Scripts\python.exe -m pytest host_pc\tests -q `
  --basetemp=F:\iot_design\.pytest-native-root\compact-enclosure-final `
  -p no:cacheprovider
git diff --check
```

Expected: OpenSCAD exits 0, all mechanical tests pass, all 384 host tests pass,
and Git reports no whitespace errors.

- [ ] **Step 6: Commit and push final handoff**

```powershell
git add README.md docs/developer-handoff.md `
  mechanical/desktop_enclosure/README.md `
  mechanical/desktop_enclosure/drawings/dimensions.md `
  mechanical/desktop_enclosure/tests/test_enclosure.py `
  docs/superpowers/specs docs/superpowers/plans
git commit -m "docs(mechanical): hand off compact enclosure"
git push origin codex/preliminary-demo
```
