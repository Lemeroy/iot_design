# Tool-Free PLA Enclosure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a five-part PLA enclosure that assembles without screws or a screwdriver.

**Architecture:** Replace screw loading with rigid sliding interfaces and use one low-deflection latch only where each removable closure needs axial retention. Keep board retention on the removable tray with open guides and cable ties.

**Tech Stack:** OpenSCAD 2021.01, PowerShell 5.1, Python, pytest, trimesh, Git.

## Global Constraints

- Keep exactly five production STL files and the `110 x 165 x 40 mm` body.
- Use `0.6 mm` front-panel edge clearance and `1.5 mm` retaining-lip overlap.
- Use one `30 mm` open guide channel for both camera and N16R8 widths.
- Use `0.5 mm` total rear slide clearance.
- Remove all M3 holes, pilot bosses, and screw instructions.
- Do not modify untracked firmware, Tinkercad, 3MF, or G-code content.

---

### Task 1: Lock The Tool-Free Source Contract

**Files:**
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`
- Modify: `mechanical/desktop_enclosure/scad/parameters.scad`

**Interfaces:**
- Produces the fit and latch parameters consumed by all geometry modules.

- [ ] Add failing tests for `panel_clearance = 0.6`,
  `front_lip_overlap = 1.5`, `rear_slide_clearance = 0.5`,
  `rear_latch_engagement = 0.6`, and `base_latch_engagement = 0.5`.
- [ ] Require modules named `front_panel_retaining_lip`,
  `front_panel_stop_tabs`, `rear_cover_slide_rails`,
  `rear_cover_release_latch`, and `base_release_latch`.
- [ ] Reject `rear_cover_bosses`, `base_pilot_bosses`,
  `rear_cover_pressure_posts`, `m3_clearance`, and `m3_pilot_diameter`.
- [ ] Run the focused tests and verify they fail on the current screw-based model.

### Task 2: Implement Front And Tray Fit

**Files:**
- Modify: `mechanical/desktop_enclosure/scad/parts.scad`
- Modify: `mechanical/desktop_enclosure/scad/parameters.scad`
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`

**Interfaces:**
- Produces a retained `102.8 x 157.8 x 2 mm` front panel.
- Produces an open-ended `30 mm` shared board channel on the tray.

- [ ] Add the fused front lip and four short rear stops, then remove the
  full-height side rails.
- [ ] Apply edge clearance to both front-panel dimensions.
- [ ] Replace the camera cage cross stops with a shared open channel whose two
  lateral rails serve the camera and N16R8 zones.
- [ ] Export and run the panel/tray envelope and mesh tests.

### Task 3: Implement Tool-Free Rear Cover And Base

**Files:**
- Modify: `mechanical/desktop_enclosure/scad/parts.scad`
- Modify: `mechanical/desktop_enclosure/tests/test_enclosure.py`

**Interfaces:**
- Produces rear side channels, one cover release tongue and pocket, tray spacer
  ribs, and one rear base release tongue.

- [ ] Remove rear-cover screw bosses and holes.
- [ ] Add two fused rear C-channels and a bottom stop plane.
- [ ] Cut relief slots around one long cover tongue, add its shallow engagement
  bump, and add the matching shell pocket.
- [ ] Remove base holes and lower shell pilot bosses.
- [ ] Add an isolated rear base flexure with a sloped hook that catches the
  shell's lower rear edge.
- [ ] Re-export and require every STL to remain one watertight component with
  unsupported downward area below the existing tolerance.

### Task 4: Update Handoff And Verify

**Files:**
- Modify: `README.md`
- Modify: `docs/developer-handoff.md`
- Modify: `mechanical/desktop_enclosure/README.md`
- Modify: `mechanical/desktop_enclosure/drawings/dimensions.md`
- Modify: generated `mechanical/desktop_enclosure/stl/` and `renders/`

**Interfaces:**
- Documents the five-step tool-free assembly and PLA durability limitation.

- [ ] Remove M3 installation instructions and document front-panel tilt-in,
  tray insertion, base latch, rear-cover slide, and hand-release operations.
- [ ] State that all five parts require reprinting and that physical fit remains
  pending the next PLA print.
- [ ] Run OpenSCAD export/render, all mechanical tests, all host tests, and
  `git diff --check`.
- [ ] Commit and push only tracked project files to `codex/preliminary-demo`.

