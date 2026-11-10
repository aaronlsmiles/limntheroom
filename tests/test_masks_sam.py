"""seam.masks.track: SAM 2.1 small on CPU must follow a synthetic moving square.

The short test (4 frames) runs by default, ~15 s on an idle M5. The two-object test runs only with LIMN_SLOW=1."""
import os

import numpy as np
import pytest

from seam import masks

pytestmark = pytest.mark.skipif(not masks.CKPT.exists(), reason="SAM 2.1 checkpoint missing: see models/MODELS.md")
slow = pytest.mark.skipif(not os.environ.get("LIMN_SLOW"), reason="slow SAM test: set LIMN_SLOW=1")

H, W, S = 240, 320, 40


def _scene(n, squares):
    """squares: list of (first_frame, x0, y0, dx, colour)."""
    frames = np.full((n, H, W, 3), 225, np.uint8)
    truth = []
    for first, x0, y0, dx, colour in squares:
        t = np.zeros((n, H, W), bool)
        for i in range(first, n):
            x = x0 + dx * (i - first)
            frames[i, y0:y0 + S, x:x + S] = colour
            t[i, y0:y0 + S, x:x + S] = True
        truth.append(t)
    return frames, truth


def _iou(a, b):
    u = np.logical_or(a, b).sum()
    return np.logical_and(a, b).sum() / u if u else 1.0


def test_tracks_moving_square():
    n = 4
    frames, (truth,) = _scene(n, [(0, 40, 100, 20, (30, 30, 40))])
    out = masks.track(frames, {"square": [(0, 60.0, 120.0, True)]})
    m = out["square"]
    assert m.shape == (n, H, W) and m.dtype == bool
    ious = [_iou(m[i], truth[i]) for i in range(n)]
    assert min(ious) >= 0.8, ious
    cx = [np.nonzero(m[i])[1].mean() for i in range(n)]
    assert all(b > a for a, b in zip(cx, cx[1:])), cx
    assert all(masks.quality_ok(m))


@slow
def test_two_objects_and_late_prompt():
    n = 8
    frames, (t1, t2) = _scene(n, [(0, 20, 20, 15, (30, 30, 40)), (3, 200, 150, -10, (180, 40, 40))])
    out = masks.track(frames, {"a": [(0, 40.0, 40.0, True)], "b": [(3, 220.0, 170.0, True)]})
    assert sorted(out) == ["a", "b"]
    assert not out["b"][:3].any(), "frames before the first prompt stay empty"
    assert min(_iou(out["a"][i], t1[i]) for i in range(n)) >= 0.8
    assert min(_iou(out["b"][i], t2[i]) for i in range(3, n)) >= 0.8
