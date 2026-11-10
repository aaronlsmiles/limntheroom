import numpy as np
import pytest
from scipy.ndimage import distance_transform_edt as edt

from seam.drawn import density, moment_align


def ring(shape, cy, cx, r, w=1.5):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    d = np.hypot(yy - cy, xx - cx)
    return np.abs(d - r) <= w


def chamfer(a, b):
    return 0.5 * (edt(~b)[a].mean() + edt(~a)[b].mean())


def test_scaled_translated_ring_aligns_back():
    ref = ring((200, 200), 100, 100, 40)
    src = ring((720, 1280), 400, 900, 80, w=3)       # twice the size, elsewhere, on the frame grid
    out = moment_align(src, ref)
    assert out.shape == ref.shape
    assert chamfer(out, ref) < 1.0
    assert chamfer(src[:200, :200] | ring((200, 200), 60, 60, 20), ref) > 5   # sanity: unaligned is far


def test_points_off_the_grid_are_dropped():
    ref = np.zeros((50, 50), bool)
    ref[20:30, 20:30] = True
    src = np.zeros((50, 50), bool)
    src[0:10, 0:10] = True
    out = moment_align(src, ref)
    assert out.any() and out.shape == (50, 50)


def test_empty_is_none():
    z = np.zeros((10, 10), bool)
    o = np.ones((10, 10), bool)
    assert moment_align(z, o) is None and moment_align(o, z) is None


def test_density():
    lines = np.zeros((10, 10), bool)
    lines[:, :5] = True
    mask = np.ones((10, 10), bool)
    assert density(lines, mask) == pytest.approx(0.5)
    assert density(lines, np.zeros_like(mask)) is None
