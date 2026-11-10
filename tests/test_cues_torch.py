"""seam.cues.torch: bright-spot onset and aim from luminance, with glint rejection."""
import numpy as np

from seam.cues import torch as torch_cue

H, W = 180, 320


def _frames(n=40):
    rng = np.random.default_rng(1)
    return np.clip(90 + rng.normal(0, 2, (n, H, W, 1)), 0, 255).repeat(3, axis=3).astype(np.uint8)


def _beam(frames, start=10, length=20, x0=80, y0=90, dx=4, r=30, gain=120):
    yy, xx = np.mgrid[0:H, 0:W]
    for i in range(start, start + length):
        cx = x0 + dx * (i - start)
        d = np.hypot(xx - cx, yy - y0)
        glow = gain * np.clip(1 - (d / r) ** 2, 0, 1)
        frames[i] = np.clip(frames[i].astype(float) + glow[..., None], 0, 255).astype(np.uint8)
    return frames


def _glint(frames, start, length, x=260, y=40, s=4):
    frames[start:start + length, y:y + s, x:x + s] = 255
    return frames


def test_moving_beam_detected():
    (e,) = torch_cue.detect(_beam(_frames()), fps=15)
    assert e["cue"] == "light" and e["source"] == "detector:torch"
    assert e["t"] == round(10 / 15, 3) and e["t_end"] == 2.0
    ax, ay = e["evidence"]["aim"]
    assert abs(ax - 80) <= 3 and abs(ay - 90) <= 3
    assert e["evidence"]["travel_px"] > 50
    assert len(e["evidence"]["path"]) >= 3


def test_short_glint_rejected():
    assert torch_cue.detect(_glint(_frames(), 12, 2, s=3), fps=15) == []


def test_static_glint_rejected():
    # small and still for 25 frames: a metal edge catching the beam, not the beam
    assert torch_cue.detect(_glint(_frames(), 8, 25), fps=15) == []


def test_beam_with_glint():
    f = _glint(_beam(_frames()), 10, 20)
    (e,) = torch_cue.detect(f, fps=15)
    ax, ay = e["evidence"]["aim"]
    assert abs(ax - 80) <= 3 and abs(ay - 90) <= 3


def test_lands_on_home():
    homes = {"ink": (60, 70, 40, 40), "gold": (200, 70, 40, 40)}
    (e,) = torch_cue.detect(_beam(_frames()), fps=15, homes=homes)
    assert e["evidence"]["lands_on"] == "ink"
    assert "ink" in e["what"]


def test_no_light_no_event():
    assert torch_cue.detect(_frames(), fps=15) == []


def _shaky_page(n=40, seed=3):
    """A white page with dark ink strokes on a grey desk, shaken by up to 3 px per frame (handheld)."""
    rng = np.random.default_rng(seed)
    base = np.full((H + 20, W + 20), 90, np.uint8)
    base[30:170, 40:300] = 205
    for _ in range(25):
        x0, y0 = rng.integers(45, 290), rng.integers(35, 160)
        base[y0:y0 + 2, x0:x0 + rng.integers(10, 40)] = 30
        base[y0:y0 + rng.integers(10, 30), x0:x0 + 2] = 30
    out = []
    for i in range(n):
        dx, dy = (0, 0) if i < 5 else rng.integers(-3, 4, 2)
        out.append(base[10 + dy:10 + dy + H, 10 + dx:10 + dx + W])
    return np.stack(out)[..., None].repeat(3, axis=3).copy()


def test_handheld_shake_is_not_light():
    assert torch_cue.detect(_shaky_page(), fps=15) == []


def test_handheld_beam_detected():
    f = _beam(_shaky_page(), gain=80)
    (e,) = torch_cue.detect(f, fps=15)
    assert abs(e["t"] - 10 / 15) <= 1 / 15 + 1e-9


def test_thresholds_are_named_constants():
    t = torch_cue
    assert (t.BASELINE_FRAMES, t.DELTA, t.MIN_LUMA, t.MIN_SPOT_AREA, t.MIN_ON, t.GLINT_AREA, t.MIN_TRAVEL,
            t.DEAD_ZONE_PX, t.MAX_SHIFT_PX, t.LUMA_SIGMA, t.HIGHPASS_SIGMA) == (5, 40, 150, 4, 5, 150, 12.0, 0.25, 16, 2, 6)


def _reference_spots(frames):
    """The pre-streaming algorithm (every blurred luma frame held at once), kept to prove equality."""
    import cv2
    lum = [torch_cue._luma(f) for f in frames]
    base = np.median(np.stack(lum[:5]), axis=0).astype(np.float32)
    out = []
    for y in lum:
        b = torch_cue._register(base, y)
        mask = ((y - b > 40) & (y > 150)).astype(np.uint8)
        n, _, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if n <= 1:
            out.append(None)
            continue
        k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        area = int(stats[k, cv2.CC_STAT_AREA])
        out.append((float(cents[k][0]), float(cents[k][1]), area) if area >= 4 else None)
    return out


