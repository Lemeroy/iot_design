# StrokeGuard Split Printed Front Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add upper and lower printable front-panel STL files with a centered camera opening, hidden rear lap, and rear stiffening ribs that fit the existing desktop enclosure.

**Architecture:** Extend the existing OpenSCAD parameter and part modules so the front-panel dimensions remain derived from the enclosure. Export both parts through the existing PowerShell pipeline and validate them with the existing pytest/trimesh suite. Update the mechanical handoff without changing the TinkerCAD presentation authority or device electronics.

**Tech Stack:** OpenSCAD 2021.01, PowerShell 5.1, Python 3.14, pytest, trimesh, Pillow.

## Global Constraints

- Each panel part must fit a 220 by 220 mm XY build area.
- Assembled panel nominal envelope is derived as approximately 208 by 294 mm.
- Rail-engaging edge thickness is 2.0 mm.
- Visible split gap is 0.30 mm and aligns with the 150 mm shell boundary.
- Lower rear lap height is 8 mm and stops before both side rail zones.
- Upper camera opening remains centered and 36 by 22 mm.
- Rear ribs are approximately 6 mm wide and 2 mm high.
- Ribs must avoid camera, shell joint, side rail, NMO432 acoustic, USB, and wiring exclusion zones.
- No board outline, mounting-hole spacing, front-panel material claim, or medical-performance claim may be invented.
- Existing unrelated untracked caches, firmware build outputs, and `TinkercadMPC/` remain untouched.

---

### Task 1: Parameterized Split-Panel Geometry

**Files:**
- Modify: `mechanical/desktop_enclosure/scad/parameters.scad`
- Modify: `mechanical/desktop_enclosure/scad/parts.scad`
- Modify: `mechanical/desktop_enclosure/scad/strokeguard_enclosure.scad`
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`

**Interfaces:**
- Consumes: `body_width`, `body_height`, `split_height`, `wall`, `camera_window`, `panel_thickness`, and the existing assembled/exploded views.
- Produces: `front_panel_upper_printable()`, `front_panel_lower_printable()`, `front_panel_assembled()`, plus entry modes `front_panel_upper` and `front_panel_lower`.

- [ ] **Step 1: Write failing source-contract tests**

```python
def test_split_front_panel_contract():
    parameters = scad_text("parameters.scad")
    parts = scad_text("parts.scad")
    entry = scad_text("strokeguard_enclosure.scad")
    for declaration in (
        "front_panel_skin = 2",
        "front_panel_gap = 0.3",
        "front_panel_lap_height = 8",
        "front_panel_rib_width = 6",
        "front_panel_rib_height = 2",
    ):
        assert declaration in parameters
    for module in (
        "module front_panel_upper_printable(",
        "module front_panel_lower_printable(",
        "module front_panel_assembled(",
    ):
        assert module in parts
    assert '"front_panel_upper"' in entry
    assert '"front_panel_lower"' in entry
```

- [ ] **Step 2: Run RED**

```powershell
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pytest `
  mechanical\desktop_enclosure\tests\test_enclosure.py::test_split_front_panel_contract -v
```

Expected: FAIL because the approved panel parameters and modules are absent.

- [ ] **Step 3: Add derived panel parameters**

```scad
front_panel_skin = 2;
front_panel_gap = 0.3;
front_panel_lap_height = 8;
front_panel_rib_width = 6;
front_panel_rib_height = 2;
front_panel_width = body_width - 2 * wall;
front_panel_height = body_height - 2 * wall;
front_panel_half_height = (front_panel_height - front_panel_gap) / 2;
front_panel_rail_keepout = wall + panel_thickness + panel_clearance + 4;
```

- [ ] **Step 4: Implement printable upper and lower modules**

Build each part as a 2 mm skin plus rear ribs. The upper part subtracts the
existing `camera_window` at its existing global center. The lower part adds an
8 mm rear lap that is inset by `front_panel_rail_keepout` on both sides. Add
horizontal and vertical ribs only inside the approved exclusion regions; all
ribs must overlap the skin by at least 0.2 mm to remain manifold.

- [ ] **Step 5: Replace display-only front panel placement**

`front_panel_assembled()` places lower and upper parts at the body front with
the 0.30 mm split gap. `assembled_body()` calls this module instead of the old
one-piece `front_panel(body_height, camera=true)`. `exploded_view()` places both
parts separately with their rear faces visible.

- [ ] **Step 6: Add entry-point dispatch and verify GREEN**

```scad
else if (part == "front_panel_upper") front_panel_upper_printable();
else if (part == "front_panel_lower") front_panel_lower_printable();
```

Run the focused test and smoke-export both modes to `.tmp`. Expected: test PASS,
OpenSCAD exit 0, and both temporary STL files exceed 256 bytes.

- [ ] **Step 7: Commit and push geometry**

```powershell
git add mechanical/desktop_enclosure/scad mechanical/desktop_enclosure/tests/test_enclosure.py
git commit -m "feat(mechanical): model split printed front panel"
git push origin codex/preliminary-demo
```

