import numpy as np
import pytest

from seam import cells, controls, pairs, regions

H, W = 180, 320


def room_frames(n=20):
    f = np.full((n, H, W, 3), 230, np.uint8)
    f[:, :, 8::16] = 60                       # room lines: dark grey, two per 32 px cell
    return f


def grid_frames(n=20):
    """Mixed orientation without crossings: in every 32 px cell a vertical tick (x 6, y 2-14) and
    a horizontal tick (y 22, x 14-30), 30 line px. (A dense crossing grid is a poor fixture: its
    crossings keep a diagonally shifted patch's IoU near 0.42, just above κ/2.)"""
    f = np.full((n, H, W, 3), 230, np.uint8)
    for y0 in range(0, H, 32):
        for x0 in range(0, W, 32):
            f[:, y0 + 2:min(y0 + 15, H), x0 + 6] = 60
            if y0 + 22 < H:
                f[:, y0 + 22, x0 + 14:x0 + 31] = 60
    return f


def hatch_frames(n=3, x0=0, x1=W):
    """A uniform 45° hatch (1 px diagonals every 16 px) between columns x0 and x1."""
    f = np.full((n, H, W, 3), 230, np.uint8)
    yy, xx = np.mgrid[0:H, 0:W]
    on = ((xx + yy) % 16 == 0) & (xx >= x0) & (xx < x1)
    f[:, on] = 60
    return f


