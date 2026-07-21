"""语音 S 分测试 (启发式 backend)."""
import numpy as np

from stroke_host.perception.speech_cnn import SpeechScoreStabilizer, score_speech


def _tone(freq: float, dur: float, sr: int = 16000, amp: float = 0.3) -> np.ndarray:
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _speech_like(sr: int = 16000, dur: float = 1.5) -> np.ndarray:
    """粗略模拟浊音 + 辅音: 多个共振峰叠加 + 噪声调制."""
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    fund = 0.25 * np.sin(2 * np.pi * 180 * t)
    f1 = 0.15 * np.sin(2 * np.pi * 720 * t)
    f2 = 0.10 * np.sin(2 * np.pi * 1240 * t)
    env = 0.5 * (1 + np.sin(2 * np.pi * 3 * t))  # 3Hz 音节包络
    noise = 0.05 * np.random.RandomState(0).randn(len(t))
    return ((fund + f1 + f2) * env + noise).astype(np.float32)


def test_empty_audio_unavailable():
    r = score_speech(np.zeros(0, dtype=np.float32))
    assert not r.available
    assert "no_audio" in r.reasons


def test_missing_cnn_weights_reports_heuristic_fallback(tmp_path):
    r = score_speech(_speech_like(), weights_path=tmp_path / "missing.onnx")

    assert r.available
    assert r.raw["backend"] == "heuristic"
    assert r.raw["fallback_reason"] == "cnn_weights_missing"
    assert r.raw["cnn_weights"] == str(tmp_path / "missing.onnx")


def test_unintegrated_cnn_reports_heuristic_fallback(tmp_path):
    weights = tmp_path / "speech.onnx"
    weights.write_bytes(b"placeholder")

    r = score_speech(_speech_like(), weights_path=weights)

    assert r.available
    assert r.raw["backend"] == "heuristic"
    assert r.raw["fallback_reason"] == "cnn_not_integrated"
    assert r.raw["cnn_weights"] == str(weights)


def test_silence_unavailable():
    r = score_speech(np.zeros(16000, dtype=np.float32))
    assert not r.available


def test_pure_tone_gets_some_score():
    # 纯音 voiced_ratio 高, HNR 高, 但 mfcc_std 极低 -> 分数不会很高
    sig = _tone(300, 1.5)
    r = score_speech(sig)
    assert r.available
    assert 0 <= r.score <= 100
    assert r.raw["backend"] == "heuristic"


def test_speech_like_scores_higher_than_silence():
    speech = _speech_like()
    r_speech = score_speech(speech)
    assert r_speech.available
    assert r_speech.score > 30


def test_very_quiet_still_flagged_unavailable():
    r = score_speech(0.0001 * np.random.RandomState(0).randn(16000).astype(np.float32))
    # 极小振幅 -> rms < 5e-4 -> unavailable
    assert not r.available


def test_speech_stabilizer_retains_last_valid_score_for_five_minutes():
    stabilizer = SpeechScoreStabilizer(retention_seconds=300)
    assert stabilizer.update(72, now=100.0) == 72
    assert stabilizer.update(None, now=200.0) == 72
    assert stabilizer.update(None, now=399.0) == 72
    assert stabilizer.update(None, now=401.0) is None


def test_speech_stabilizer_smooths_valid_scores():
    stabilizer = SpeechScoreStabilizer(retention_seconds=300, smoothing=0.35)
    assert stabilizer.update(70, now=100.0) == 70
    assert stabilizer.update(20, now=101.0) == 52