def test_streaming_matches_reference_on_long_clip():
    import tracemalloc
    n = 300
    f = _beam(_glint(_shaky_page(n=n), 50, 30), start=120, length=60, gain=80)
    ref = _reference_spots(f)
    gen = (fr for fr in f)                       # a generator: frames are never all held by the detector
    tracemalloc.start()
    got = torch_cue.spots(gen)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert got == ref
    luma_bytes = H * W * 4
    assert peak < 40 * luma_bytes, f"peak {peak} bytes: the detector is holding the whole clip"
    assert torch_cue.detect((fr for fr in f), fps=15) == torch_cue.detect(f, fps=15)


# --- call 132 (Aaron, 9 Nov): light counts only on the page, off every hand and prop track ----------------
# On the printed terrazzo, skin or glass over a dark chip is a luma rise too; on white paper only light is.

PAGE = (slice(30, 150), slice(60, 260))          # rows, cols of the page on the synthetic frame


def _page_scene(n=40):
    f = np.full((n, H, W), 90, np.uint8)
    f[:, PAGE[0], PAGE[1]] = 205
    return f[..., None].repeat(3, axis=3).copy()


def _track(n, rows, cols, start=0):
    m = np.zeros((n, H, W), bool)
    m[start:, rows, cols] = True
    return m


def _scene_masks(n=40, **extra):
    m = {"page": _track(n, *PAGE),
         "home_ink": _track(n, slice(75, 95), slice(95, 125)),
         "home_gold": _track(n, slice(75, 95), slice(150, 180)),
         "home_paper": _track(n, slice(75, 95), slice(205, 235))}
    m.update(extra)
    return m


def test_region_is_the_page_eroded_minus_tracks_dilated():
    hand = _track(3, slice(100, 120), slice(100, 120))
    r = list(torch_cue.region({"page": _track(3, *PAGE), "home_ink": _track(3, slice(75, 95), slice(95, 125)),
                               "hand": hand}, 3))
    assert len(r) == 3
    a = r[0]
    assert a[40, 70] and not a[33, 70] and not a[40, 63]      # page eroded by 4 px
    assert not a[110, 110] and not a[92, 110] and a[91, 110]  # hand dilated by 8 px
    assert a[85, 110]                                         # a home is not an obstacle: it is where light lands


def test_light_off_the_page_does_not_count():
    f = _beam(_page_scene(), x0=20, y0=90, dx=0, r=30)        # the pool sits on the desk left of the page
    assert torch_cue.detect(f, fps=15) != []                  # unmasked, it reads as light
    assert torch_cue.detect(f, fps=15, masks=_scene_masks()) == []


def test_a_bright_object_in_a_hand_track_is_not_light():
    f = _page_scene()
    hand = np.zeros((40, H, W), bool)
    for i in range(10, 40):                                   # a bright thing slides across the page
        x = 70 + 4 * (i - 10)
        f[i, 110:130, x:x + 20] = 250
        hand[i, 110:130, x:x + 20] = True
    assert torch_cue.detect(f, fps=15) != []
    assert torch_cue.detect(f, fps=15, masks=_scene_masks(hand=hand)) == []


def test_lands_on_by_the_lit_share_of_each_home():
    # a wide pool whose centre falls left of the ink home but which lights part of it
    f = _beam(_page_scene(), x0=72, y0=85, dx=0, r=45)
    (e,) = torch_cue.detect(f, fps=15, masks=_scene_masks())
    ax, _ = e["evidence"]["aim"]
    assert ax < 95                                            # the centre misses the home
    sh = e["evidence"]["lands_share"]
    assert sh["ink"] > torch_cue.LANDS_MIN_SHARE and sh["gold"] == 0 and sh["paper"] == 0
    assert e["evidence"]["lands_on"] == "ink" and "ink" in e["what"]


def test_lands_on_nothing_below_the_minimum_share():
    f = _beam(_page_scene(), x0=235, y0=135, dx=0, r=20)      # lit near the page's bottom right, far from homes
    (e,) = torch_cue.detect(f, fps=15, masks=_scene_masks())
    assert e["evidence"]["lands_on"] is None
    assert max(e["evidence"]["lands_share"].values()) < torch_cue.LANDS_MIN_SHARE


def test_region_constants_are_named():
    t = torch_cue
    assert (t.PAGE_ERODE_PX, t.TRACK_DILATE_PX, t.LANDS_FRAMES, t.LANDS_MIN_SHARE) == (4, 8, 8, 0.05)
