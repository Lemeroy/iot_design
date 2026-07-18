import json
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PRINTABLE_PARTS = (
    "upper_shell",
    "lower_shell",
    "upper_rear_cover",
    "lower_rear_cover",
    "base",
    "lean_support",
    "camera_carriage",
    "camera_bezel",
    "controller_rail",
    "microphone_holder",
    "usb_blank",
    "fit_coupon",
    "front_panel_upper",
    "front_panel_lower",
)


def scad_text(name: str) -> str:
    return (ROOT / "scad" / name).read_text(encoding="utf-8")


def load_mesh(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load_mesh(path, force="mesh", process=True)
    assert isinstance(mesh, trimesh.Trimesh)
    return mesh


def test_export_script_isolated_toolchain_contract():
    script = (ROOT / "scripts" / "export_models.ps1").read_text(encoding="utf-8")
    for contract in (
        "function Find-OpenScad",
        "function Invoke-CheckedOpenScad",
        "[switch]$InstallDependencies",
        "[switch]$Export",
        "[switch]$Render",
        "$env:OPENSCAD_EXE",
        "mechanical environment",
    ):
        assert contract in script

    assert "host_pc" not in script


def test_export_script_preserves_scad_string_quotes_on_windows_powershell():
    script = (ROOT / "scripts" / "export_models.ps1").read_text(encoding="utf-8")
    assert r'part=\`"$Part\`"' in script
    assert r'variant=\`"$Variant\`"' in script


def test_scad_contract_declares_approved_dimensions():
    parameters = scad_text("parameters.scad")
    for declaration in (
        "display_width = 220",
        "printable_width = 214",
        "body_height = 300",
        "body_depth = 55",
        "wall = 3",
        "camera_window = [36, 22]",
        "m3_clearance = 3.4",
        "lean_angle = 7",
    ):
        assert declaration in parameters


def test_body_modules_include_required_interfaces():
    parts = scad_text("parts.scad")
    for module in (
        "module upper_shell(",
        "module lower_shell(",
        "module upper_rear_cover(",
        "module lower_rear_cover(",
        "module base(",
        "module lean_support(",
        "module fit_coupon(",
    ):
        assert module in parts

    assert "panel_thickness + panel_clearance" in parts
    assert "camera_window[0]" in parts
    assert "camera_window[1]" in parts


def test_body_joint_has_four_rear_fastener_positions():
    parameters = scad_text("parameters.scad")
    parts = scad_text("parts.scad")
    assert "joint_fastener_x = [-75, -25, 25, 75]" in parameters
    assert "for (x = joint_fastener_x)" in parts


def test_rear_covers_have_matching_shell_bosses():
    parameters = scad_text("parameters.scad")
    parts = scad_text("parts.scad")
    assert "rear_cover_fastener_x = [-90, 90]" in parameters
    assert "rear_cover_fastener_z = [-58, 58]" in parameters
    assert "rear_cover_boss_diameter = 12" in parameters
    assert "module rear_cover_bosses(" in parts
    assert "rear_cover_bosses(section_height);" in parts


def test_base_and_lean_support_share_fastener_positions():
    parameters = scad_text("parameters.scad")
    parts = scad_text("parts.scad")
    assert "base_support_fastener_x = [-36, 36]" in parameters
    assert "base_support_fastener_y = 20" in parameters
    assert "for (x = base_support_fastener_x)" in parts
    assert "support_mount_offset_y = 8" in parameters


def test_entry_point_exposes_body_output_modes():
    entry = scad_text("strokeguard_enclosure.scad")
    for mode in (
        '"upper_shell"',
        '"lower_shell"',
        '"upper_rear_cover"',
        '"lower_rear_cover"',
        '"base"',
        '"lean_support"',
        '"fit_coupon"',
        '"assembled"',
        '"exploded"',
        '"display_stl"',
    ):
        assert mode in entry
    assert 'else if (part == "display_stl") display_stl_model();' in entry


def test_assembled_body_uses_split_front_panel_and_installs_rear_covers():
    parts = scad_text("parts.scad")
    assert "front_panel_assembled();" in parts
    assert "module installed_rear_covers(" in parts
    assert "installed_rear_covers();" in parts


def test_service_modules_are_adjustable_and_do_not_claim_board_dimensions():
    parts = scad_text("parts.scad")
    for module in (
        "module camera_carriage(",
        "module camera_bezel(",
        "module controller_rail(",
        "module microphone_holder(",
        "module usb_blank(",
    ):
        assert module in parts

    assert "camera_adjustment = 10" in scad_text("parameters.scad")
    assert "board_hole_spacing" not in parts
    assert "fixed_usb_offset" not in parts


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


def test_entry_point_exposes_service_part_modes():
    entry = scad_text("strokeguard_enclosure.scad")
    for mode in (
        '"camera_carriage"',
        '"camera_bezel"',
        '"controller_rail"',
        '"microphone_holder"',
        '"usb_blank"',
    ):
        assert mode in entry


def test_assembly_places_service_parts():
    parts = scad_text("parts.scad")
    assert "module installed_service_parts(" in parts
    assert "installed_service_parts();" in parts
    assert "module camera_lens_placeholder(" in parts
    assert "camera_lens_placeholder();" in parts


def test_printable_meshes_are_watertight_and_fit_build_plate():
    for name in PRINTABLE_PARTS:
        path = ROOT / "stl" / "printable" / f"{name}.stl"
        assert path.stat().st_size > 256
        mesh = load_mesh(path)
        assert mesh.is_watertight, name
        extents = sorted(mesh.extents.tolist(), reverse=True)
        assert extents[1] <= 220.01, (name, mesh.extents)
        if name in ("upper_shell", "lower_shell"):
            assert mesh.extents[1] <= 55.01, (name, mesh.extents)


def test_display_stl_and_renders_are_nonblank():
    display_stl = ROOT / "stl" / "display" / "strokeguard-display.stl"
    assert display_stl.stat().st_size > 256
    assert load_mesh(display_stl).is_watertight

    for name in ("assembled.png", "exploded.png"):
        path = ROOT / "renders" / name
        image = Image.open(path).convert("RGB")
        assert image.size == (1600, 1200)
        assert float(np.asarray(image).std()) > 5.0


def test_split_panels_match_enclosure_and_camera_contract():
    upper = load_mesh(ROOT / "stl" / "printable" / "front_panel_upper.stl")
    lower = load_mesh(ROOT / "stl" / "printable" / "front_panel_lower.stl")
    assert upper.is_watertight and lower.is_watertight
    assert upper.extents[0] <= 208.01
    assert lower.extents[0] <= 208.01
    assert upper.extents[1] <= 220.01
    assert lower.extents[1] <= 220.01
    assert upper.extents[2] <= 4.01
    assert lower.extents[2] <= 4.01


def test_exploded_view_exposes_panel_rear_ribs():
    parts = scad_text("parts.scad")
    assert "rotate([180, 0, 0]) front_panel_upper_printable();" in parts
    assert "rotate([180, 0, 0]) front_panel_lower_printable();" in parts


def test_tinkercad_manifest_is_credential_free_and_matches_display_envelope():
    data = json.loads((ROOT / "tinkercad-design.json").read_text(encoding="utf-8"))
    assert data["name"] == "StrokeGuard Desktop Demonstrator"
    assert data["envelope_mm"] == [220, 300, 55]
    assert data["design_id"]
    assert data["url"].startswith("https://www.tinkercad.com/")
    assert data["authority"] == "presentation-only"

    serialized = json.dumps(data).lower()
    for forbidden in ("cookie", "token", "password", "oauth"):
        assert forbidden not in serialized


def test_handoff_documents_required_limits_and_workflow():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for phrase in (
        "214 x 300 x 55 mm",
        "220 x 300 x 55 mm",
        "fit coupon",
        "NMO432",
        "camera",
        "OpenSCAD",
        "TinkerCAD",
        "not a diagnostic device",
    ):
        assert phrase.lower() in readme.lower()

    dimensions = (ROOT / "drawings" / "dimensions.md").read_text(encoding="utf-8")
    assert "M3" in dimensions
    assert "3.4 mm" in dimensions
    assert "36 x 22 mm" in dimensions

    repository_root = ROOT.parents[1]
    for path in (repository_root / "README.md", repository_root / "docs" / "developer-handoff.md"):
        text = path.read_text(encoding="utf-8")
        assert "mechanical/desktop_enclosure" in text
