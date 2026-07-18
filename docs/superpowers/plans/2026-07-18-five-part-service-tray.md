# Five-Part Service Tray Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace three unattached internal mounts with one printable electronics tray and complete every shell, rear-cover, and base fastening interface.

**Architecture:** Keep the existing compact body envelope and split the printable delivery into exactly five connected parts. The electronics tray carries all boards, seats against fused shell stops, and is retained by rear-cover pressure posts; printed M3 pilot bosses provide prototype screw retention.

**Tech Stack:** OpenSCAD 2021.01, PowerShell 5.1, Python 3.14, pytest, trimesh, Pillow, Git.

## Global Constraints

- Keep the mirror body at `110 x 165 x 40 mm` and camera aperture at `12 mm`.
- Camera source envelope is `27 x 42 x 19 mm`; do not encode unknown hole spacing.
- Electronics tray backplane is `96 x 149 x 3 mm`; complete tray is at most `96 x 149 x 15 mm`.
- Production export contains exactly five STL files.
- Rear cover and base use `3.4 mm` clearance holes against `2.6 mm` printed pilot holes.
- Every production STL must be one connected watertight mesh and use a tested print orientation.
- Do not delete untracked user 3MF projects, `TinkercadMPC`, firmware builds, or `sdkconfig`.
- Physical screw fit, print time, and material performance remain pending real prints.

---

### Task 1: Lock The Five-Part Contract

**Files:**
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`
- Modify: `mechanical/desktop_enclosure/scad/parameters.scad`
- Modify: `mechanical/desktop_enclosure/scad/strokeguard_enclosure.scad`
- Modify: `mechanical/desktop_enclosure/scripts/export_models.ps1`

**Interfaces:**
- Produces printable modes `compact_shell`, `front_panel`, `electronics_tray`, `rear_cover`, and `desktop_base`.
- Produces `tray_width`, `tray_height`, `tray_thickness`, `tray_feature_height`, and `m3_pilot_diameter` for Task 2.

- [ ] **Step 1: Write failing production-list and parameter tests**

```python
PRINTABLE_PARTS = (
    "compact_shell", "front_panel", "electronics_tray",
    "rear_cover", "desktop_base",
)

def test_five_part_parameter_contract():
    parameters = scad_text("parameters.scad")
    for declaration in (
        "tray_width = 96", "tray_height = 149", "tray_thickness = 3",
        "tray_feature_height = 12", "m3_pilot_diameter = 2.6",
    ):
        assert declaration in parameters
```

Extend obsolete names with `camera_clamp`, `controller_rail`, and
`microphone_holder`, then assert they are absent from the SCAD entry and export
script.

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pytest `
  mechanical\desktop_enclosure\tests\test_enclosure.py::test_five_part_parameter_contract `
  mechanical\desktop_enclosure\tests\test_enclosure.py::test_only_compact_part_modes_are_exported -v
```

Expected: failures list the missing tray mode and old three modes.

- [ ] **Step 3: Implement the five-part parameter and dispatch contract**

Add:

```openscad
tray_width = 96;
tray_height = 149;
tray_thickness = 3;
tray_feature_height = 12;
m3_pilot_diameter = 2.6;
tray_installed_y = 0;
tray_stop_overlap = 1;
```

Replace the three old production modes with `electronics_tray` in the entry and
PowerShell export array.

- [ ] **Step 4: Verify GREEN and commit**

Run the focused command, then:

```powershell
git add mechanical/desktop_enclosure/tests/test_enclosure.py `
  mechanical/desktop_enclosure/scad/parameters.scad `
  mechanical/desktop_enclosure/scad/strokeguard_enclosure.scad `
  mechanical/desktop_enclosure/scripts/export_models.ps1
git commit -m "refactor(mechanical): define five-part enclosure contract"
git push origin codex/preliminary-demo
```

---

### Task 2: Build The Tray And Real Fastening Interfaces

**Files:**
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`
- Modify: `mechanical/desktop_enclosure/scad/parts.scad`

**Interfaces:**
- Produces `electronics_tray()`, `tray_stop_pads()`, `base_pilot_bosses()`, and rear-cover pressure posts.
- Removes the old three internal modules and `installed_service_parts()`.

- [ ] **Step 1: Add failing source and connectivity tests**

Require these source contracts:

```python
def test_service_tray_and_retention_contract():
    parts = scad_text("parts.scad")
    for module in (
        "module electronics_tray(", "module tray_stop_pads(",
        "module base_pilot_bosses(", "module rear_cover_pressure_posts(",
    ):
        assert module in parts
    for obsolete in (
        "camera_clamp", "controller_rail", "microphone_holder",
        "installed_service_parts",
    ):
        assert f"module {obsolete}(" not in parts
```

After export, require the tray mesh to be one component, watertight, Z-zero, and
no larger than `[96, 149, 15]`.

- [ ] **Step 2: Run source tests and verify RED**

