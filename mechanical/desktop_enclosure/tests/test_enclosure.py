from pathlib import Path

import numpy as np
import trimesh
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PRINTABLE_PARTS = (
    "compact_shell",
    "front_panel",
    "electronics_tray",
    "rear_cover",
    "desktop_base",
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
    "camera_clamp",
    "controller_rail",
    "microphone_holder",
}


def scad_text(name: str) -> str:
    return (ROOT / "scad" / name).read_text(encoding="utf-8")


def load_mesh(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load_mesh(path, force="mesh", process=True)
    assert isinstance(mesh, trimesh.Trimesh)
    return mesh


def mesh_component_count(mesh: trimesh.Trimesh) -> int:
    parent = list(range(len(mesh.vertices)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    used_vertices: set[int] = set()
    for face in mesh.faces:
        first = int(face[0])
        used_vertices.update(int(index) for index in face)
        union(first, int(face[1]))
        union(first, int(face[2]))

    return len({find(index) for index in used_vertices})


def unsupported_downward_area(mesh: trimesh.Trimesh) -> float:
    mask = (mesh.face_normals[:, 2] < -0.2) & (mesh.triangles_center[:, 2] > 0.25)
    return float(mesh.area_faces[mask].sum())


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


def test_five_part_parameter_contract():
    parameters = scad_text("parameters.scad")
    for declaration in (
        "tray_width = 96",
        "tray_height = 149",
        "tray_thickness = 3",
        "tray_feature_height = 12",
        "m3_pilot_diameter = 2.6",
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
        "module electronics_tray(",
    ):
        assert module in parts
    assert "camera_aperture_diameter" in parts
    assert "camera_board[0] + 2 * camera_clearance" in parts
    assert "camera_board_hole_spacing" not in parts


def test_service_tray_and_retention_contract():
    parts = scad_text("parts.scad")
    for module in (
        "module electronics_tray(",
        "module tray_stop_pads(",
        "module base_pilot_bosses(",
        "module rear_cover_pressure_posts(",
    ):
        assert module in parts
    for obsolete in (
        "camera_clamp",
        "controller_rail",
        "microphone_holder",
        "installed_service_parts",
    ):
        assert f"module {obsolete}(" not in parts
    assert "m3_pilot_diameter" in parts


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
    assert (
        "translate([0, 0, base_height + 4])\n"
        "            rotate([-lean_angle, 0, 0])"
    ) in parts
    assert "module lean_support(" not in parts
    assert "cover_height / 2" in parts
    assert "cube([18, 8" in parts


def test_assembly_places_only_compact_parts():
    parts = scad_text("parts.scad")
    assert "module assembled_body(" in parts
    assert "compact_shell_model();" in parts
    assert "installed_front_and_rear();" in parts
    assert "installed_electronics_tray();" in parts
    assert "desktop_base();" in parts


def test_tray_is_sandwiched_between_shell_stops_and_cover_posts():
    parts = scad_text("parts.scad")
    assert "stop_y = tray_installed_y - tray_thickness - moving_clearance - 2" in parts
    assert "body_depth / 2 - tray_installed_y - moving_clearance" in parts
    assert "translate([0, tray_installed_y, body_height / 2])" in parts


def test_printable_meshes_are_watertight_and_fit_build_plate():
    for name in PRINTABLE_PARTS:
        path = ROOT / "stl" / "printable" / f"{name}.stl"
        assert path.stat().st_size > 256
        mesh = load_mesh(path)
        assert mesh.is_watertight, name
        assert mesh_component_count(mesh) == 1, name
        extents = sorted(mesh.extents.tolist(), reverse=True)
        assert extents[1] <= 220.01, (name, mesh.extents)


def test_printable_directory_contains_only_compact_parts():
    actual = {path.stem for path in (ROOT / "stl" / "printable").glob("*.stl")}
    assert actual == set(PRINTABLE_PARTS)


def test_compact_body_panel_and_base_envelopes():
    shell = load_mesh(ROOT / "stl" / "printable" / "compact_shell.stl")
    assert np.allclose(shell.extents, [165, 40, 110], atol=0.01)
    assert abs(float(shell.bounds[0][2])) <= 0.01
    assert mesh_component_count(shell) == 1

    panel = load_mesh(ROOT / "stl" / "printable" / "front_panel.stl")
    assert np.allclose(panel.extents, [104, 159, 2], atol=0.01)

    base = load_mesh(ROOT / "stl" / "printable" / "desktop_base.stl")
    assert np.allclose(base.extents, [110, 65, 12], atol=0.01)
    assert unsupported_downward_area(base) < 1.0


def test_electronics_tray_is_printable_and_within_envelope():
    tray = load_mesh(ROOT / "stl" / "printable" / "electronics_tray.stl")
    assert tray.is_watertight
    assert mesh_component_count(tray) == 1
    assert np.all(tray.extents <= np.array([96.01, 149.01, 15.01]))
    assert abs(float(tray.bounds[0][2])) <= 0.01
    assert unsupported_downward_area(tray) < 1.0


def test_display_stl_and_renders_are_nonblank():
    display_stl = ROOT / "stl" / "display" / "strokeguard-display.stl"
    assert display_stl.stat().st_size > 256
    assert load_mesh(display_stl).is_watertight

    for name in ("assembled.png", "exploded.png"):
        path = ROOT / "renders" / name
        image = Image.open(path).convert("RGB")
        assert image.size == (1600, 1200)
        assert float(np.asarray(image).std()) > 5.0


def test_compact_handoff_documents_match_current_production_model():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    dimensions = (ROOT / "drawings" / "dimensions.md").read_text(encoding="utf-8")
    combined_handoff = f"{readme}\n{dimensions}"

    for phrase in (
        "110 x 165 x 40 mm",
        "12 mm",
        "27 x 42 x 19 mm",
        "compact_shell.stl",
        "front_panel.stl",
        "electronics_tray.stl",
        "rear_cover.stl",
        "desktop_base.stl",
        "exactly five",
        "smooth visible face",
        "populate the electronics tray first",
        "insert the populated tray from the rear",
        "shell stop pads",
        "rear-cover pressure posts",
        "3.4 mm",
        "2.6 mm",
        "cable ties",
        "physical print",
        "not a diagnostic device",
    ):
        assert phrase.lower() in combined_handoff.lower()

    for obsolete in (
        "214 x 300",
        "front_panel_upper.stl",
        "rear lap",
        "36 x 22 mm",
        "camera_clamp.stl",
        "controller_rail.stl",
        "microphone_holder.stl",
        "seven production",
    ):
        assert obsolete.lower() not in combined_handoff.lower()

    repository_root = ROOT.parents[1]
    for path in (repository_root / "README.md", repository_root / "docs" / "developer-handoff.md"):
        text = path.read_text(encoding="utf-8")
        assert "mechanical/desktop_enclosure" in text
