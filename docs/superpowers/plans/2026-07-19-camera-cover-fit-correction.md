# Camera And Rear-Cover Fit Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the first-print camera-guide and rear-cover interferences without changing the five-part enclosure or external envelope.

**Architecture:** Keep the integrated electronics tray and parameterize the three physical-fit corrections. Derive rear-cover post length in installed coordinates so a tray-position change cannot recreate the interference.

**Tech Stack:** OpenSCAD 2021.01, PowerShell 5.1, Python, pytest, trimesh, Git.

## Global Constraints

- Camera-guide clear opening is `30 mm`.
- Electronics tray installed position is `Y=2 mm` toward the rear.
- Rear-cover post-to-tray assembly gap is `0.5 mm`.
- Keep the `110 x 165 x 40 mm` body and exactly five production STL files.
- Do not add board-hole coordinates or delete untracked 3MF/G-code files.

---

### Task 1: Lock And Implement Physical-Fit Parameters

**Files:**
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`
- Modify: `mechanical/desktop_enclosure/scad/parameters.scad`
- Modify: `mechanical/desktop_enclosure/scad/parts.scad`

**Interfaces:**
- Produces: `camera_mount_inner_width`, `tray_installed_y`, and `rear_cover_post_gap` OpenSCAD parameters.
- Consumes: existing camera board envelope and rear-cover installation transform.

- [ ] **Step 1: Write failing source-contract tests**

Require these declarations and formulas:

```python
for declaration in (
    "camera_mount_inner_width = 30",
    "tray_installed_y = 2",
    "rear_cover_post_gap = 0.5",
):
    assert declaration in parameters

assert "camera_mount_inner_width" in parts
assert "body_depth / 2 - 2 * rear_cover_thickness" in parts
assert "rear_cover_post_gap" in parts
```

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pytest `
  mechanical\desktop_enclosure\tests\test_enclosure.py::test_physical_camera_and_cover_fit_contract -v
```

Expected: failure because the new parameters and corrected post formula are absent.

- [ ] **Step 3: Implement the minimum geometry correction**

Use `camera_mount_inner_width` for the side-guide opening. Set the tray position
to `2 mm`. Compute pressure-post height from the rear-cover inner face to
`tray_installed_y + rear_cover_post_gap`, accounting for the cover placement and
the post's overlap into the cover plate.

- [ ] **Step 4: Re-export and verify GREEN**

```powershell
powershell -ExecutionPolicy Bypass -File `
  mechanical\desktop_enclosure\scripts\export_models.ps1 -Export -Render
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pytest `
  mechanical\desktop_enclosure\tests\test_enclosure.py -q
```

Expected: OpenSCAD exits `0` and all mechanical tests pass.

### Task 2: Update Handoff And Complete Verification

**Files:**
- Modify: `mechanical/desktop_enclosure/README.md`
- Modify: `mechanical/desktop_enclosure/drawings/dimensions.md`
- Modify: generated files under `mechanical/desktop_enclosure/stl/` and `renders/`

**Interfaces:**
- Documents the exact prototype clearances used by Task 1.

- [ ] **Step 1: Document the changed fit and reprint scope**

State that the camera opening is `30 mm`, the tray shifts rearward `2 mm`, and
the pressure posts leave `0.5 mm` nominal clearance. Identify the tray and rear
cover as mandatory reprints; the shell is also reprinted because tray stop
locations follow the shifted tray plane.

- [ ] **Step 2: Run complete verification**

```powershell
mechanical\desktop_enclosure\.venv\Scripts\python.exe -m pytest `
  mechanical\desktop_enclosure\tests\test_enclosure.py -q
host_pc\.venv\Scripts\python.exe -m pytest host_pc\tests -q `
  -p no:cacheprovider --basetemp=F:\iot_design\.pytest-camera-fit-final
git diff --check
```

Expected: all mechanical tests and all host tests pass with no whitespace errors.

- [ ] **Step 3: Commit and push**

```powershell
git add docs/superpowers mechanical/desktop_enclosure
git commit -m "fix(mechanical): correct camera and rear-cover fit"
git push origin codex/preliminary-demo
```

