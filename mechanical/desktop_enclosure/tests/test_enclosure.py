from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def scad_text(name: str) -> str:
    return (ROOT / "scad" / name).read_text(encoding="utf-8")


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


def test_assembled_body_uses_one_front_panel_and_installs_rear_covers():
    parts = scad_text("parts.scad")
    assert "front_panel(body_height, camera = true);" in parts
    assert "front_panel(split_height" not in parts
    assert "module installed_rear_covers(" in parts
    assert "installed_rear_covers();" in parts
