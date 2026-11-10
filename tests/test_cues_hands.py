"""seam.cues.hands: hand enter and leave. Interval logic on synthetic presence; MediaPipe smoke test."""
import numpy as np
import pytest

from seam.cues import hands


def test_intervals_basic():
    pres = [0] * 5 + [1] * 10 + [0] * 10
    assert hands.presence_intervals(pres) == [(5, 15)]


def test_intervals_debounce():
    pres = [0] * 3 + [1] * 6 + [0] + [1] * 6 + [0] * 5   # a 1-frame dropout does not split
    assert hands.presence_intervals(pres, min_on=3, min_off=2) == [(3, 16)]
    blip = [0] * 5 + [1] * 2 + [0] * 5                     # below min_on: not a hand
    assert hands.presence_intervals(blip, min_on=3) == []
    two = [1] * 4 + [0] * 4 + [1] * 4
    assert hands.presence_intervals(two, min_on=3, min_off=2) == [(0, 4), (8, 12)]


def test_interval_open_at_end():
    pres = [0] * 4 + [1] * 8
    assert hands.presence_intervals(pres) == [(4, 12)]
    evs = hands.detect_from_presence(pres, fps=15)
    assert evs[0]["t_end"] is None and evs[0]["evidence"]["open_at_end"] is True


def test_detect_events():
    pres = [0] * 15 + [1] * 15 + [0] * 15
    (e,) = hands.detect_from_presence(pres, fps=15)
    assert e["cue"] == "hand" and e["source"] == "detector:hands"
    assert e["what"] == "a hand comes into view"
    assert e["t"] == 1.0 and e["t_end"] == 2.0
    assert e["evidence"] == {"enter_frame": 15, "leave_frame": 30, "frames_present": 15, "open_at_end": False}


@pytest.mark.skipif(not hands.MODEL.exists(), reason="hand_landmarker.task missing: see models/MODELS.md")
def test_mediapipe_no_hand_on_blank():
    frames = np.full((5, 360, 640, 3), 230, np.uint8)
    with hands.HandDetector() as det:
        pres = [det.present(f, i, fps=15) for i, f in enumerate(frames)]
    assert pres == [False] * 5
    assert hands.detect(frames, fps=15) == []


def test_thresholds_are_named_constants():
    import inspect
    assert (hands.MIN_ON, hands.MIN_OFF) == (3, 3)
    for fn in (hands.presence_intervals, hands.detect_from_presence, hands.detect):
        sig = inspect.signature(fn).parameters
        assert sig["min_on"].default is hands.MIN_ON and sig["min_off"].default is hands.MIN_OFF


def test_missing_model_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="MODELS.md"):
        hands.HandDetector(model=tmp_path / "missing.task")