Expected: failures because only the old floating parts exist.

- [ ] **Step 3: Implement the electronics tray**

Use a `96 x 149 x 3 mm` rounded backplane. Subtract:

- a large camera lens opening in the upper zone;
- paired camera tie slots around the `27 x 42 mm` envelope;
- repeated N16R8 horizontal and vertical tie slots in the center zone;
- paired NMO432 tie slots and an open acoustic path in the lower zone;
- cable-routing slots between all three zones.

Add fused camera side guides and lower microphone guides no higher than
`tray_feature_height`. Keep every guide overlapped with the backplane.

- [ ] **Step 4: Implement tray retention and screw pilots**

Add four shell stop pads fused to side walls with at least `1 mm` overlap. Add
four rear-cover pressure posts whose installed ends contact the tray plane.
Change shell rear bosses to `m3_pilot_diameter`; keep rear-cover holes at
`m3_clearance`. Add two fused lower-shell pilot bosses aligned with
`base_fastener_x`; keep base holes at `m3_clearance`.

- [ ] **Step 5: Update assembly and exploded views**

Install one tray at `tray_installed_y`; remove all three old placements. Show
the tray as one separated part in the exploded view.

- [ ] **Step 6: Export, run full mechanical tests, and commit source**

```powershell
powershell -ExecutionPolicy Bypass -File `
  mechanical\desktop_enclosure\scripts\export_models.ps1 -Export -Render
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pytest `
  mechanical\desktop_enclosure\tests\test_enclosure.py -q
git add mechanical/desktop_enclosure/scad/parts.scad `
  mechanical/desktop_enclosure/tests/test_enclosure.py
git commit -m "feat(mechanical): add removable electronics tray"
git push origin codex/preliminary-demo
```

---

### Task 3: Replace STL Assets

**Files:**
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`
- Delete: `mechanical/desktop_enclosure/stl/printable/camera_clamp.stl`
- Delete: `mechanical/desktop_enclosure/stl/printable/controller_rail.stl`
- Delete: `mechanical/desktop_enclosure/stl/printable/microphone_holder.stl`
- Create: `mechanical/desktop_enclosure/stl/printable/electronics_tray.stl`
- Modify: other current STL and render outputs generated from changed geometry

- [ ] **Step 1: Run the exact-directory test and verify RED**

Expected: it reports the three old STL names and missing `electronics_tray`.

- [ ] **Step 2: Remove only the three tracked old STL files**

Use explicit `git rm` paths. Do not remove the untracked
`camera_clamp.3mf` file.

- [ ] **Step 3: Re-export and inspect both renders**

Run the export command. Confirm the tray is visibly installed in assembly and
separated in the exploded view, with no floating part or overlap.

- [ ] **Step 4: Run mesh tests and commit assets**

```powershell
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pytest `
  mechanical\desktop_enclosure\tests\test_enclosure.py -q
git add mechanical/desktop_enclosure/stl mechanical/desktop_enclosure/renders `
  mechanical/desktop_enclosure/tests/test_enclosure.py
git commit -m "build(mechanical): export five-part enclosure"
git push origin codex/preliminary-demo
```

---

### Task 4: Document Assembly And Verify The Project

**Files:**
- Modify: `README.md`
- Modify: `mechanical/desktop_enclosure/README.md`
- Modify: `mechanical/desktop_enclosure/drawings/dimensions.md`
- Modify: `docs/developer-handoff.md`
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`

- [ ] **Step 1: Add failing documentation assertions**

Require `electronics_tray.stl`, `2.6 mm`, `pressure posts`, `insert from the
rear`, and the five production names. Reject the three old STL names in current
handoff documents.

- [ ] **Step 2: Rewrite the assembly sequence**

Document front panel, populated tray insertion, base fastening, cable routing,
and rear-cover pressure retention in exact order. State that cable ties and M3
screws are required and that pilot fit must be tested on the real print.

- [ ] **Step 3: Run final verification**

```powershell
powershell -ExecutionPolicy Bypass -File `
  mechanical\desktop_enclosure\scripts\export_models.ps1 -Export -Render
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pytest `
  mechanical\desktop_enclosure\tests\test_enclosure.py -q
host_pc\.venv\Scripts\python.exe -m pytest host_pc\tests -q `
  --basetemp=F:\iot_design\.pytest-native-root\five-part-final `
  -p no:cacheprovider
git diff --check
```

Expected: OpenSCAD exits 0, mechanical tests pass, all 384 host tests pass, and
Git reports no whitespace errors.

- [ ] **Step 4: Commit and push handoff**

```powershell
git add README.md docs/developer-handoff.md `
  mechanical/desktop_enclosure/README.md `
  mechanical/desktop_enclosure/drawings/dimensions.md `
  mechanical/desktop_enclosure/tests/test_enclosure.py
git commit -m "docs(mechanical): document five-part assembly"
git push origin codex/preliminary-demo
```
