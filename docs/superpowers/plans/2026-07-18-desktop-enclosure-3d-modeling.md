# StrokeGuard Desktop Enclosure 3D Modeling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a TinkerCAD presentation assembly and a verified parameterized OpenSCAD/STL package for the preliminary-round StrokeGuard desktop demonstrator enclosure.

**Architecture:** OpenSCAD is the manufacturing source of truth and exports independently printable parts from small parameter and part modules. A dedicated Python test environment validates source contracts, STL watertightness, and build-plate bounds. TinkerCAD contains a non-authoritative assembled and exploded presentation model whose design identity is recorded in the repository.

**Tech Stack:** OpenSCAD, PowerShell 5.1, Python 3.10+, pytest, trimesh, TinkerCAD MCP, ASCII Markdown.

## Global Constraints

- Display envelope: 220 mm wide, 300 mm high, 55 mm deep.
- Printable envelope: 214 mm wide, 300 mm high, 55 mm deep.
- Each printable part must fit a 220 by 220 mm XY build area.
- Nominal wall thickness is 3.0 mm.
- Initial moving clearance is 0.30 mm and locating-tongue clearance is 0.25 mm per side.
- M3 clearance holes are 3.4 mm.
- Front panel slot is `measured_panel_thickness + 0.40 mm`.
- The front face has only a centered 36 by 22 mm camera opening; the NMO432 acoustic path is hidden on the lower edge.
- Board mounting remains adjustable; no unmeasured board outline, hole spacing, or USB offset may be invented.
- The model includes only the N16R8, camera coprocessor, and NMO432 provisions.
- The TinkerCAD model is for presentation; OpenSCAD and exported STL files are the manufacturing authority.
- Existing unrelated untracked test caches, firmware build directories, and `TinkercadMPC/` must not be staged.

---

## File Map

- `mechanical/desktop_enclosure/README.md`: print, assembly, and handoff instructions.
- `mechanical/desktop_enclosure/requirements-dev.txt`: isolated geometry-test dependencies.
- `mechanical/desktop_enclosure/scad/parameters.scad`: shared dimensions and mode selection.
- `mechanical/desktop_enclosure/scad/parts.scad`: all printable modules and assembly placement helpers.
- `mechanical/desktop_enclosure/scad/strokeguard_enclosure.scad`: command-line entry point selecting one part, assembled view, or exploded view.
- `mechanical/desktop_enclosure/scripts/export_models.ps1`: OpenSCAD discovery, STL export, and PNG rendering.
- `mechanical/desktop_enclosure/tests/test_enclosure.py`: source contract and generated-mesh acceptance tests.
- `mechanical/desktop_enclosure/stl/printable/*.stl`: committed printable outputs.
- `mechanical/desktop_enclosure/stl/display/strokeguard-display.stl`: committed nominal display assembly.
- `mechanical/desktop_enclosure/renders/assembled.png`: assembled presentation render.
- `mechanical/desktop_enclosure/renders/exploded.png`: exploded presentation render.
- `mechanical/desktop_enclosure/drawings/dimensions.md`: dimension and fastener schedule.
- `mechanical/desktop_enclosure/tinkercad-design.json`: TinkerCAD design ID, URL, model name, and envelope only; no credentials or cookies.

---

### Task 1: Isolated Mechanical Toolchain and Contract Tests

**Files:**
- Create: `mechanical/desktop_enclosure/requirements-dev.txt`
- Create: `mechanical/desktop_enclosure/tests/test_enclosure.py`
- Create: `mechanical/desktop_enclosure/scripts/export_models.ps1`

**Interfaces:**
- Consumes: Windows PowerShell 5.1 and either `OPENSCAD_EXE`, `openscad.com` on PATH, or the standard OpenSCAD install path.
- Produces: `Find-OpenScad`, `Export-Stl`, and `Export-Render` PowerShell functions plus an isolated mechanical Python environment.

- [ ] **Step 1: Write the dependency declaration and failing toolchain-contract test**

Create `requirements-dev.txt`:

```text
pytest>=8.3,<9
trimesh>=4.8,<5
numpy>=2.1,<3
Pillow>=11,<12
```

Create a test that requires the isolated export interface:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_export_script_isolated_toolchain_contract():
    script = (ROOT / "scripts" / "export_models.ps1").read_text("utf-8")
    for contract in (
        "function Find-OpenScad", "function Invoke-CheckedOpenScad",
        "[switch]$InstallDependencies", "[switch]$Export",
        "[switch]$Render", "$env:OPENSCAD_EXE", "mechanical environment",
    ):
        assert contract in script
    assert "host_pc" not in script
