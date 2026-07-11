"""MFCC 特征提取 (纯 numpy 实现, 与固件端 M1b 计划算法一致).

参数 (与 Ember 端约定):
  sample_rate = 16000
  win_ms      = 25   (400 samples)
  hop_ms      = 10   (160 samples)
  n_fft       = 512
  n_mels      = 26
  n_mfcc      = 13
  preemph     = 0.97

依赖: numpy only (不引 librosa, 与嵌入式 C 版本可 bitmatch).
"""
from __future__ import annotations

import numpy as np

SAMPLE_RATE = 16000
WIN_MS = 25
HOP_MS = 10
N_FFT = 512
N_MELS = 26
N_MFCC = 13
PREEMPH = 0.97
FMIN = 20.0
FMAX = 8000.0


def _hz_to_mel(hz: np.ndarray) -> np.ndarray:
    return 2595.0 * np.log10(1.0 + hz / 700.0)


def _mel_to_hz(mel: np.ndarray) -> np.ndarray:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def _mel_filterbank(n_mels: int, n_fft: int, sr: int,
                    fmin: float, fmax: float) -> np.ndarray:
    """(n_mels, n_fft//2+1) 三角滤波器组."""
    mel_min, mel_max = _hz_to_mel(np.array([fmin, fmax]))
    mel_pts = np.linspace(mel_min, mel_max, n_mels + 2)
    hz_pts = _mel_to_hz(mel_pts)
    bin_pts = np.floor((n_fft + 1) * hz_pts / sr).astype(int)

    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for m in range(n_mels):
        l, c, r = bin_pts[m], bin_pts[m + 1], bin_pts[m + 2]
        if c == l:
            c = l + 1
        if r == c:
            r = c + 1
        for k in range(l, c):
            fb[m, k] = (k - l) / (c - l)
        for k in range(c, r):
            fb[m, k] = (r - k) / (r - c)
    return fb


def _dct2_matrix(n_out: int, n_in: int) -> np.ndarray:
    """DCT-II 矩阵 (orthonormal)."""
    n = np.arange(n_in)
    k = np.arange(n_out).reshape(-1, 1)
    m = np.cos(np.pi * (2 * n + 1) * k / (2 * n_in)).astype(np.float32)
    m *= np.sqrt(2.0 / n_in)
    m[0] *= 1.0 / np.sqrt(2.0)
    return m


# 预生成
_MEL_FB = _mel_filterbank(N_MELS, N_FFT, SAMPLE_RATE, FMIN, FMAX)
_DCT_M = _dct2_matrix(N_MFCC, N_MELS)


def compute_mfcc(samples: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """输入 float32 mono, 输出 (T, N_MFCC) float32."""
    if sr != SAMPLE_RATE:
        raise ValueError(f"expect sr={SAMPLE_RATE}, got {sr}")
    if samples.dtype != np.float32:
        samples = samples.astype(np.float32)

    # 预加重
    emph = np.empty_like(samples)
    emph[0] = samples[0]
    emph[1:] = samples[1:] - PREEMPH * samples[:-1]

    win_len = int(WIN_MS * sr / 1000)
    hop_len = int(HOP_MS * sr / 1000)
    if emph.shape[0] < win_len:
        return np.zeros((0, N_MFCC), dtype=np.float32)

    # 帧切分
    n_frames = 1 + (emph.shape[0] - win_len) // hop_len
    frames = np.lib.stride_tricks.as_strided(
        emph,
        shape=(n_frames, win_len),
        strides=(emph.strides[0] * hop_len, emph.strides[0]),
    ).copy()
    # 汉明窗
    frames *= np.hamming(win_len).astype(np.float32)

    # FFT -> 功率谱
    spec = np.fft.rfft(frames, n=N_FFT).astype(np.complex64)
    power = (spec.real ** 2 + spec.imag ** 2)

    # Mel + log
    mel_e = power @ _MEL_FB.T
    mel_e = np.maximum(mel_e, 1e-10)
    log_mel = np.log(mel_e).astype(np.float32)

    # DCT-II
    mfcc = log_mel @ _DCT_M.T
    return mfcc.astype(np.float32)


def frame_features(samples: np.ndarray, sr: int = SAMPLE_RATE) -> dict:
    """整段音频的启发式特征, 供 CNN 未训练时 fallback."""
    if samples.size == 0:
        return {"rms": 0.0, "zcr": 0.0, "hnr_db": 0.0,
                "voiced_ratio": 0.0, "duration": 0.0}

    x = samples.astype(np.float32)
    rms = float(np.sqrt(np.mean(x ** 2) + 1e-12))
    # 过零率
    zc = np.sum(np.abs(np.diff(np.sign(x)))) / 2.0
    zcr = float(zc / len(x))
    # 帧级能量 -> voiced_ratio (语音活动检测)
    win = int(0.02 * sr)
    if win <= 0 or len(x) < win:
        voiced_ratio = 0.0
    else:
        n_f = len(x) // win
        energies = (x[: n_f * win].reshape(n_f, win) ** 2).mean(axis=1)
        thr = max(1e-6, energies.mean() * 0.3)
        voiced_ratio = float((energies > thr).mean())
    # HNR (简易谐噪比估计, dB)
    if rms > 1e-4:
        hnr_db = float(20 * np.log10(rms / (np.std(x - x.mean()) + 1e-6) + 1e-6))
    else:
        hnr_db = -30.0

    return {
        "rms": round(rms, 5),
        "zcr": round(zcr, 5),
        "hnr_db": round(hnr_db, 2),
        "voiced_ratio": round(voiced_ratio, 3),
        "duration": round(len(x) / sr, 3),
    }
