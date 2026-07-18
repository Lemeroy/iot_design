from pathlib import Path

import numpy as np
import trimesh
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
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
    "upper_shell",
    "lower_shell",
    "upper_rear_cover",
    "lower_rear_cover",
    "base",
    "lean_support",
    "camera_carriage",
    "camera_bezel",
    "usb_blank",
    "fit_coupon",
    "front_panel_upper",
    "front_panel_lower",
}


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


def test_compact_parameter_contract():
    parameters = scad_text("parameters.scad")
    for declaration in (
        "body_width = 110",
        "body_height = 165",
        "body_depth = 40",
        "camera_aperture_diameter = 12",
        "camera_board = [27, 42, 19]",
        "camera_position_z = body_height - 24",
        "base_width = 110",
        "base_depth = 65",
        "base_height = 12",
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
    for mode in ("assembled", "exploded", "display_stl"):
        assert f'"{mode}"' in entry


def test_compact_modules_and_camera_contract():
    parts = scad_text("parts.scad")
    for module in (
        "module compact_shell(",
        "module front_panel(",
        "module rear_cover(",
        "module desktop_base(",
        "module camera_clamp(",
        "module controller_rail(",
        "module microphone_holder(",
    ):
        assert module in parts
    assert "camera_aperture_diameter" in parts
    assert "camera_board[0] + 2 * camera_clearance" in parts
    assert "camera_board_hole_spacing" not in parts


def test_large_geometry_modules_are_removed():
    parts = scad_text("parts.scad")
    for obsolete in (
        "upper_shell",
        "lower_shell",
        "joint_tongue",
        "lean_support",
        "front_panel_upper_printable",
        "front_panel_lower_printable",
        "camera_bezel",
        "usb_blank",
    ):
        assert f"module {obsolete}(" not in parts


def test_shell_has_front_rails_rear_bosses_and_base_fasteners():
    parts = scad_text("parts.scad")
    assert "module front_panel_rails(" in parts
    assert "module rear_cover_bosses(" in parts
    assert "for (x = base_fastener_x)" in parts
    assert "m3_clearance" in parts


def test_base_integrates_lean_and_rear_cover_has_cable_exit():
    parts = scad_text("parts.scad")
    assert "rotate([lean_angle, 0, 0])" in parts
    assert "module lean_support(" not in parts
    assert "cover_height / 2" in parts
    assert "cube([18, 8" in parts


def test_assembly_places_only_compact_parts():
    parts = scad_text("parts.scad")
    assert "module assembled_body(" in parts
    assert "compact_shell();" in parts
    assert "installed_front_and_rear();" in parts
    assert "installed_service_parts();" in parts
    assert "desktop_base();" in parts


def test_camera_clamp_installation_is_constrained_inside_body():
    parts = scad_text("parts.scad")
    assert "clamp_center_z = min(" in parts
    assert "body_height - wall - clamp_height / 2" in parts


def test_printable_meshes_are_watertight_and_fit_build_plate():
    for name in PRINTABLE_PARTS:
        path = ROOT / "stl" / "printable" / f"{name}.stl"
        assert path.stat().st_size > 256
        mesh = load_mesh(path)
        assert mesh.is_watertight, name
        extents = sorted(mesh.extents.tolist(), reverse=True)
        assert extents[1] <= 220.01, (name, mesh.extents)


def test_compact_body_panel_and_base_envelopes():
    shell = load_mesh(ROOT / "stl" / "printable" / "compact_shell.stl")
    assert np.all(shell.extents <= np.array([110.01, 40.01, 165.01]))

    panel = load_mesh(ROOT / "stl" / "printable" / "front_panel.stl")
    assert np.allclose(panel.extents, [104, 159, 2], atol=0.01)

    base = load_mesh(ROOT / "stl" / "printable" / "desktop_base.stl")
    assert np.allclose(base.extents, [110, 65, 12], atol=0.01)


def test_camera_clamp_stays_within_service_depth():
    clamp = load_mesh(ROOT / "stl" / "printable" / "camera_clamp.stl")
    assert np.all(clamp.extents <= np.array([40, 52, 24]))
    assert clamp.extents[2] >= 22


def test_display_stl_and_renders_are_nonblank():
    display_stl = ROOT / "stl" / "display" / "strokeguard-display.stl"
    assert display_stl.stat().st_size > 256
    assert load_mesh(display_stl).is_watertight

    for name in ("assembled.png", "exploded.png"):
        path = ROOT / "renders" / name
        image = Image.open(path).convert("RGB")
        assert image.size == (1600, 1200)
        assert float(np.asarray(image).std()) > 5.0