```

- [ ] **Step 2: Run the contract test and verify RED**

Run:

```powershell
python -m venv mechanical\desktop_enclosure\.venv
mechanical\desktop_enclosure\.venv\Scripts\python -m pip install -r mechanical\desktop_enclosure\requirements-dev.txt
mechanical\desktop_enclosure\.venv\Scripts\python -m pytest mechanical\desktop_enclosure\tests\test_enclosure.py -v
```

Expected: FAIL because `scripts/export_models.ps1` does not exist.

- [ ] **Step 3: Implement OpenSCAD discovery and bounded export commands**

The PowerShell script must resolve OpenSCAD in this order:

```powershell
function Find-OpenScad {
    $candidates = @(
        $env:OPENSCAD_EXE,
        (Get-Command openscad.com -ErrorAction SilentlyContinue).Source,
        (Get-Command openscad.exe -ErrorAction SilentlyContinue).Source,
        'C:\Program Files\OpenSCAD\openscad.com',
        'C:\Program Files\OpenSCAD\openscad.exe'
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    if (-not $candidates) {
        throw 'OpenSCAD not found. Install OpenSCAD or set OPENSCAD_EXE.'
    }
    return $candidates[0]
}

function Invoke-CheckedOpenScad([string[]]$Arguments) {
    & (Find-OpenScad) @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "OpenSCAD exited with code $LASTEXITCODE"
    }
}
```

The script accepts `-InstallDependencies`, `-Export`, and `-Render` switches.
`-InstallDependencies` runs pip only inside `.venv`; it never modifies
`host_pc/.venv` or global Python.

- [ ] **Step 4: Install OpenSCAD if discovery still fails**

Run:

```powershell
winget install --id OpenSCAD.OpenSCAD --exact --accept-package-agreements --accept-source-agreements
```

Expected: OpenSCAD installs successfully, or winget reports it is already installed.

- [ ] **Step 5: Commit the toolchain test harness**

```powershell
git add mechanical/desktop_enclosure/requirements-dev.txt mechanical/desktop_enclosure/tests/test_enclosure.py mechanical/desktop_enclosure/scripts/export_models.ps1
git commit -m "test(mechanical): add enclosure geometry harness"
git push origin codex/preliminary-demo
```

---

### Task 2: Parameterized Body, Joint, Covers, and Base

**Files:**
- Create: `mechanical/desktop_enclosure/scad/parameters.scad`
- Create: `mechanical/desktop_enclosure/scad/parts.scad`
- Create: `mechanical/desktop_enclosure/scad/strokeguard_enclosure.scad`
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`

**Interfaces:**
- Consumes: global parameters from `parameters.scad` and command-line variables `part`, `variant`, and `panel_thickness`.
- Produces: OpenSCAD modules `upper_shell()`, `lower_shell()`, `upper_rear_cover()`, `lower_rear_cover()`, `base()`, `lean_support()`, `fit_coupon()`, `assembled_view()`, and `exploded_view()`.

- [ ] **Step 1: Extend tests for shell geometry and source safety**

```python
def test_body_modules_include_required_interfaces():
    parts = scad_text("parts.scad")
    for module in (
        "module upper_shell(", "module lower_shell(",
        "module upper_rear_cover(", "module lower_rear_cover(",
        "module base(", "module lean_support(", "module fit_coupon(",
    ):
        assert module in parts
    assert "panel_thickness + panel_clearance" in parts
    assert "camera_window[0]" in parts
    assert "camera_window[1]" in parts
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
mechanical\desktop_enclosure\.venv\Scripts\python -m pytest mechanical\desktop_enclosure\tests\test_enclosure.py -v
```

Expected: FAIL because body modules are absent.

- [ ] **Step 3: Implement shared parameters and body modules**

`parameters.scad` declares the approved values and derives:

```scad
display_width = 220;
printable_width = 214;
body_height = 300;
body_depth = 55;
wall = 3;
corner_radius = 3;
camera_window = [36, 22];
panel_clearance = 0.4;
moving_clearance = 0.3;
tongue_clearance = 0.25;
tongue_overlap = 8;
m3_clearance = 3.4;
lean_angle = 7;
split_height = body_height / 2;
body_width = variant == "display" ? display_width : printable_width;
```

