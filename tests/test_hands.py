from pathlib import Path

import numpy as np
import pytest

from seam import hands

MODEL = Path(__file__).resolve().parents[1] / "models/hand_landmarker.task"


def skeleton():
    rng = np.random.default_rng(0)
    return np.column_stack([rng.uniform(400, 700, 21), rng.uniform(200, 500, 21)])


def test_translated_skeleton_drift():
    k = skeleton()
    diag = np.hypot(*(k.max(0) - k.min(0)))
    assert hands.keypoint_drift(k, k + [3.0, 4.0]) == pytest.approx(5.0 / diag)
    assert hands.keypoint_drift(k, k) == 0.0


def test_none_and_shape_handling():
    k = skeleton()
    assert hands.keypoint_drift(None, k) is None and hands.keypoint_drift(k, None) is None
    with pytest.raises(ValueError):
        hands.keypoint_drift(k[:20], k[:20])


def test_drift_series_uses_valid_frames():
    k = skeleton()

    class Fake:
        def __init__(self, seq):
            self.seq = iter(seq)

        def detect(self, frame):
            return next(self.seq)

    take = Fake([k, None])               # detect is called on valid frames only (0 and 2)
    rend = Fake([k + [3, 4], k])
    s = hands.drift_series(take, rend, [0, 1, 2], [0, 1, 2], valid=[True, False, True])
    assert s[1] is None and s[2] is None and s[0] > 0


@pytest.mark.skipif(not MODEL.exists(), reason="hand_landmarker.task not fetched")
def test_tracker_returns_none_without_a_hand():
    tr = hands.HandTracker(MODEL)
    assert tr.detect(np.full((720, 1280, 3), 200, np.uint8)) is None