def creature_rgba(r=15):
    s = 2 * r + 5
    yy, xx = np.mgrid[0:s, 0:s]
    d = np.hypot(yy - s // 2, xx - s // 2)
    rgba = np.zeros((s, s, 4), np.uint8)
    rgba[..., :3] = 240                       # paper
    rgba[np.abs(d - r + 3) <= 1.5, :3] = 0    # creature ink: pure black
    rgba[d <= r, 3] = 255
    return rgba


def dark(frames):
    return [f[..., 0] < 128 for f in frames]


def leaky(r):
    """Room lines as they are; creature ink (pure black) spreads r px, like a large receptive field."""
    def ext(frames):
        return [(f[..., 0] < 128) | regions.dilate(f[..., 0] < 10, r) for f in frames]
    return ext


def null_maps(take_maps):
    # a codec that moves the lines by one pixel in one frame of twenty: D0 = [1, 0, 0, ...]
    return [np.roll(m, 1, axis=1) if i == 0 else m.copy() for i, m in enumerate(take_maps)]


def run_paste(extract):
    take = room_frames()
    pasted, masks = controls.paste(take, creature_rgba(), xy=(140, 70), window=range(len(take)))
    home = np.zeros((H, W), bool)
    tm = extract(take)
    return controls.paste_control(tm, extract(pasted), null_maps(tm), masks, home, model="aleph2")


def test_paste_composites_inside_window_only():
    take = room_frames(6)
    out, masks = controls.paste(take, creature_rgba(), xy=(140, 70), window=range(2, 4))
    assert np.array_equal(out[0], take[0]) and not masks[0].any()
    assert masks[2].sum() > 0 and (out[2][masks[2]] != take[2][masks[2]]).any()
    assert np.array_equal(out[2][~masks[2]], take[2][~masks[2]])


def test_paste_control_clean_extractor_picks_32():
    res = run_paste(dark)
    assert res["testable"] and res["m"] == 32
    assert res["per_m"][32]["threshold"] == pytest.approx(controls.p95([1.0] + [0.0] * 19))


def test_paste_control_leak_moves_m_up():
    res = run_paste(leaky(40))
    assert not res["per_m"][32]["pass"] and res["m"] == 48 and res["testable"]


def test_paste_control_big_leak_not_testable():
    res = run_paste(leaky(80))
    assert res["m"] is None and not res["testable"]


def test_shift_control_flags_redrawn():
    take = grid_frames()
    xy = controls.choose_shift_patch(dark(take), [np.ones((H, W), bool)] * len(take))
    assert xy is not None and xy[0] % 32 == 0 and xy[1] % 32 == 0
    shifted = controls.shift_patch(take, xy)
    R = [np.ones((H, W), bool)] * len(take)
    res = controls.shift_control(dark(take), dark(shifted), R, xy, kappa=0.8)
    assert res["pass"] and res["frac"] >= 0.9
    same = controls.shift_control(dark(take), dark(take), R, xy, kappa=0.8)
    assert not same["pass"] and same["frac"] == 0.0


def test_shift_patch_moves_content_by_three_diagonally():
    rng = np.random.default_rng(0)
    take = rng.integers(0, 256, size=(1, H, W, 3), dtype=np.uint8)
    assert controls.SHIFT == (3, 3)
    out = controls.shift_patch(take, (64, 64))
    assert np.array_equal(out[0][64 + 3:128, 64 + 3:128], take[0][64:128 - 3, 64:128 - 3])
    assert np.array_equal(out[0][:64], take[0][:64]) and np.array_equal(out[0][128:], take[0][128:])
    assert np.array_equal(out[0][:, :64], take[0][:, :64])


def test_shift_control_flags_horizontal_strokes_too():
    """A (3, 0) move would leave horizontal strokes kept; the diagonal move displaces them.
    (The chooser rejects such a one-orientation patch anyway; here the patch is placed by hand.)"""
    take = np.full((20, H, W, 3), 230, np.uint8)
    take[:, 8::16, :] = 60                     # horizontal room lines, two per cell
    R = [np.ones((H, W), bool)] * len(take)
    xy = (64, 64)
    res = controls.shift_control(dark(take), dark(controls.shift_patch(take, xy)), R, xy, kappa=0.8)
    assert res["pass"] and res["frac"] >= 0.9
    flat = controls.shift_patch(take, xy, dx=3, dy=0)
    assert not controls.shift_control(dark(take), dark(flat), R, xy, kappa=0.8)["pass"]


def test_choose_shift_patch_avoids_outside_R_and_sparse_cells():
    take = grid_frames(3)
    maps = dark(take)
    R = np.ones((H, W), bool)
    R[:, :160] = False                         # left half is creature
    xy = controls.choose_shift_patch(maps, [R] * 3)
    assert xy[0] >= 160
    blank = [np.zeros((H, W), bool)] * 3
    assert controls.choose_shift_patch(blank, [R] * 3) is None


def test_kappa_keep():
    xs = list(np.linspace(0.2, 1.0, 101))
    assert controls.kappa_keep(xs) == pytest.approx(np.percentile(xs, 1))
    assert controls.kappa_keep([]) is None


def test_d_series_and_p95():
    a = [np.eye(8, dtype=bool), np.zeros((8, 8), bool)]
    s = controls.d_series(a, [np.eye(8, dtype=bool)] * 2, [np.ones((8, 8), bool)] * 2)
    assert s == [0.0, None]
    assert controls.p95([None, None]) is None


def test_pairs_round_trip(tmp_path):
    n = 3
    take = np.zeros((n, 4, 6, 3), np.uint8)
    render = take + 1
    valid = np.array([True, False, True])
    R = np.ones((n, 4, 6), bool)
    t = np.arange(n) / 15
    p = pairs.write_pair(tmp_path / "p.npz", take=take, render=render, valid=valid, R=R, t=t,
                         homes={"left": np.zeros((4, 6), bool)}, meta={"render": "x"})
    d = pairs.read_pair(p)
    assert d["render"].dtype == np.uint8 and np.array_equal(d["render"], render)
    assert d["valid"].dtype == bool and d["R"].shape == (n, 4, 6)
    assert d["meta"] == {"render": "x"} and set(d["homes"]) == {"left"}
    assert d["creature"] is None and d["scan"] is None
    with pytest.raises(ValueError):
        pairs.write_pair(tmp_path / "bad.npz", take=take, render=render[:2], valid=valid, R=R, t=t)


def test_coherence_values():
    full = [np.ones((H, W), bool)]
    assert controls.coherence(dark(grid_frames(1)), (64, 64)) < 0.3
    assert controls.coherence(dark(room_frames(1)), (64, 64)) > 0.9        # vertical only
    assert controls.coherence(dark(hatch_frames(1)), (64, 64)) > 0.9       # 45° hatch
    assert controls.coherence([np.zeros((H, W), bool)], (64, 64)) is None
    assert controls.COHERENCE_MAX == 0.5 and full


def test_45_degree_hatch_patch_is_not_chosen():
    take = hatch_frames()
    R = [np.ones((H, W), bool)] * len(take)
    maps = dark(take)
    assert all(m[64:96, 64:96].sum() >= 20 for m in maps)       # enough lines: only orientation rejects it
    assert controls.choose_shift_patch(maps, R) is None
    assert controls.choose_shift_patch(dark(room_frames(3)), R) is None   # vertical only: rejected too


def test_chooser_skips_the_hatch_and_takes_the_mixed_patch():
    take = hatch_frames(x0=0, x1=160)
    take[:, :, 160:] = grid_frames(len(take))[:, :, 160:]
    R = [np.ones((H, W), bool)] * len(take)
    xy = controls.choose_shift_patch(dark(take), R)
    assert xy is not None and xy[0] >= 160
    res = controls.shift_control(dark(take), dark(controls.shift_patch(take, xy)), R, xy, kappa=0.8)
    assert res["pass"] and res["coherence"] < 0.5


def test_null_height_follows_the_render_model():
    assert controls.null_height("aleph2") == 1080            # keeps the input resolution
    for m in ("kling_4", "seedance2_5", "gemini_omni_flash_1.1"):
        assert controls.null_height(m) == 720
    with pytest.raises(ValueError):
        controls.null_height("some_other_model")
    assert run_paste(dark)["null_height"] == 1080


def test_paste_control_needs_twenty_scored_frames():
    take = room_frames(19)
    pasted, masks = controls.paste(take, creature_rgba(), xy=(140, 70), window=range(len(take)))
    tm = dark(take)
    res = controls.paste_control(tm, dark(pasted), null_maps(tm), masks, np.zeros((H, W), bool), model="kling_4")
    assert not res["testable"] and res["m"] is None
    assert res["reason"] == "fewer than 20 scored frames"
    assert all(v["n_scored"] == 19 and not v["pass"] for v in res["per_m"].values())
    assert run_paste(dark)["reason"] is None


def test_paste_control_values_equal_direct_frame_rule():
    take = room_frames()
    pasted, masks = controls.paste(take, creature_rgba(), xy=(140, 70), window=range(len(take)))
    home = np.zeros((H, W), bool)
    tm, pm = dark(take), dark(pasted)
    nm = null_maps(tm)
    res = controls.paste_control(tm, pm, nm, masks, home, model="aleph2")
    for m in controls.M_CHOICES:
        R = [regions.measured_region(k, home, m) for k in masks]
        D = controls.d_series(pm, tm, R)
        D0 = controls.d_series(nm, tm, R)
        thr = controls.p95(D0)
        assert res["per_m"][m]["threshold"] == thr
        assert res["per_m"][m]["frac"] == float(np.mean([d <= thr for d in D if d is not None]))


def test_shift_patch_bounds():
    take = room_frames(1)
    with pytest.raises(ValueError):
        controls.shift_patch(take, (0, 64))          # x - 3 < 0
    with pytest.raises(ValueError):
        controls.shift_patch(take, (W - 32, 64))     # runs off the right edge


def test_pairs_missing_keys_and_empty(tmp_path):
    with pytest.raises(ValueError):
        pairs.write_pair(tmp_path / "e.npz", take=np.zeros((0, 4, 6, 3), np.uint8),
                         render=np.zeros((0, 4, 6, 3), np.uint8), valid=np.zeros(0, bool),
                         R=np.zeros((0, 4, 6), bool), t=np.zeros(0))
    np.savez(tmp_path / "bad.npz", take=np.zeros((1, 4, 6, 3), np.uint8))
    with pytest.raises(ValueError, match="render.*R|missing"):
        pairs.read_pair(tmp_path / "bad.npz")


def test_pairs_writer_makes_its_folder(tmp_path):
    """Found by the rehearsal: the first pair of a run goes into a runs/pairs/ that does not exist yet."""
    f = np.zeros((1, 4, 6, 3), np.uint8)
    p = pairs.write_pair(tmp_path / "runs" / "pairs" / "p.npz", take=f, render=f, valid=np.ones(1, bool),
                         R=np.ones((1, 4, 6), bool), t=np.zeros(1))
    assert pairs.read_pair(p)["take"].shape == (1, 4, 6, 3)


# ---- call 133 (Aaron, 10 Nov): the room's share of cells that read a 3 px move ------------------------------------------------
def test_move_frames_moves_content_by_three_diagonally_and_marks_the_strip():
    take = np.zeros((2, H, W, 3), np.uint8)
    take[:, 50, 60] = 255
    take[:, 0, 100] = 9                                       # in the strip that has no source
    moved, cover = controls.move_frames(take)
    assert moved[0, 53, 63].tolist() == [255] * 3 and moved[0, 50, 60].tolist() == [0] * 3
    assert cover.shape == (H, W) and not cover[:3].any() and not cover[:, :3].any() and cover[3:, 3:].all()
    assert np.array_equal(moved[:, :3], take[:, :3]) and np.array_equal(moved[:, :, :3], take[:, :, :3])


def test_room_shift_share_counts_the_room_cells_by_verdict():
    take = dark(grid_frames(4))
    R = [np.ones((H, W), bool)] * 4
    same = controls.room_shift_share(take, take, R, np.ones((H, W), bool), kappa=0.8)
    assert same["kept"] == 1.0 and same["redrawn"] == 0.0 and same["n_room_cells"] > 0
    moved, cover = controls.move_frames(grid_frames(4))
    res = controls.room_shift_share(take, dark(moved), R, cover, kappa=0.8)
    assert res["redrawn"] + res["kept"] + res["none"] == pytest.approx(1.0)
    assert res["redrawn"] > 0.5 and res["kappa"] == 0.8 and len(res["per_frame_redrawn"]) == 4
    rows, cols = cells.grid_shape(H, W)
    assert res["n_room_cells"] <= 4 * (rows - 1) * (cols - 1)  # the strip's top row and left column of cells drop out
    half = np.zeros((H, W), bool)
    half[:, :W // 2] = True
    assert controls.room_shift_share(take, dark(moved), [half] * 4, cover, 0.8)["n_room_cells"] < res["n_room_cells"]