Build shells from a rounded outer solid minus the inner cavity, rear service
opening, front-panel pocket, camera window, USB service windows, airflow slots,
joint clearances, and fastener paths. Keep all subtraction solids extending at
least 0.2 mm beyond the target face to avoid coincident OpenSCAD surfaces.

- [ ] **Step 4: Add the entry-point dispatcher**

`strokeguard_enclosure.scad` uses exact dispatch with a hard failure marker:

```scad
include <parameters.scad>
use <parts.scad>

part = is_undef(part) ? "assembled" : part;
variant = is_undef(variant) ? "printable" : variant;
panel_thickness = is_undef(panel_thickness) ? 2 : panel_thickness;

if (part == "upper_shell") upper_shell();
else if (part == "lower_shell") lower_shell();
else if (part == "upper_rear_cover") upper_rear_cover();
else if (part == "lower_rear_cover") lower_rear_cover();
else if (part == "base") base();
else if (part == "lean_support") lean_support();
else if (part == "fit_coupon") fit_coupon();
else if (part == "assembled") assembled_view();
else if (part == "exploded") exploded_view();
else if (part == "display_stl") assembled_view();
else assert(false, str("Unknown part: ", part));
```

Task 3 extends this dispatcher with service parts before STL export.

- [ ] **Step 5: Run tests and parse every body output with OpenSCAD**

Run each body mode to a temporary STL using `openscad.com -D
'part="upper_shell"' -o <temp.stl> strokeguard_enclosure.scad`, then repeat for
the remaining body modules. Expected: pytest PASS and OpenSCAD exits 0 for
every body part.

- [ ] **Step 6: Commit body geometry**

```powershell
git add mechanical/desktop_enclosure/scad mechanical/desktop_enclosure/tests/test_enclosure.py
git commit -m "feat(mechanical): model split desktop enclosure body"
git push origin codex/preliminary-demo
```

---

### Task 3: Adjustable Electronics Mounts and Service Parts

**Files:**
- Modify: `mechanical/desktop_enclosure/scad/parts.scad`
- Modify: `mechanical/desktop_enclosure/scad/strokeguard_enclosure.scad`
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`

**Interfaces:**
- Consumes: shell interior envelope and the shared clearance/fastener parameters.
- Produces: `camera_carriage()`, `camera_bezel()`, `controller_rail()`, `microphone_holder()`, and `usb_blank()` modules plus their entry-point dispatch modes.

- [ ] **Step 1: Write failing service-part contract tests**

```python
def test_service_modules_are_adjustable_and_do_not_claim_board_dimensions():
    parts = scad_text("parts.scad")
    for module in (
        "module camera_carriage(", "module camera_bezel(",
        "module controller_rail(", "module microphone_holder(",
        "module usb_blank(",
    ):
        assert module in parts
    assert "camera_adjustment = 10" in scad_text("parameters.scad")
    assert "board_hole_spacing" not in parts
    assert "fixed_usb_offset" not in parts
```

- [ ] **Step 2: Run the test and verify RED**

Expected: FAIL because service modules are absent.

- [ ] **Step 3: Implement the adjustable service parts**

Implement the following bounded geometry:

- Camera carriage: crossed 3.4 mm slots providing 10 mm X/Y adjustment and a
  slotted depth bracket; no fixed camera-board hole pattern.
- Camera bezel: 36 by 22 mm outer-window adapter with a replaceable center
  aperture parameter.
- Controller rail: one universal rail with repeated M2/M3 slots and cable-tie
  passages; instantiate it twice in assembly view.
- NMO432 holder: clip cavity, lower acoustic channel, and cable strain relief;
  do not close the microphone port.
- USB blank: snap-free sliding plate with 0.30 mm fit clearance so development
  cables can use either service window.

- [ ] **Step 4: Extend dispatcher and assembled/exploded placement**

Every new service part gets a direct `part` mode. `assembled_view()` places the
parts without overlap. `exploded_view()` translates each family along Y and Z
while retaining the same orientation as the assembly.

- [ ] **Step 5: Run source tests and OpenSCAD smoke exports**

Expected: all source tests PASS; every service part exports to a non-empty STL;
assembled and exploded modes render without OpenSCAD errors.

- [ ] **Step 6: Commit adjustable hardware mounts**

```powershell
git add mechanical/desktop_enclosure/scad mechanical/desktop_enclosure/tests/test_enclosure.py
git commit -m "feat(mechanical): add adjustable electronics mounts"
git push origin codex/preliminary-demo
```

---

### Task 4: Exported STL, Mesh Acceptance, and Presentation Renders

**Files:**
- Modify: `mechanical/desktop_enclosure/scripts/export_models.ps1`
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`
- Create: `mechanical/desktop_enclosure/stl/printable/*.stl`
- Create: `mechanical/desktop_enclosure/stl/display/strokeguard-display.stl`
- Create: `mechanical/desktop_enclosure/renders/assembled.png`
- Create: `mechanical/desktop_enclosure/renders/exploded.png`