---

### Task 2: Exported Panel STL and Visual Acceptance

**Files:**
- Modify: `mechanical/desktop_enclosure/scripts/export_models.ps1`
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`
- Create: `mechanical/desktop_enclosure/stl/printable/front_panel_upper.stl`
- Create: `mechanical/desktop_enclosure/stl/printable/front_panel_lower.stl`
- Modify: `mechanical/desktop_enclosure/renders/assembled.png`
- Modify: `mechanical/desktop_enclosure/renders/exploded.png`

**Interfaces:**
- Consumes: the two Task 1 part modes.
- Produces: committed watertight STL files and updated assembly renders.

- [ ] **Step 1: Extend failing mesh acceptance**

Add `front_panel_upper` and `front_panel_lower` to `PRINTABLE_PARTS`, then add:

```python
def test_split_panels_match_enclosure_and_camera_contract():
    upper = load_mesh(ROOT / "stl" / "printable" / "front_panel_upper.stl")
    lower = load_mesh(ROOT / "stl" / "printable" / "front_panel_lower.stl")
    assert upper.is_watertight and lower.is_watertight
    assert upper.extents[0] <= 208.01
    assert lower.extents[0] <= 208.01
    assert upper.extents[1] <= 220.01
    assert lower.extents[1] <= 220.01
```

- [ ] **Step 2: Run RED**

Expected: FAIL because committed panel STL files do not exist.

- [ ] **Step 3: Add both modes to deterministic export**

Append exact names `front_panel_upper` and `front_panel_lower` to
`$PrintableParts`. Keep cleanup bounded to those known output filenames.

- [ ] **Step 4: Export and run full mechanical tests**

```powershell
powershell -ExecutionPolicy Bypass -File `
  mechanical\desktop_enclosure\scripts\export_models.ps1 -Export -Render
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pytest `
  mechanical\desktop_enclosure\tests\test_enclosure.py -v
```

Expected: all tests PASS; all 14 printable STL files are watertight and
build-plate bounded; assembled and exploded PNGs remain nonblank.

- [ ] **Step 5: Inspect both renders**

Verify that the assembled front faces are coplanar, the split aligns with the
shell boundary, the camera opening remains visible, and the exploded view shows
upper/lower orientation and rear ribs without incoherent overlap.

- [ ] **Step 6: Commit and push generated artifacts**

```powershell
git add mechanical/desktop_enclosure/scripts/export_models.ps1 `
  mechanical/desktop_enclosure/tests/test_enclosure.py `
  mechanical/desktop_enclosure/stl mechanical/desktop_enclosure/renders
git commit -m "build(mechanical): export split front panel models"
git push origin codex/preliminary-demo
```

---

### Task 3: Print Handoff and Final Verification

**Files:**
- Modify: `mechanical/desktop_enclosure/README.md`
- Modify: `mechanical/desktop_enclosure/drawings/dimensions.md`
- Modify: `README.md`
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`

**Interfaces:**
- Consumes: verified split-panel STL and renders.
- Produces: print order, orientation, assembly, and fit acceptance instructions.

- [ ] **Step 1: Write failing handoff assertions**

```python
def test_front_panel_handoff_is_documented():
    readme = (ROOT / "README.md").read_text("utf-8")
    dimensions = (ROOT / "drawings" / "dimensions.md").read_text("utf-8")
    for phrase in ("front_panel_upper.stl", "front_panel_lower.stl", "rear lap", "0.30 mm"):
        assert phrase.lower() in readme.lower()
    assert "208 x 294 mm" in dimensions
    assert "36 x 22 mm" in dimensions
```

- [ ] **Step 2: Run RED**

Expected: FAIL because the handoff still describes an externally cut front
panel.

- [ ] **Step 3: Update print and assembly guidance**

Document lower-first fit testing, largest-flat-face print orientation, rear-rib
orientation, 0.30 mm process gap, lower rear lap, camera-opening check, and the
requirement to verify both pieces in the shell before installing electronics.
Remove instructions that say the front panel must be cut separately.

- [ ] **Step 4: Run final verification**

```powershell
powershell -ExecutionPolicy Bypass -File `
  mechanical\desktop_enclosure\scripts\export_models.ps1 -Export -Render
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pytest `
  mechanical\desktop_enclosure\tests\test_enclosure.py -q
host_pc\.venv\Scripts\python.exe -m pytest host_pc\tests -q `
  --basetemp=F:\iot_design\.pytest-native-root\front-panel-final `
  -p no:cacheprovider
git diff --check
```

Expected: mechanical tests and all 384 host tests PASS, exports are fresh, and
there are no whitespace errors.

- [ ] **Step 5: Commit and push handoff**

```powershell
git add README.md mechanical/desktop_enclosure/README.md `
  mechanical/desktop_enclosure/drawings/dimensions.md `
  mechanical/desktop_enclosure/tests/test_enclosure.py
git commit -m "docs(mechanical): document split front panel printing"
git push origin codex/preliminary-demo
```
