"""CSI 透传适配器测试."""
from stroke_host.perception.csi_score import score_csi


def test_none_unavailable():
    r = score_csi(None)
    assert not r.available
    assert "csi_unavailable" in r.reasons


def test_invalid_type():
    r = score_csi("not_a_number")
    assert not r.available


def test_out_of_range_negative():
    r = score_csi(-1)
    assert not r.available


def test_out_of_range_over():
    r = score_csi(101)
    assert not r.available


def test_normal_high():
    r = score_csi(85)
    assert r.available
    assert r.score == 85
    assert r.reasons == []


def test_warning_zone():
    r = score_csi(45)
    assert r.score == 45
    assert any("info" in x or "warning" in x for x in r.reasons)


def test_danger_zone():
    r = score_csi(19)
    assert r.score == 19
    assert any("danger" in x for x in r.reasons)


def test_float_coerced_to_int():
    r = score_csi(87.6)
    assert r.available
    assert r.score == 87


def test_csi_raw_marks_measured_source_by_default():
    r = score_csi(85)

    assert r.raw["source"] == "esp32_csi_monitor"
    assert r.raw["quality"] == "measured"
    assert r.raw["warn_threshold"] == 60
    assert r.raw["danger_threshold"] == 20


def test_csi_raw_marks_simulated_source():
    r = score_csi(76, source="synthetic_frame")

    assert r.raw["source"] == "synthetic_frame"
    assert r.raw["quality"] == "simulated"


def test_csi_unavailable_keeps_source_context():
    r = score_csi(None, source="pc_real")

    assert not r.available
    assert r.raw["source"] == "pc_real"
    assert r.raw["quality"] == "unavailable"