**Interfaces:**
- Consumes: all OpenSCAD entry-point modes.
- Produces: deterministic exported artifacts and mesh validation results.

- [ ] **Step 1: Write failing mesh-validation tests**

```python
import trimesh

PRINTABLE_PARTS = (
    "upper_shell", "lower_shell", "upper_rear_cover", "lower_rear_cover",
    "base", "lean_support", "camera_carriage", "camera_bezel",
    "controller_rail", "microphone_holder", "usb_blank", "fit_coupon",
)


def load_mesh(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load_mesh(path, force="mesh", process=True)
    assert isinstance(mesh, trimesh.Trimesh)
    return mesh


def test_printable_meshes_are_watertight_and_fit_build_plate():
    for name in PRINTABLE_PARTS:
        path = ROOT / "stl" / "printable" / f"{name}.stl"
        assert path.stat().st_size > 256
        mesh = load_mesh(path)
        assert mesh.is_watertight, name
        extents = sorted(mesh.extents.tolist(), reverse=True)
        assert extents[1] <= 220.01, (name, mesh.extents)
```

- [ ] **Step 2: Verify RED before export**

Expected: FAIL because generated STL files do not exist.

- [ ] **Step 3: Complete deterministic export and render script**

The script clears only known output filenames beneath
`mechanical/desktop_enclosure/stl` and `renders`, exports each printable mode
with `variant="printable"`, exports `display_stl` with `variant="display"`, and
renders assembled/exploded PNGs at 1600 by 1200 pixels. It must never recurse
outside `mechanical/desktop_enclosure`.

- [ ] **Step 4: Export all artifacts and run full geometry tests**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File mechanical\desktop_enclosure\scripts\export_models.ps1 -Export -Render
mechanical\desktop_enclosure\.venv\Scripts\python -m pytest mechanical\desktop_enclosure\tests\test_enclosure.py -v
```

Expected: all exports exit 0; all meshes are non-empty and watertight; every
printable part passes the 220 by 220 mm XY-envelope test; both PNGs exist and
have non-zero image variance.

- [ ] **Step 5: Inspect assembled and exploded renders**

Open both PNGs and verify that the camera opening is centered, the front has no
extra visible openings, service windows are on the side walls, the base supports
the rearward lean, and exploded parts do not overlap incoherently.

- [ ] **Step 6: Commit generated deliverables**

```powershell
git add mechanical/desktop_enclosure/scripts mechanical/desktop_enclosure/tests mechanical/desktop_enclosure/stl mechanical/desktop_enclosure/renders
git commit -m "build(mechanical): export verified enclosure models"
git push origin codex/preliminary-demo
```

---

### Task 5: TinkerCAD Presentation Assembly

**Files:**
- Create: `mechanical/desktop_enclosure/tinkercad-design.json`
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`

**Interfaces:**
- Consumes: approved 220 by 300 by 55 mm display envelope and the rendered part layout.
- Produces: TinkerCAD design `StrokeGuard Desktop Demonstrator` and a credential-free repository manifest.

- [ ] **Step 1: Add the manifest contract test**

```python
import json


def test_tinkercad_manifest_is_credential_free_and_matches_display_envelope():
    data = json.loads((ROOT / "tinkercad-design.json").read_text("utf-8"))
    assert data["name"] == "StrokeGuard Desktop Demonstrator"
    assert data["envelope_mm"] == [220, 300, 55]
    assert data["design_id"]
    assert data["url"].startswith("https://www.tinkercad.com/")
    text = json.dumps(data).lower()
    assert "cookie" not in text and "token" not in text and "password" not in text
```

- [ ] **Step 2: Verify RED before creating the online model**

Expected: FAIL because `tinkercad-design.json` does not exist.

- [ ] **Step 3: Create the TinkerCAD design non-destructively**

Call `tinkercad_create_3d_design` with exactly:

```json
{"name":"StrokeGuard Desktop Demonstrator"}
```

Do not delete or overwrite any existing design. Record the returned design ID
and URL only after creation succeeds.

- [ ] **Step 4: Add assembled and exploded presentation primitives**

