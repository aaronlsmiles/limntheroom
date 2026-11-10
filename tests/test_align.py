import cv2
import numpy as np
import pytest

from seam import align
from seam.video import analysis_times, resample

W, H = 1280, 720


def room(seed=0):
    """A deterministic textured desk: rectangles, circles and strokes on mid-grey, mild noise."""
    rng = np.random.default_rng(seed)
    img = np.full((H, W, 3), 128, np.uint8)
    for _ in range(260):
        x, y = int(rng.integers(0, W)), int(rng.integers(0, H))
        c = tuple(int(v) for v in rng.integers(0, 256, 3))
        k = rng.integers(0, 3)
        if k == 0:
            cv2.rectangle(img, (x, y), (x + int(rng.integers(8, 60)), y + int(rng.integers(8, 60))), c, -1)
        elif k == 1:
            cv2.circle(img, (x, y), int(rng.integers(4, 30)), c, -1)
        else:
            cv2.line(img, (x, y), (x + int(rng.integers(-80, 80)), y + int(rng.integers(-80, 80))), c, 2)
    noise = rng.normal(0, 2, img.shape)
    return np.clip(img + noise, 0, 255).astype(np.uint8)


def page():
    m = np.zeros((H, W), bool)
    m[260:460, 520:760] = True
    return m


def affine(img, M):
    return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def sim(scale=1.0, tx=0.0, ty=0.0, cx=W / 2, cy=H / 2):
    M = cv2.getRotationMatrix2D((cx, cy), 0, scale)
    M[:, 2] += (tx, ty)
    return M


@pytest.fixture(scope="module")
def take():
    return room(0)


@pytest.fixture(scope="module")
def excl():
    return align.exclusion(page())


def test_exclusion_dilates_page_by_64(excl):
    assert excl[260 - 64, 600] and not excl[260 - 66, 600]
    assert excl[300, 520 - 64] and not excl[300, 520 - 66]


def test_shift_recovered(take, excl):
    # the render is the take moved by (+3.5, -2.0); the fit maps render -> take
    render = affine(take, sim(tx=3.5, ty=-2.0))
    fit = align.fit_similarity(render, take, excl)
    assert fit is not None
    assert fit.M[0, 2] == pytest.approx(-3.5, abs=0.1)
    assert fit.M[1, 2] == pytest.approx(2.0, abs=0.1)
    assert fit.scale == pytest.approx(1.0, abs=0.002)
    assert fit.residual < 1.0
    assert align.frame_ok(fit, rho=1.0)


def test_scale_outside_tolerance_fails(take, excl):
    fit = align.fit_similarity(affine(take, sim(scale=1.02)), take, excl)
    assert 1 / fit.scale == pytest.approx(1.02, abs=0.002)
    assert not align.frame_ok(fit, rho=1.0)
    ok = align.fit_similarity(affine(take, sim(scale=1.005)), take, excl)
    assert align.frame_ok(ok, rho=1.0)


