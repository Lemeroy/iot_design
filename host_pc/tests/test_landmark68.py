"""FaceMesh 468 -> 68 点映射测试."""
import numpy as np

from stroke_host.perception.landmark68 import FACEMESH_68, mesh468_to_68


def test_mapping_length_is_68():
    assert len(FACEMESH_68) == 68


def test_mapping_indices_in_range():
    for i in FACEMESH_68:
        assert 0 <= i < 468


def test_mesh468_to_68_shape():
    lm = np.random.RandomState(0).randn(468, 3).astype(np.float32)
    out = mesh468_to_68(lm)
    assert out.shape == (68, 3)


def test_mesh468_to_68_values_match():
    lm = np.arange(468 * 3, dtype=np.float32).reshape(468, 3)
    out = mesh468_to_68(lm)
    for i, idx in enumerate(FACEMESH_68):
        assert np.array_equal(out[i], lm[idx])


def test_short_input_raises():
    import pytest
    with pytest.raises(ValueError):
        mesh468_to_68(np.zeros((100, 3), dtype=np.float32))
