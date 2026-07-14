"""Static tests for the M1b hardware scaffold.

Sensors are not delivered yet, so this test locks the compile-time boundaries:
drivers are present, disabled by default, and wiring is documented as
unconfirmed instead of being hard-coded.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FW_MAIN = ROOT / "firmware_esp32" / "main"
DOCS = ROOT / "docs"

MODULES = {
    "board_pins": ["SG_PIN_UNASSIGNED"],
    "camera_coprocessor": ["sg_camera_coprocessor_init", "sg_camera_coprocessor_poll"],
    "audio_inmp441": ["sg_audio_inmp441_init", "sg_audio_inmp441_read_mfcc"],
    "display_st7789": ["sg_display_st7789_init", "sg_display_st7789_show_status"],
    "audio_out_max98357": ["sg_audio_out_max98357_init", "sg_audio_out_max98357_play_prompt"],
    "alert_io": ["sg_alert_io_init", "sg_alert_io_set_level"],
}

KCONFIG_SYMBOLS = [
    "STROKEGUARD_CAMERA_COPROCESSOR_ENABLE",
    "STROKEGUARD_NMO432_ENABLE",
    "STROKEGUARD_HW_DISPLAY_ENABLE",
    "STROKEGUARD_HW_AUDIO_OUT_ENABLE",
    "STROKEGUARD_HW_ALERT_ENABLE",
    "STROKEGUARD_CAMERA_I2C_SDA",
    "STROKEGUARD_CAMERA_I2C_SCL",
    "STROKEGUARD_CAMERA_I2C_ADDRESS",
    "STROKEGUARD_NMO432_BCLK",
    "STROKEGUARD_PIN_ST7789_MOSI",
    "STROKEGUARD_PIN_MAX98357_DIN",
    "STROKEGUARD_PIN_ALERT_RGB",
    "STROKEGUARD_PIN_BUTTON_1",
]


def test_hardware_scaffold_files_and_api_names_exist():
    for module, api_names in MODULES.items():
        header = FW_MAIN / f"{module}.h"
        source = FW_MAIN / f"{module}.c"
        assert header.exists(), f"missing {header}"
        if module != "board_pins":
            assert source.exists(), f"missing {source}"
        text = header.read_text(encoding="utf-8")
        if source.exists():
            text += source.read_text(encoding="utf-8")
        for api in api_names:
            assert api in text


def test_cmake_includes_all_hardware_scaffold_sources():
    cmake = (FW_MAIN / "CMakeLists.txt").read_text(encoding="utf-8")
    for module in MODULES:
        if module == "board_pins":
            continue
        assert f'"{module}.c"' in cmake


def test_kconfig_has_disabled_hardware_switches_and_unassigned_pins():
    kconfig = (FW_MAIN / "Kconfig.projbuild").read_text(encoding="utf-8")
    for symbol in KCONFIG_SYMBOLS:
        assert f"config {symbol}" in kconfig

    for switch in [
        "STROKEGUARD_CAMERA_COPROCESSOR_ENABLE",
        "STROKEGUARD_NMO432_ENABLE",
        "STROKEGUARD_HW_DISPLAY_ENABLE",
        "STROKEGUARD_HW_AUDIO_OUT_ENABLE",
        "STROKEGUARD_HW_ALERT_ENABLE",
    ]:
        block = kconfig.split(f"config {switch}", 1)[1].split("\n\n", 1)[0]
        assert "default n" in block

    for pin in [
        "STROKEGUARD_PIN_ST7789_MOSI",
        "STROKEGUARD_PIN_MAX98357_DIN",
        "STROKEGUARD_PIN_ALERT_RGB",
    ]:
        block = kconfig.split(f"config {pin}", 1)[1].split("\n\n", 1)[0]
        assert "default -1" in block


def test_wiring_doc_marks_unconfirmed_wiring_and_medical_scope():
    doc = DOCS / "wiring.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    assert "待确认" in text
    assert "不新增镜端硬件" in text
    assert "Arm" in text
    assert "GC2145" in text
    assert "INMP441" in text
    assert "ST7789" in text
    assert "MAX98357A" in text
