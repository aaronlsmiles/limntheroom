"""seam.cues.props: prop onset and settle from the prop's take-mask area over time."""
import numpy as np

from seam.cues import props


def _slide_in(n_before=10, n_move=10, n_still=20, area=900.0):
    areas, cents = [], []
    for _ in range(n_before):
        areas.append(0.0); cents.append(None)
    for i in range(n_move):                       # arrives from the right edge, growing as it enters
        areas.append(area * (i + 1) / n_move); cents.append((300.0 - 10 * i, 100.0))
    for _ in range(n_still):
        areas.append(area); cents.append((200.0, 100.0))
    return areas, cents


def test_onset_and_settle():
    areas, cents = _slide_in()
    (e,) = props.detect(areas, cents, fps=15, obj="pen", cue="pen")
    assert e["cue"] == "pen" and e["source"] == "detector:props"
    assert e["what"] == "the pen is set down"
    assert e["evidence"]["onset_frame"] == 10
    assert abs(e["evidence"]["settle_frame"] - 20) <= 1
    assert e["t"] == round(e["evidence"]["settle_frame"] / 15, 3)
    assert e["t_end"] is None


def test_never_settles():
    areas = [0.0] * 5 + [900.0] * 30
    cents = [None] * 5 + [(10.0 + 6 * i, 50.0) for i in range(30)]   # keeps sliding 6 px per frame
    assert props.detect(areas, cents, fps=15, obj="glass", cue="water") == []


def test_hand_occlusion_dip():
    areas, cents = _slide_in(n_still=30)
    areas[28], areas[29] = 500.0, 520.0           # a hand passes in front for two frames
    evs = props.detect(areas, cents, fps=15, obj="glass", cue="water")
    assert len(evs) == 1


def test_from_masks():
    m = np.zeros((3, 20, 30), bool)
    m[1, 2:6, 10:14] = True                       # 16 px, centroid (11.5, 3.5)
    m[2, 2:6, 10:15] = True
    areas, cents = props.areas_centroids(m)
    assert areas == [0.0, 16.0, 20.0]
    assert cents[0] is None and cents[1] == (11.5, 3.5)


def test_min_area_ignores_specks():
    areas = [0.0] * 5 + [12.0] * 30
    cents = [None] * 5 + [(50.0, 50.0)] * 30
    assert props.detect(areas, cents, fps=15, obj="pen", cue="pen", min_area=50) == []


def test_thresholds_are_named_constants():
    import inspect
    assert (props.MIN_AREA, props.ON_FRAMES, props.OFF_FRAMES, props.SETTLE_FRAMES, props.AREA_TOL,
            props.MOVE_PX) == (50, 3, 5, 5, 0.05, 3.0)
    p = inspect.signature(props.detect).parameters
    assert p["min_area"].default == props.MIN_AREA and p["settle_frames"].default == props.SETTLE_FRAMES
    assert p["on_frames"].default == props.ON_FRAMES and p["off_frames"].default == props.OFF_FRAMES
    assert p["area_tol"].default == props.AREA_TOL and p["move_px"].default == props.MOVE_PX


def test_settle_requires_min_area():
    # present at onset, then shrinks to a steady speck below min_area (the prop left; a speck stays)
    areas = [0.0] * 5 + [900.0] * 3 + [20.0] * 20
    cents = [None] * 5 + [(10.0 + 20 * i, 50.0) for i in range(3)] + [(100.0, 50.0)] * 20
    assert props.detect(areas, cents, fps=15, obj="pen", cue="pen") == []
