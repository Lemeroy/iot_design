from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "firmware_esp32" / "main"


def read(name: str) -> str:
    return (MAIN / name).read_text(encoding="utf-8")


def test_local_score_bus_is_wired_into_fusion():
    assert (MAIN / "score_bus.h").is_file()
    assert (MAIN / "score_bus.c").is_file()
    app = read("app_main.c")
    assert '#include "score_bus.h"' in app
    assert "sg_score_bus_snapshot" in app
    assert "sg_csi_get_score" in app
    assert "sg_fusion_compute" in app


def test_production_app_does_not_accept_pc_scores():
    app = read("app_main.c")
    cmake = read("CMakeLists.txt")
    assert "on_cdc_rx" not in app
    assert "sg_scores_parse" not in app
    assert '"scores_parser.c"' not in cmake


def test_no_runtime_fabricated_healthy_scores():
    bus = read("score_bus.c")
    assert "memset(out, 0xFF" not in bus
    assert "NAN" in bus
    assert "score = -1" in bus
