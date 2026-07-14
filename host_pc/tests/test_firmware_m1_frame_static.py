"""Static checks for the ESP32 M1 frame contract scaffold.

The real GC2145/INMP441 drivers cannot be physically validated until parts
arrive, but the firmware must still expose the final frame JSON builder and
wire it into the ESP-IDF app.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FW_MAIN = ROOT / "firmware_esp32" / "main"


def test_firmware_hardware_contract_uses_camera_coprocessor_and_nmo432():
    kconfig = (FW_MAIN / "Kconfig.projbuild").read_text(encoding="utf-8")
    pins = (FW_MAIN / "board_pins.h").read_text(encoding="utf-8")

    for token in (
        "STROKEGUARD_CAMERA_COPROCESSOR_ENABLE",
        "STROKEGUARD_CAMERA_I2C_SDA",
        "STROKEGUARD_CAMERA_I2C_SCL",
        "STROKEGUARD_CAMERA_I2C_ADDRESS",
        "STROKEGUARD_NMO432_ENABLE",
        "STROKEGUARD_NMO432_BCLK",
        "STROKEGUARD_NMO432_WS",
        "STROKEGUARD_NMO432_DIN",
    ):
        assert token in kconfig
    assert "SG_PIN_CAMERA_I2C_SDA" in pins
    assert "SG_PIN_NMO432_BCLK" in pins


def test_firmware_contains_sensor_frame_builder_files():
    assert (FW_MAIN / "sensor_frame.h").exists()
    assert (FW_MAIN / "sensor_frame.c").exists()


def test_firmware_sensor_frame_builder_uses_final_contract_fields():
    src = (FW_MAIN / "sensor_frame.c").read_text(encoding="utf-8")
    normalized = src.replace('\\"', '"')

    assert "sg_sensor_frame_build_json" in src
    assert '"type":"frame"' in normalized
    assert '"jpeg_b64"' in normalized
    assert '"mfcc"' in normalized
    assert '"csi_score"' in normalized


def test_firmware_cmake_and_app_main_wire_sensor_frame_source():
    cmake = (FW_MAIN / "CMakeLists.txt").read_text(encoding="utf-8")
    app = (FW_MAIN / "app_main.c").read_text(encoding="utf-8")

    assert '"sensor_frame.c"' in cmake
    assert '#include "sensor_frame.h"' in app
    assert "sg_sensor_frame_build_json" in app
    assert "SG_FRAME_TYPE_DATA" in app
