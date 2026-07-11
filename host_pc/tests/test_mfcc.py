"""MFCC 纯 numpy 实现测试."""
import numpy as np

from stroke_host.perception.mfcc import (
    N_MFCC,
    SAMPLE_RATE,
    compute_mfcc,
    frame_features,
)


def test_mfcc_shape_and_finite():
    sr = SAMPLE_RATE
    t = np.linspace(0, 1.0, sr, endpoint=False)
    sig = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    mfcc = compute_mfcc(sig, sr)
    assert mfcc.shape[1] == N_MFCC
    assert mfcc.shape[0] > 50  # 1s / 10ms hop ~ 98
    assert np.isfinite(mfcc).all()


def test_mfcc_too_short():
    mfcc = compute_mfcc(np.zeros(10, dtype=np.float32), SAMPLE_RATE)
    assert mfcc.shape[0] == 0


def test_mfcc_wrong_sr_raises():
    import pytest
    with pytest.raises(ValueError):
        compute_mfcc(np.zeros(1000, dtype=np.float32), sr=8000)


def test_frame_features_silence():
    sig = np.zeros(SAMPLE_RATE, dtype=np.float32)
    f = frame_features(sig, SAMPLE_RATE)
    assert f["rms"] < 1e-3
    assert f["voiced_ratio"] == 0.0 or f["voiced_ratio"] < 0.5


def test_frame_features_tone():
    sr = SAMPLE_RATE
    t = np.linspace(0, 1.0, sr, endpoint=False)
    sig = (0.3 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    f = frame_features(sig, sr)
    assert f["rms"] > 0.1
    assert f["voiced_ratio"] > 0.5