def test_local_warp_residual_exceeds_rho(take, excl):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    mx = xx + 4 * np.sin(2 * np.pi * yy / 300)
    my = yy + 4 * np.sin(2 * np.pi * xx / 300)
    render = cv2.remap(take, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    fit = align.fit_similarity(render, take, excl)
    assert fit is None or (fit.residual > 1.0 and not align.frame_ok(fit, rho=1.0))


def test_fit_is_deterministic(take, excl):
    render = affine(take, sim(tx=1.3, ty=0.7))
    a, b = align.fit_similarity(render, take, excl), align.fit_similarity(render, take, excl)
    assert np.array_equal(a.M, b.M) and a.residual == b.residual


def test_blank_frame_fit_is_none(excl):
    blank = np.full((H, W, 3), 128, np.uint8)
    assert align.fit_similarity(blank, blank, excl) is None
    assert not align.frame_ok(None, rho=1.0)


def test_rho_from_round_trip(take, excl):
    rho, res, n_failed = align.round_trip_rho([take, take], [take, take], excl)
    assert rho == 1.0 and max(res) < 0.5 and n_failed == 0
    blank = np.full((H, W, 3), 128, np.uint8)
    rho, res, n_failed = align.round_trip_rho([take, blank], [take, blank], excl)
    assert n_failed == 1 and res[1] is None
    assert align.rho_from_residuals([0.6] * 10) == pytest.approx(1.2)
    assert align.rho_from_residuals([0.1, 0.2]) == 1.0


def _fit(res, scale=1.0):
    return align.Fit(M=np.eye(2, 3), scale=scale, residual=res, n_matches=100, n_inliers=100)


def test_gate_90_percent_rule():
    fits = [_fit(0.5)] * 9 + [_fit(5.0)]
    g = align.gate(fits, rho=1.0, lag=0)
    assert g["pass"] and g["frames_ok"] == pytest.approx(0.9) and g["ok"][-1] is False
    fits2 = [_fit(0.5)] * 8 + [_fit(5.0), None]
    assert not align.gate(fits2, rho=1.0, lag=0)["pass"]
    assert not align.gate([_fit(0.5)] * 10, rho=1.0, lag=2)["pass"]
    assert align.gate([_fit(0.5)] * 10, rho=1.0, lag=-1)["pass"]


def test_best_lag_recovers_shifts():
    rng = np.random.default_rng(5)
    e = rng.random(120)
    assert align.best_lag(e[10:100], e[7:97])[0] == 3       # render late: e_r(t+3) = e_t(t)
    assert align.best_lag(e[10:100], e[12:102])[0] == -2    # render early
    assert align.best_lag(e, e)[0] == 0
    assert not align.lag_ok(2) and align.lag_ok(-1) and align.lag_ok(0)


def test_best_lag_tie_prefers_small_then_negative():
    e = np.tile([0.0, 1.0], 30)             # period 2: lags -2, 0, 2 all correlate perfectly
    assert align.best_lag(e, e)[0] == 0
    f = np.tile([0.0, 1.0], 30)
    assert align.best_lag(f[1:], f[:-1])[0] == -1   # -1 and +1 tie: the negative one wins


def _pos(t):
    return 100 + 250 * t + 120 * np.sin(2 * np.pi * 0.9 * t)     # uneven speed, so energy varies


VMAX = 250 + 120 * 2 * np.pi * 0.9


def _moving_square(times):
    out = np.full((len(times), H, W, 3), 230, np.uint8)
    for i, t in enumerate(times):
        x = int(round(_pos(t)))
        out[i, 300:360, x:x + 60] = 20
    return out


def _square_x(frame):
    cols = np.where((frame[:, :, 0] < 128).any(axis=0))[0]
    return cols.min()


def test_frame_rate_conversion_by_timestamp():
    pts_take = np.arange(60) / 30          # 2 s at 30 fps
    pts_rend = np.arange(48) / 24          # 2 s at 24 fps
    take = _moving_square(pts_take)
    rend = _moving_square(pts_rend)
    t = analysis_times(min(pts_take[-1], pts_rend[-1]))
    tk, rd = resample(take, pts_take, t), resample(rend, pts_rend, t)
    dx = [abs(_square_x(a) - _square_x(b)) for a, b in zip(tk, rd)]
    assert max(dx) <= VMAX / 48 + 1          # at most half a 24 fps frame apart in time
    mask = np.ones((H, W), bool)
    masks = [mask] * len(t)
    lag, r = align.best_lag(align.motion_energy(tk, masks), align.motion_energy(rd, masks))
    assert lag == 0


def test_delayed_render_fails_lag_check():
    rng = np.random.default_rng(9)
    n = 40
    ys = 80 + np.cumsum(rng.integers(-15, 16, n))                          # jerky motion
    frames = np.full((n + 2, 180, 320, 3), 230, np.uint8)
    for i in range(n + 2):
        y = int(np.clip(ys[min(i, n - 1)], 20, 140)) if i < n else 80
        frames[i, y - 10:y + 10, 100:140] = 20
    take = frames[2:n]
    render = frames[0:n - 2]                 # render shows each state 2 analysis frames late
    masks = [np.ones((180, 320), bool)] * len(take)
    lag, _ = align.best_lag(align.motion_energy(take, masks), align.motion_energy(render, masks))
    assert lag == 2 and not align.lag_ok(lag)


def test_motion_energy_inside_mask_only():
    a = np.zeros((3, 10, 10, 3), np.uint8)
    a[1, 0:5] = 100                          # change outside the mask's half
    a[2, 5:] = 50
    mask = np.zeros((10, 10), bool)
    mask[5:] = True
    e = align.motion_energy(a, [mask] * 3)
    assert e.shape == (2,) and e[0] == 0 and e[1] == pytest.approx(50)


def test_warp_puts_render_on_take_grid(take, excl):
    render = affine(take, sim(tx=4.0, ty=3.0))
    fit = align.fit_similarity(render, take, excl)
    back = align.warp(render, fit.M)
    inner = (slice(40, H - 40), slice(40, W - 40))
    assert np.abs(back[inner].astype(int) - take[inner].astype(int)).mean() < 2.0
    m = np.zeros((H, W), bool)
    m[100:200, 100:200] = True
    wm = align.warp_mask(m, np.array([[1, 0, 5], [0, 1, 0]], float))
    assert wm.dtype == bool and wm[150, 105] and not wm[150, 104] and wm[150, 204] and not wm[150, 205]


def test_cover_marks_the_border_the_warp_fills():
    # the render shows the room 5 px right and 3 px down; warped back, the take's last 5 columns and
    # last 3 rows have no render pixel behind them (the warp replicates the render's edge there)
    M = np.float64([[1, 0, -5], [0, 1, -3]])                 # render -> take
    cov = align.cover(M)
    assert cov.shape == (H, W) and cov.dtype == bool
    assert not cov[:, W - 5:].any() and not cov[H - 3:, :].any()
    assert cov[:H - 3, :W - 5].all()
    assert align.cover(np.float64([[1, 0, 0], [0, 1, 0]])).all()      # the identity covers every pixel
    # sub-pixel: a pixel whose source lands past the last render pixel is uncovered (1278 -> 1279.5)
    c = align.cover(np.float64([[1, 0, -1.5], [0, 1, 0]]))
    assert c[:, W - 3].all() and not c[:, W - 2:].any()


def test_gate_fails_cleanly_when_rho_is_undefined():
    # every round-trip fit failed: rho is None, so no frame can pass and the render is not aligned
    g = align.gate([_fit(0.1)] * 10, rho=None, lag=0)
    assert g["pass"] is False and g["frames_ok"] == 0.0
    assert g["reason"] == "rho undefined: no round-trip fit"
    assert not align.frame_ok(_fit(0.1), rho=None)


def test_gate_reasons():
    assert align.gate([_fit(0.5)] * 10, rho=1.0, lag=0)["reason"] is None
    assert align.gate([_fit(0.5)] * 10, rho=1.0, lag=3)["reason"] == "lag check failed"
    assert align.gate([_fit(5.0)] * 10, rho=1.0, lag=0)["reason"] == "fewer than 90 % of frames pass"
    assert align.gate([_fit(5.0)] * 10, rho=1.0, lag=None)["reason"] == "lag check failed; fewer than 90 % of frames pass"


def test_gate_records_library_versions():
    v = align.gate([_fit(0.5)] * 10, rho=1.0, lag=0)["versions"]
    assert set(v) == {"opencv-python", "numpy", "av"} and all(v.values())


# --- the lag check: energy over the frames with a hand or prop mask (call 126, ruling 1) -----

def _desk_with_page(n, phases, seed=3):
    """A static textured desk with a striped page whose stripes flutter by phases[i] px."""
    base = room(seed)
    out = np.repeat(base[None], n, axis=0)
    yy, xx = np.mgrid[260:460, 520:760]
    for i in range(n):
        out[i, 260:460, 520:760] = (128 + 100 * np.sin(2 * np.pi * (xx + phases[i]) / 23))[..., None].astype(np.uint8)
    return out


def test_breath_take_lag_not_applicable_alignment_rests_on_the_90_percent_rule():
    rng = np.random.default_rng(11)
    n = 40
    phases = np.cumsum(rng.normal(0, 3, n + 2))          # the page flutters, but there is no hand or prop
    frames = _desk_with_page(n + 2, phases)
    take, late = frames[2:], frames[:n]
    empty = [np.zeros((H, W), bool)] * n
    for masks in (None, empty):
        lc = align.lag_check(take, late, masks)          # even a late render: nothing is timed
        assert not lc["applicable"] and lc["source"] is None and lc["lag"] is None and lc["n_active"] == 0
        assert "no frame with a hand or prop mask" in lc["reason"]
        g = align.gate([_fit(0.3)] * n, rho=1.0, lag_check=lc)
        assert g["pass"] and g["lag_applicable"] is False and "not applicable" in g["lag_reason"]
        assert g["lag_n_active"] == 0
        # the 90 % rule alone decides: 36 of 40 frames pass, 35 do not
        assert align.gate([_fit(0.3)] * 36 + [_fit(5.0)] * 4, rho=1.0, lag_check=lc)["pass"]
        g = align.gate([_fit(0.3)] * 35 + [_fit(5.0)] * 5, rho=1.0, lag_check=lc)
        assert not g["pass"] and g["reason"] == "fewer than 90 % of frames pass"


def _hand_take(n=165, moves=range(60, 90), seed=21):
    """A full-length take (11 s at 15 fps) on small frames: a dark block, the hand, moves jerkily for
    2 s (frames 60-89) and is absent otherwise; its mask is the whole frame while it is in shot."""
    rng = np.random.default_rng(seed)
    hh, ww = 180, 320
    frames = np.full((n + 2, hh, ww, 3), 230, np.uint8)
    ys = rng.integers(30, 150, n + 2)                    # a jerky hand: a new height every frame
    inshot = np.zeros(n + 2, bool)
    for i in range(n + 2):
        if (i - 2) in moves:
            y = int(ys[i])
            frames[i, y - 8:y + 8, 100:124] = 20
            inshot[i] = True
    hand = [np.ones((hh, ww), bool) if v else np.zeros((hh, ww), bool) for v in inshot[2:]]
    return frames, hand


def test_hand_moving_2_s_of_11_now_gets_a_lag():
    frames, hand = _hand_take()
    take, late = frames[2:], frames[:-2]                 # the render shows each state 2 frames late
    e = align.motion_energy(take, hand)
    assert e.mean() < align.ENERGY_FLOOR                 # over the whole take it sat under the floor (LOG 3 Nov)
    lc = align.lag_check(take, take.copy(), hand)
    assert lc["applicable"] and lc["source"] == "hands_props" and lc["lag"] == 0
    assert lc["n_active"] == 30 and lc["energy_mean"] >= align.ENERGY_FLOOR
    assert align.gate([_fit(0.3)] * len(take), rho=1.0, lag_check=lc)["pass"]
    bad = align.lag_check(take, late, hand)
    assert bad["applicable"] and bad["lag"] == 2
    g = align.gate([_fit(0.3)] * len(take), rho=1.0, lag_check=bad)
    assert not g["pass"] and g["reason"] == "lag check failed"


def test_static_take_lag_not_applicable_gate_rests_on_space_and_duration():
    frames = np.repeat(room(4)[None], 30, axis=0)
    hands = [page()] * 30                                # a hand mask in every frame, but nothing moves
    lc = align.lag_check(frames, frames, hands)
    assert not lc["applicable"] and lc["lag"] is None and lc["source"] == "hands_props"
    assert "floor" in lc["reason"] and lc["energy_mean"] < align.ENERGY_FLOOR
    g = align.gate([_fit(0.3)] * 30, rho=1.0, lag_check=lc)
    assert g["pass"] and g["lag_applicable"] is False and "not applicable" in g["lag_reason"]
    assert not align.gate([_fit(5.0)] * 30, rho=1.0, lag_check=lc)["pass"]          # spatial still counts
    short = align.gate([_fit(0.3)] * 30, rho=1.0, lag_check=lc, duration_ok=False)
    assert not short["pass"] and "duration" in short["reason"]


def test_duration_check():
    times = np.arange(31) / 15                           # 0..2 s
    assert align.duration_ok(np.arange(61) / 30, times)     # 0 .. 2.0 s
    assert not align.duration_ok(np.arange(40) / 30, times)


# --- whole-render runs: the gate record the pair writer warps with ---------------------------

def _tm(n, glass=True):
    pg = np.repeat(page()[None], n, axis=0)
    out = {"page": pg, "home_ink": np.zeros_like(pg)}
    if glass:
        out["glass"] = np.zeros_like(pg)
    return out


def test_run_gate_records_each_frames_transform(take):
    n = 3
    takes = np.repeat(take[None], n, axis=0)
    rend = np.stack([affine(take, sim(tx=2.5, ty=-1.5))] * n)
    g = align.run_gate(takes, rend, np.arange(n) / 15, _tm(n), rho=1.0)
    assert g["pass"] and g["ok"] == [True] * n and len(g["transforms"]) == n
    M = np.asarray(g["transforms"][0])
    assert M.shape == (2, 3) and abs(M[0, 2] + 2.5) < 0.3 and abs(M[1, 2] - 1.5) < 0.3     # render -> take
    assert g["residuals"][0] <= 1.0 and abs(g["scales"][0] - 1) < 0.01
    assert align.lag_masks(_tm(n, glass=False)) is None and align.lag_masks(_tm(n)).shape == (n, H, W)


def test_run_gate_on_a_short_render_fails_duration(take):
    n = 3
    takes = np.repeat(take[None], n, axis=0)
    g = align.run_gate(takes, takes[:2], np.arange(2) / 15, _tm(n), rho=1.0)
    assert not g["pass"] and g["transforms"][2] is None and "duration" in g["reason"]


def test_rho_record_from_the_round_trip(take):
    n = 2
    takes = np.repeat(take[None], n, axis=0)
    r = align.rho_record(takes, takes, _tm(n))
    assert r["schema"] == "p47-rho/1" and r["rho"] == 1.0 and r["n_failed"] == 0
    with pytest.raises(ValueError, match="page"):
        align.rho_record(takes, takes, {"home_ink": np.zeros((n, H, W), bool)})


# --- review finding 2 (call 135): a render from a trimmed input is gated against the same span of the take ----------------
def test_run_gate_on_a_trimmed_render_uses_its_span_of_the_take(take):
    n = 6
    takes = np.stack([affine(take, sim(tx=float(k))) for k in range(n)])     # every take frame distinct
    rend = takes[2:5].copy()                                                  # a render of the take's frames 2-4
    whole = align.run_gate(takes, rend, np.arange(3) / 15, _tm(n), rho=1.0)
    assert not whole["pass"] and "duration" in whole["reason"]               # against the whole take it is short
    g = align.run_gate(takes, rend, np.arange(3) / 15, _tm(n), rho=1.0, span=(2, 3))
    assert g["pass"] and g["ok"] == [True] * 3 and len(g["transforms"]) == 3
    assert g["span"] == {"start_frame": 2, "frames": 3}
    assert all(abs(np.asarray(M)[0, 2]) < 0.3 for M in g["transforms"])       # frame j onto take frame 2 + j


def test_run_gate_refuses_a_span_outside_the_take(take):
    takes = np.repeat(take[None], 4, axis=0)
    with pytest.raises(ValueError, match="span"):
        align.run_gate(takes, takes[:3], np.arange(3) / 15, _tm(4), rho=1.0, span=(2, 3))


def test_span_frames_from_the_requests_trim():
    assert align.span_frames(0, 10, 192) == (0, 150)              # the probe and the no-op: the first 10 s
    assert align.span_frames(1.6, 4, 192) == (24, 60)             # a draft's 4 s window
    with pytest.raises(ValueError, match="span"):
        align.span_frames(12, 4, 192)