Use `tinkercad_add_shape` to place simple boxes and cylinders representing the
upper/lower body, front panel, centered camera bezel, base, rear support, rear
covers, camera carriage, controller rails, microphone holder, and USB blanks.
Place the assembled unit at the workspace origin and the exploded arrangement
at least 300 mm to its right. This online representation must retain the 220 by
300 by 55 mm nominal assembled envelope.

- [ ] **Step 5: Verify TinkerCAD session and persist the manifest**

Call `tinkercad_get_session_status`, then `tinkercad_list_designs`. Verify the
new name and design ID are present. Create `tinkercad-design.json` with exactly
five keys: `name` set to `StrokeGuard Desktop Demonstrator`, `design_id` set to
the ID returned by the create call, `url` set to that call's returned URL,
`envelope_mm` set to `[220, 300, 55]`, and `authority` set to
`presentation-only`. Write the actual returned strings directly into the file;
do not store an OAuth session, cookie, password, token, or example identifier.

- [ ] **Step 6: Run the manifest test and commit**

```powershell
mechanical\desktop_enclosure\.venv\Scripts\python -m pytest mechanical\desktop_enclosure\tests\test_enclosure.py -v
git add mechanical/desktop_enclosure/tinkercad-design.json mechanical/desktop_enclosure/tests/test_enclosure.py
git commit -m "feat(mechanical): publish TinkerCAD enclosure assembly"
git push origin codex/preliminary-demo
```

---

### Task 6: Mechanical Handoff and Final Acceptance

**Files:**
- Create: `mechanical/desktop_enclosure/README.md`
- Create: `mechanical/desktop_enclosure/drawings/dimensions.md`
- Modify: `README.md`
- Modify: `docs/developer-handoff.md`

**Interfaces:**
- Consumes: verified SCAD, STL, PNG, and TinkerCAD manifest outputs.
- Produces: reproducible setup, print, assembly, and transfer instructions.

- [ ] **Step 1: Write documentation contract tests**

```python
def test_handoff_documents_required_limits_and_workflow():
    readme = (ROOT / "README.md").read_text("utf-8")
    for phrase in (
        "214 x 300 x 55 mm", "220 x 300 x 55 mm",
        "fit coupon", "NMO432", "camera", "OpenSCAD", "TinkerCAD",
        "not a diagnostic device",
    ):
        assert phrase.lower() in readme.lower()
```

- [ ] **Step 2: Verify RED before documentation**

Expected: FAIL because the mechanical README is absent.

- [ ] **Step 3: Write the mechanical README and dimension schedule**

Document exact dependency installation, virtual-environment setup, export and
test commands, part list, print orientation, initial slicer settings, fit-coupon
sequence, M3 fastener schedule, assembly order, board adjustment, camera framing,
hidden NMO432 acoustic path, USB service access, and measured-result recording.
State that print values are first-print settings and that front-panel thickness
is an explicit input.

- [ ] **Step 4: Link the mechanical package from project handoff docs**

Add one concise section to the root README and developer handoff. Do not add
claims about clinical accuracy, ingress protection, certification, or measured
thermal/acoustic performance.

- [ ] **Step 5: Run final verification**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File mechanical\desktop_enclosure\scripts\export_models.ps1 -Export -Render
mechanical\desktop_enclosure\.venv\Scripts\python -m pytest mechanical\desktop_enclosure\tests\test_enclosure.py -v
git diff --check
git status --short
```

Expected: all mechanical tests pass; exports are fresh; no whitespace errors;
only intentional mechanical documentation changes are staged for the final
commit; unrelated untracked cache/build files remain untouched.

- [ ] **Step 6: Commit and push the handoff**

```powershell
git add README.md docs/developer-handoff.md mechanical/desktop_enclosure/README.md mechanical/desktop_enclosure/drawings/dimensions.md mechanical/desktop_enclosure/tests/test_enclosure.py
git commit -m "docs(mechanical): add printable enclosure handoff"
git push origin codex/preliminary-demo
```

---

## Final Review Gate

- OpenSCAD manufacturing source matches the approved specification.
- Printable and display dimensions are not conflated.
- All listed STL files are generated, watertight, and build-plate bounded.
- Assembled and exploded renders are visually inspected.
- The fit coupon is available before full-shell printing.
- TinkerCAD design exists and its manifest contains no credentials.
- The handoff explains how another developer changes measured panel and board
  placement parameters without redesigning the enclosure.
- No original audio/video data, cloud secrets, medical claims, or unrelated
  project artifacts are introduced by the mechanical package.
