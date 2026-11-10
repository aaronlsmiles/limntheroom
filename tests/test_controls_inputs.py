"""seam/controls_inputs.py: the paste composite and the shift-control input, built from a real take
(here synthetic), the flat scan crop, the take masks and the cue sheet, written in the npz formats
lines_job.py reads. The lines job itself runs here with a trivial extractor (dark pixels)."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from seam import controls, controls_inputs as ci, lines_job, masks, pairs, regions, video

H, W, N = 180, 320, 40
ROOT = Path(__file__).resolve().parent.parent


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


def creature_rgba(r=15):
    s = 2 * r + 5
    yy, xx = np.mgrid[0:s, 0:s]
    d = np.hypot(yy - s // 2, xx - s // 2)
    rgba = np.zeros((s, s, 4), np.uint8)
    rgba[..., :3] = 240                       # paper
    rgba[np.abs(d - r + 3) <= 1.5, :3] = 0    # creature ink: pure black
    rgba[d <= r, 3] = 255
    return rgba


def rect(y0, y1, x0, x1):
    m = np.zeros((H, W), bool)
    m[y0:y1, x0:x1] = True
    return m


HOME = rect(40, 60, 100, 120)
TOUCHED = rect(60, 110, 200, 240)
PAGE = rect(10, 130, 20, 300)


def stack(m, n=N):
    return np.broadcast_to(m, (n, H, W)).copy()


SHEET = {"take": "t01", "fps": 15, "n_frames": N, "size": [W, H], "vlm_log": [], "events": [
    {"id": "e01", "t": 0.2, "t_end": 0.4, "cue": "hand", "what": "a hand sets the glass down", "target": None,
     "source": "detector:hands", "evidence": ""},
    {"id": "e02", "t": 0.4, "t_end": None, "cue": "water", "what": "the glass settles", "target": "ink",
     "source": "detector:props", "evidence": ""},
    {"id": "e03", "t": 1.2, "t_end": None, "cue": "water", "what": "ripples", "target": "ink",
     "source": "detector:props", "evidence": ""},
]}


# ---- the crop ----------------------------------------------------------------------------------------------
@pytest.fixture
def crops(tmp_path):
    d = tmp_path / "scan"
    d.mkdir()
    Image.fromarray(creature_rgba(15), "RGBA").save(d / "ink.png")
    Image.fromarray(creature_rgba(15)[..., :3], "RGB").save(d / "flat.png")           # no alpha
    Image.fromarray(np.zeros((20, 20, 4), np.uint8), "RGBA").save(d / "clear.png")     # nothing opaque
    (d / "crops.json").write_text(json.dumps({"crops": {"ink": {"file": "ink.png"}, "flat": {"file": "flat.png"},
                                                         "clear": {"file": "clear.png"}, "gone": {"file": "gone.png"}}}))
    return d / "crops.json"


def test_load_crop_reads_rgba(crops):
    rgba = ci.load_crop(crops, "ink")
    assert rgba.shape == (35, 35, 4) and rgba.dtype == np.uint8
    assert np.array_equal(rgba, creature_rgba(15))
    assert ci.alpha_mask(rgba).sum() == (creature_rgba(15)[..., 3] > 127).sum()


@pytest.mark.parametrize("name,match", [("flat", "alpha"), ("clear", "opaque"), ("gone", "gone.png"),
                                        ("nobody", "nobody")])
def test_load_crop_refuses(crops, name, match):
    with pytest.raises(ci.ControlInputError, match=match):
        ci.load_crop(crops, name)


def test_fit_scale_matches_the_homes_area_and_scaling_keeps_the_ink():
    rgba = creature_rgba(15)
    s = ci.fit_scale(rgba, HOME)
    assert s == pytest.approx(np.sqrt(HOME.sum() / ci.alpha_mask(rgba).sum()))
    small = ci.scale_rgba(rgba, s)
    assert ci.alpha_mask(small).sum() == pytest.approx(HOME.sum(), rel=0.08)
    assert small.shape[0] == pytest.approx(rgba.shape[0] * s, abs=1)
    # premultiplied resampling: opaque interior stays paper, ink stays dark, no dark fringe round the edge
    opaque = small[..., 3] == 255
    assert (small[opaque][:, 0] > 200).any() and (small[opaque][:, 0] < 40).any()
    assert ci.scale_rgba(rgba, 1.0) is not None and np.array_equal(ci.scale_rgba(rgba, 1.0), rgba)
    assert np.array_equal(ci.scale_rgba(rgba, s), ci.scale_rgba(rgba, s))
    with pytest.raises(ci.ControlInputError):
        ci.scale_rgba(rgba, 0)


# ---- the cue window -----------------------------------------------------------------------------------------
def test_cue_window_starts_at_the_first_event_that_fires_a_law():
    t, i0 = ci.cue_window(SHEET, "ink")
    assert (t, i0) == (0.4, 6)                                    # the hand context event (target None) fires nothing
    assert ci.cue_window(SHEET, "ink", event="e03") == (1.2, 18)
    assert ci.cue_window(SHEET, "ink", t=1.0) == (1.0, 15)
    assert ci.cue_window({**SHEET, "events": [{**SHEET["events"][1], "t": 0.41}]}, "ink")[1] == 7      # 6.15 -> 7


def test_cue_window_refuses():
    with pytest.raises(ci.ControlInputError, match="gold"):
        ci.cue_window(SHEET, "gold")
    with pytest.raises(ci.ControlInputError, match="e99"):
        ci.cue_window(SHEET, "ink", event="e99")
    with pytest.raises(ci.ControlInputError, match="both"):
        ci.cue_window(SHEET, "ink", event="e02", t=1.0)
    with pytest.raises(ci.ControlInputError, match="e01"):
        ci.cue_window(SHEET, "ink", event="e01")                  # a context event fires nothing


# ---- placement -------------------------------------------------------------------------------------------------
def test_placement_clears_the_touched_object_by_4_px_on_the_line_to_home():
    rgba = ci.scale_rgba(creature_rgba(15), ci.fit_scale(creature_rgba(15), HOME))
    xy, info = ci.place_at_object(rgba, TOUCHED, HOME)
    from scipy.ndimage import distance_transform_edt
    ys, xs = np.nonzero(ci.alpha_mask(rgba))
    d = distance_transform_edt(~TOUCHED)[ys + xy[1], xs + xy[0]]
    assert 4 <= d.min() < 5.5 and info["distance"] == pytest.approx(d.min())
    # the crop's centroid lies on the line from the touched object's centroid towards the home's
    c_t = np.array(np.nonzero(TOUCHED)).mean(axis=1)[::-1]
    c_h = np.array(np.nonzero(HOME)).mean(axis=1)[::-1]
    c_c = np.array([xs.mean() + xy[0], ys.mean() + xy[1]])
    u = (c_h - c_t) / np.linalg.norm(c_h - c_t)
    off = c_c - c_t
    assert abs(off[0] * u[1] - off[1] * u[0]) < 1.5 and off @ u > 0
    # deterministic, and the crop lies inside the frame
    assert ci.place_at_object(rgba, TOUCHED, HOME)[0] == xy
    assert xy[0] >= 0 and xy[1] >= 0 and xy[0] + rgba.shape[1] <= W and xy[1] + rgba.shape[0] <= H


def test_placement_refuses_without_a_touched_object_or_room():
    rgba = creature_rgba(15)
    with pytest.raises(ci.ControlInputError, match="touched"):
        ci.place_at_object(rgba, np.zeros((H, W), bool), HOME)
    with pytest.raises(ci.ControlInputError, match="home"):
        ci.place_at_object(rgba, TOUCHED, np.zeros((H, W), bool))
    corner = rect(0, 20, 0, 20)                                   # the line to home leaves the frame at once
    far_home = rect(0, 5, 0, 5)
    with pytest.raises(ci.ControlInputError, match="frame|room"):
        ci.place_at_object(rgba, corner, far_home)


def test_breath_placement_is_just_below_the_page():
    rgba = creature_rgba(15)
    xy = ci.place_below(rgba, HOME, PAGE)
    ys, xs = np.nonzero(ci.alpha_mask(rgba))
    assert xy[1] + ys.min() == 130 + 4                            # the crop's top mask row: page bottom + gap
    assert abs((xs.mean() + xy[0]) - 110) <= 1                    # centred on the home's x
    no_page = ci.place_below(rgba, HOME, None)
    assert no_page[1] + ys.min() == 60 + 4


# ---- the composite ---------------------------------------------------------------------------------------------
def entry(**kw):
    return {"crop": "ink", "touched_mask": "glass", "home_mask": "home_ink", **kw}


def test_build_paste_composites_through_the_cue_window(crops):
    take = room_frames(N)
    m = {"glass": stack(TOUCHED), "home_ink": stack(HOME), "page": stack(PAGE)}
    built = ci.build_paste(take, m, entry(), "ink", SHEET, ci.load_crop(crops, "ink"))
    i0 = built["i0"]
    assert i0 == 6 and built["window"] == (6, N)
    assert built["take"].shape == (N - 6, H, W, 3) and built["composite"].shape == built["take"].shape
    assert np.array_equal(built["take"], take[6:])
    assert built["masks"].shape == built["take"].shape[:3] and built["masks"].all(axis=(1, 2)).sum() == 0
    mk = built["masks"][0]
    assert mk.sum() > 0 and (built["composite"][0][mk] != take[6][mk]).any()
    far = ~regions.dilate(mk, 2)                                  # anti-aliased edge pixels (alpha <= 127) sit within 2 px
    assert np.array_equal(built["composite"][0][far], take[6][far])           # the room is untouched
    assert all(np.array_equal(built["masks"][k], mk) for k in range(len(mk) and len(built["masks"])))  # held still
    assert np.array_equal(built["home"], HOME)
    assert built["info"]["distance"] >= 4 and built["info"]["scale"] == pytest.approx(
        ci.fit_scale(ci.load_crop(crops, "ink"), HOME))


def test_build_paste_honours_an_explicit_scale_and_a_moving_home_is_voted_static(crops):
    take = room_frames(N)
    home = stack(HOME)
    home[3] = False                                               # a flicker in the home track
    home[4, :5] = True
    m = {"glass": stack(TOUCHED), "home_ink": home}
    built = ci.build_paste(take, m, entry(scale=1.0), "ink", SHEET, ci.load_crop(crops, "ink"))
    assert built["info"]["scale"] == 1.0 and built["rgba"].shape == (35, 35, 4)
    assert np.array_equal(built["home"], HOME)


def test_build_paste_for_the_breath_take_goes_below_the_page(crops):
    sheet = {**SHEET, "events": [{**SHEET["events"][1], "cue": "breath"}]}
    m = {"home_ink": stack(HOME), "page": stack(PAGE)}
    built = ci.build_paste(room_frames(N), m, {"crop": "ink", "touched_mask": None, "home_mask": "home_ink",
                                               "page_mask": "page"}, "ink", sheet, ci.load_crop(crops, "ink"))
    assert built["info"]["placement"] == "below_page"
    assert built["xy"][1] + np.nonzero(ci.alpha_mask(built["rgba"]))[0].min() == 134


def test_build_paste_names_a_missing_mask(crops):
    with pytest.raises(ci.ControlInputError, match="glass"):
        ci.build_paste(room_frames(N), {"home_ink": stack(HOME)}, entry(), "ink", SHEET, ci.load_crop(crops, "ink"))


# ---- the entry in capture/takes.json ----------------------------------------------------------------------------
def test_validate_paste_entry():
    ci.validate_paste_entry(entry())
    ci.validate_paste_entry(entry(scale=0.8, event="e02"))
    ci.validate_paste_entry({"crop": "ink", "touched_mask": None, "home_mask": "h", "page_mask": "p"})
    for bad, match in [({"crop": "ink"}, "home_mask"), (entry(scale=-1), "scale"), (entry(extra=1), "extra"),
                       (entry(event="e02", t=1.0), "event"), ({"crop": "ink", "touched_mask": None, "home_mask": "h"}, "page_mask")]:
        with pytest.raises(ci.ControlInputError, match=match):
            ci.validate_paste_entry(bad)


def test_every_rated_row_of_takes_json_has_a_valid_paste_entry():
    rows = json.loads((ROOT / "capture/takes.json").read_text())
    for r in rows:
        if r["rated"]:
            assert "paste" in r, (r["id"], r["target_material"])
            ci.validate_paste_entry(r["paste"])
            assert r["paste"]["crop"] == r["target_material"]
            assert (r["paste"]["touched_mask"] is None) == (r["touched_object"] is None)
        else:
            assert "paste" not in r
    assert ci.find_row(rows, "t01", "gold")["paste"]["home_mask"] == "home_gold"
    with pytest.raises(ci.ControlInputError):
        ci.find_row(rows, "t01", "diamond")


# ---- the codec nulls --------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    p = tmp_path_factory.mktemp("clip") / "render.mp4"
    video.write_video(p, room_frames(2 * N), 30)
    return p


def test_null_frames_are_the_take_re_encoded_at_each_height(clip, tmp_path):
    n = ci.null_frames(clip, (720, 1080), n_frames=N, size=(W, H))
    assert set(n) == {720, 1080} and n[720].shape == (N, H, W, 3) == n[1080].shape
    take, pts = video.read_video(clip, size=(W, H))
    take = video.resample(take, pts, video.analysis_times(pts[-1]))[:N]
    for h in (720, 1080):
        assert np.abs(n[h].astype(int) - take).mean() < 6
    again = ci.null_frames(clip, (720, 1080), n_frames=N, size=(W, H))
    assert np.array_equal(n[720], again[720]) and np.array_equal(n[1080], again[1080])


# ---- the npz files ----------------------------------------------------------------------------------------------
def test_paste_input_runs_through_the_lines_job_paste_control(crops, clip, tmp_path):
    take = room_frames(N)
    m = {"glass": stack(TOUCHED), "home_ink": stack(HOME)}
    built = ci.build_paste(take, m, entry(), "ink", SHEET, ci.load_crop(crops, "ink"))
    nulls = ci.null_frames(clip, (720, 1080), n_frames=N, size=(W, H))
    p = ci.write_paste_input(tmp_path / "t01-ink.paste.npz", built, {h: v[built["i0"]:] for h, v in nulls.items()},
                             meta={"render": "t01-ink"})
    with np.load(p) as z:
        assert {"take", "null_720", "null_1080", "rgba", "xy", "home", "meta"} <= set(z.files)
        assert z["take"].shape == z["null_720"].shape == (N - 6, H, W, 3) and z["xy"].shape == (2,)
        meta = json.loads(str(z["meta"]))
    assert meta["render"] == "t01-ink" and meta["window"] == {"t": 0.4, "i0": 6, "n": N - 6}
    assert meta["scale"] == pytest.approx(built["info"]["scale"])
    # the job's own reader accepts it, and the control passes on this clean synthetic scene
    job = SimpleNamespace(maps=lambda frames, cache=False: [f[..., 0] < 128 for f in frames], header=lambda: {})
    out = tmp_path / "res.json"
    lines_job.cmd_paste(SimpleNamespace(input=str(p), model="aleph2", out=str(out)), job)
    res = json.loads(out.read_text())
    assert res["testable"] and res["m"] == 32 and res["per_m"]["32"]["n_scored"] >= 20
    assert res["input_meta"]["render"] == "t01-ink" and res["input_meta"]["schema"] == ci.SCHEMA      # the result names its input


def test_paste_input_with_one_resolution_only(crops, tmp_path):
    built = ci.build_paste(room_frames(N), {"glass": stack(TOUCHED), "home_ink": stack(HOME)}, entry(), "ink", SHEET,
                           ci.load_crop(crops, "ink"))
    nulls = {1080: np.zeros_like(built["take"])}
    p = ci.write_paste_input(tmp_path / "a.npz", built, nulls)
    with np.load(p) as z:
        assert "null_1080" in z.files and "null_720" not in z.files
    with pytest.raises(ci.ControlInputError, match="shape"):
        ci.write_paste_input(tmp_path / "b.npz", built, {720: np.zeros((3, H, W, 3), np.uint8)})


def test_shift_region_is_the_homes_margin_on_every_frame():
    R = ci.shift_region(HOME, 32, 5)
    assert R.shape == (5, H, W) and R.dtype == bool
    assert np.array_equal(R[0], ~regions.dilate(HOME, 32)) and R.all(axis=0).sum() == R[0].sum()
    with pytest.raises(ci.ControlInputError, match="m"):
        ci.shift_region(HOME, 40, 5)


def test_shift_input_runs_through_the_lines_job_shift_control(tmp_path):
    take = grid_frames(20)
    p = ci.write_shift_input(tmp_path / "t01.shift.npz", take, ci.shift_region(rect(0, 4, 0, 4), 32, 20),
                             meta={"render": "t01-ink"})
    with np.load(p) as z:
        assert set(z.files) >= {"take", "R", "meta"} and z["R"].shape == (20, H, W)
    job = SimpleNamespace(maps=lambda frames, cache=False: [f[..., 0] < 128 for f in frames], header=lambda: {})
    out = tmp_path / "shift.json"
    lines_job.cmd_shift(SimpleNamespace(input=str(p), kappa=0.8, out=str(out)), job)
    res = json.loads(out.read_text())
    assert res["xy"] is not None and res["pass"] and res["frac"] >= 0.9
    assert res["input_meta"]["render"] == "t01-ink"


def test_shift_pair_is_the_take_and_its_shifted_copy_in_pairs_format(tmp_path):
    take = grid_frames(6)
    R = ci.shift_region(rect(0, 4, 0, 4), 32, 6)
    xy = (64, 64)
    p = ci.write_shift_pair(tmp_path / "s.pair.npz", take, R, xy, fps=15, meta={"render": "t01-ink"})
    P = pairs.read_pair(p)
    assert np.array_equal(P["take"], take) and np.array_equal(P["render"], controls.shift_patch(take, xy))
    assert P["valid"].all() and np.array_equal(P["R"], R) and P["t"] == pytest.approx(np.arange(6) / 15)
    assert P["meta"]["shift"] == {"xy": [64, 64], "dx": 3, "dy": 3, "size": 64} and P["meta"]["render"] == "t01-ink"
    with pytest.raises(ValueError):
        ci.write_shift_pair(tmp_path / "bad.npz", take, R, (1000, 1000))


# ---- files in, files out -----------------------------------------------------------------------------------------
@pytest.fixture
def tree(tmp_path, crops, clip):
    root = tmp_path / "repo"
    (root / "takes").mkdir(parents=True)
    (root / "takes/t01a.analysis.mp4").write_bytes(clip.read_bytes())
    (root / "takes/t01a.render.mp4").write_bytes(clip.read_bytes())
    (root / "cues").mkdir()
    (root / "cues/t01.json").write_text(json.dumps(SHEET))
    masks.save_masks(root / "masks_t01.npz", {"glass": stack(TOUCHED), "home_ink": stack(HOME), "page": stack(PAGE)},
                     take="t01")
    row = {"id": "t01", "cue": "glass", "target_material": "ink", "target_position": "left",
           "touched_object": "glass", "rated": True, "paste": entry()}
    (root / "takes.json").write_text(json.dumps([row]))
    return root


def test_paste_from_files_and_the_cli(tree, crops, tmp_path):
    out = tmp_path / "t01-ink.paste.npz"
    args = ["paste", "--take", "t01", "--material", "ink", "--take-id", "t01a", "--root", str(tree),
            "--takes", str(tree / "takes.json"), "--cues", str(tree / "cues/t01.json"),
            "--masks", str(tree / "masks_t01.npz"), "--crops", str(crops), "--size", f"{W}x{H}",
            "--heights", "720,1080", "--out", str(out)]
    assert ci.main(args) == 0
    with np.load(out) as z:
        meta = json.loads(str(z["meta"]))
        assert z["null_720"].shape[1:] == (H, W, 3) and z["take"].shape[0] == N - 6
    assert meta["take"] == "t01" and meta["material"] == "ink" and meta["take_id"] == "t01a"
    assert len(meta["sources"]["analysis"]) == 64 and len(meta["sources"]["render_input"]) == 64
    assert meta["heights"] == [720, 1080]
    # running it again gives the same bytes in the arrays
    out2 = tmp_path / "again.npz"
    assert ci.main(args[:-1] + [str(out2)]) == 0
    with np.load(out) as a, np.load(out2) as b:
        assert all(np.array_equal(a[k], b[k]) for k in a.files if k != "meta")


def test_shift_from_files_and_the_cli(tree, crops, tmp_path):
    video.write_video(tree / "takes/t01a.analysis.mp4", grid_frames(40), 30)
    out = tmp_path / "t01-ink.shift.npz"
    rc = ci.main(["shift", "--take", "t01", "--material", "ink", "--take-id", "t01a", "--root", str(tree),
                  "--takes", str(tree / "takes.json"), "--masks", str(tree / "masks_t01.npz"), "--m", "32",
                  "--size", f"{W}x{H}", "--out", str(out)])
    assert rc == 0
    with np.load(out) as z:
        assert z["take"].shape[1:] == (H, W, 3) and np.array_equal(z["R"][0], ~regions.dilate(HOME, 32))
        assert json.loads(str(z["meta"]))["m"] == 32


def test_cli_reads_m_from_a_paste_result_and_refuses_bad_input(tree, tmp_path, capsys):
    res = tmp_path / "paste.json"
    res.write_text(json.dumps({"m": None, "testable": False, "reason": "no margin passes",
                               "input_meta": {"take": "t01", "material": "ink"}}))
    rc = ci.main(["shift", "--take", "t01", "--material", "ink", "--take-id", "t01a", "--root", str(tree),
                  "--takes", str(tree / "takes.json"), "--masks", str(tree / "masks_t01.npz"),
                  "--paste-result", str(res), "--size", f"{W}x{H}", "--out", str(tmp_path / "x.npz")])
    assert rc == 1 and "not testable" in capsys.readouterr().err and not (tmp_path / "x.npz").exists()
    rc = ci.main(["paste", "--take", "t01", "--material", "gold", "--root", str(tree), "--takes", str(tree / "takes.json"),
                  "--out", str(tmp_path / "y.npz")])
    assert rc == 1 and "gold" in capsys.readouterr().err


# ---- review fixes ---------------------------------------------------------------------------------------------------------------
def test_a_palette_png_with_trns_is_a_crop_with_alpha(tmp_path):
    d = tmp_path / "scan"
    d.mkdir()
    rgba = creature_rgba(15)
    ys, xs = np.mgrid[0:35, 0:35]
    idx = np.where(rgba[..., 3] > 0, np.where(rgba[..., 0] < 100, 1, 2), 0).astype(np.uint8)
    pal = Image.fromarray(idx, "P")
    pal.putpalette([255, 0, 255, 0, 0, 0, 240, 240, 240] + [0] * (256 * 3 - 9))
    pal.save(d / "pal.png", transparency=0)                       # palette entry 0 is transparent (a tRNS chunk)
    assert Image.open(d / "pal.png").mode == "P" and "A" not in Image.open(d / "pal.png").getbands()
    (d / "crops.json").write_text(json.dumps({"crops": {"pal": {"file": "pal.png"}}}))
    got = ci.load_crop(d / "crops.json", "pal")
    assert got.shape == (35, 35, 4)
    assert np.array_equal(ci.alpha_mask(got), rgba[..., 3] > 127)
    Image.fromarray(idx, "P").save(d / "opaque.png")                # a palette PNG with no tRNS has no alpha
    (d / "crops.json").write_text(json.dumps({"crops": {"opaque": {"file": "opaque.png"}}}))
    with pytest.raises(ci.ControlInputError, match="alpha"):
        ci.load_crop(d / "crops.json", "opaque")


def _fake_job():
    return SimpleNamespace(maps=lambda frames, cache=False: [f[..., 0] < 128 for f in frames], header=lambda: {})


def _paste_result(tree, crops, clip, tmp_path, material="ink", take="t01"):
    """Build a paste input for the tree and run it through the lines job; returns the result path."""
    out = tmp_path / "paste.npz"
    args = ["paste", "--take", take, "--material", material, "--take-id", "t01a", "--root", str(tree),
            "--takes", str(tree / "takes.json"), "--cues", str(tree / "cues/t01.json"), "--masks", str(tree / "masks_t01.npz"),
            "--crops", str(crops), "--size", f"{W}x{H}", "--out", str(out)]
    assert ci.main(args) == 0
    res = tmp_path / "paste.json"
    lines_job.cmd_paste(SimpleNamespace(input=str(out), model="aleph2", out=str(res)), _fake_job())
    return res


def test_shift_checks_the_paste_results_take_and_material(tree, crops, clip, tmp_path, capsys):
    res = _paste_result(tree, crops, clip, tmp_path)
    base = ["shift", "--take", "t01", "--material", "ink", "--take-id", "t01a", "--root", str(tree), "--takes",
            str(tree / "takes.json"), "--masks", str(tree / "masks_t01.npz"), "--size", f"{W}x{H}"]
    assert ci.main([*base, "--paste-result", str(res), "--out", str(tmp_path / "ok.npz")]) == 0
    # the result of another material or take is refused
    doc = json.loads(res.read_text())
    for k, v in (("material", "gold"), ("take", "t09")):
        bad = json.loads(json.dumps(doc))
        bad["input_meta"][k] = v
        p = tmp_path / f"bad_{k}.json"
        p.write_text(json.dumps(bad))
        assert ci.main([*base, "--paste-result", str(p), "--out", str(tmp_path / f"{k}.npz")]) == 1
        assert k in capsys.readouterr().err and not (tmp_path / f"{k}.npz").exists()
    # a result that does not say which take it is for (an older job) is refused too
    anon = {k: v for k, v in doc.items() if k != "input_meta"}
    p = tmp_path / "anon.json"
    p.write_text(json.dumps(anon))
    assert ci.main([*base, "--paste-result", str(p), "--out", str(tmp_path / "anon.npz")]) == 1
    assert "input_meta" in capsys.readouterr().err


def test_shift_pair_subcommand_from_a_shift_result(tree, crops, clip, tmp_path, capsys):
    video.write_video(tree / "takes/t01a.analysis.mp4", grid_frames(40), 30)
    shift_in = tmp_path / "shift.npz"
    base = ["--take", "t01", "--material", "ink", "--take-id", "t01a", "--root", str(tree), "--takes",
            str(tree / "takes.json"), "--masks", str(tree / "masks_t01.npz"), "--size", f"{W}x{H}"]
    assert ci.main(["shift", *base, "--m", "32", "--out", str(shift_in)]) == 0
    sres = tmp_path / "shift.json"
    lines_job.cmd_shift(SimpleNamespace(input=str(shift_in), kappa=0.8, out=str(sres)), _fake_job())
    doc = json.loads(sres.read_text())
    assert doc["xy"] is not None
    out = tmp_path / "t01-ink.shift.pair.npz"
    assert ci.main(["shift-pair", *base, "--m", "32", "--shift-result", str(sres), "--out", str(out)]) == 0
    P = pairs.read_pair(out)
    assert P["meta"]["shift"]["xy"] == doc["xy"] and P["meta"]["m"] == 32 and P["meta"]["material"] == "ink"
    take = _analysis_take(tree)
    assert np.array_equal(P["render"], controls.shift_patch(take, tuple(doc["xy"]))) and np.array_equal(P["R"][0], ~regions.dilate(HOME, 32))
    # no patch found -> refuse; another material's result -> refuse; an m that disagrees with the shift input's -> refuse
    for edit, word in ((lambda d: d.update(xy=None), "patch"), (lambda d: d["input_meta"].update(material="gold"), "material"),
                       (lambda d: d["input_meta"].update(m=48), "m")):
        bad = json.loads(json.dumps(doc))
        edit(bad)
        p = tmp_path / f"b_{word}.json"
        p.write_text(json.dumps(bad))
        assert ci.main(["shift-pair", *base, "--m", "32", "--shift-result", str(p), "--out", str(tmp_path / f"{word}.npz")]) == 1
        assert word in capsys.readouterr().err
        assert not (tmp_path / f"{word}.npz").exists()


def _analysis_take(tree):
    return ci._analysis_frames(tree / "takes/t01a.analysis.mp4", (W, H))


# ---- the codec-null floors and κ_codec (§9) -----------------------------------------------------------------
def test_codec_null_is_zero_on_an_identical_null_and_floors_a_moved_one():
    take = [f[..., 0] < 128 for f in grid_frames(6)]
    homes = {"home_ink": HOME, "home_gold": rect(40, 60, 200, 220)}
    same = controls.codec_null(take, take, homes, 32, noop=True)
    assert same["m"] == 32 and same["n_frames"] == 6 and set(same["homes"]) == set(homes)
    assert same["homes"]["home_ink"]["median"] == 0.0 and same["homes"]["home_ink"]["n"] == 6
    assert same["kappa_codec"] == 1.0 and same["n_room_cells"] > 0 and same["noop_homes"] == sorted(homes)
    moved = [np.roll(t, 1, axis=1) for t in take]
    r = controls.codec_null(take, moved, homes, 32, noop=True)
    h = r["homes"]["home_ink"]
    assert 0 < h["median"] <= 1.0 and h["median"] <= h["p95"] <= 1.0
    assert 0 < r["kappa_codec"] < 1.0
    # D0 is the frame rule in ~dilate(home, m): equal to it frame by frame
    R = ~regions.dilate(HOME, 32)
    from seam.maskrule import frame_rule
    assert r["homes"]["home_ink"]["D0"] == [pytest.approx(frame_rule(b, a, R)) for a, b in zip(take, moved)]
    assert "kappa_codec" not in controls.codec_null(take, moved, homes, 48)
    with pytest.raises(ValueError, match="m"):
        controls.codec_null(take, moved, homes, 40)


def test_null_input_runs_through_the_lines_job_codec_null(tree, tmp_path, capsys):
    out = tmp_path / "t01.null.npz"
    rc = ci.main(["null", "--take", "t01", "--take-id", "t01a", "--root", str(tree), "--masks", str(tree / "masks_t01.npz"),
                  "--size", f"{W}x{H}", "--out", str(out)])
    assert rc == 0
    with np.load(out) as z:
        assert {"take", "homes", "null_720", "null_1080", "meta"} <= set(z.files)
        assert z["homes"].shape == (1, H, W) and np.array_equal(z["homes"][0], HOME)
        assert z["null_720"].shape == z["take"].shape
        meta = json.loads(str(z["meta"]))
    assert meta["homes"] == ["home_ink"] and meta["take_id"] == "t01a" and len(meta["sources"]["render_input"]) == 64
    res = tmp_path / "t01.null720.json"
    lines_job.cmd_codec_null(SimpleNamespace(input=str(out), height=720, m=32, noop=True, out=str(res)), _fake_job())
    r = json.loads(res.read_text())
    assert r["height"] == 720 and r["m"] == 32 and r["input_meta"]["take"] == "t01"
    assert r["homes"]["home_ink"]["n"] > 0 and r["kappa_codec"] is not None
    with pytest.raises(SystemExit, match="null_540"):
        lines_job.cmd_codec_null(SimpleNamespace(input=str(out), height=540, m=32, noop=False, out=str(res)), _fake_job())


# ---- call 133 (Aaron, 10 Nov) ----------------------------------------------------------------------------------------------------
# Ruling 1: SAM tracks forward from the blind placer's prompt frame, so the touched object's mask can be empty at the cue frame
# (t05's note, t06's hand). The crop goes against its first tracked frame at or after the cue; the window still starts at the cue.
def test_build_paste_places_against_the_first_tracked_frame_at_or_after_the_cue(crops):
    touched = np.zeros((N, H, W), bool)
    touched[9] = TOUCHED                          # first tracked at frame 9; the cue frame is 6
    touched[10:] = rect(70, 120, 210, 250)        # it moves afterwards
    built = ci.build_paste(room_frames(N), {"glass": touched, "home_ink": stack(HOME)}, entry(), "ink", SHEET,
                           ci.load_crop(crops, "ink"))
    assert built["i0"] == 6 and built["window"] == (6, N) and built["take"].shape[0] == N - 6
    assert built["info"]["cue_frame"] == 6 and built["info"]["placement_frame"] == 9
    want, _ = ci.place_at_object(built["rgba"], TOUCHED, HOME)
    assert built["xy"] == tuple(want)


def test_build_paste_places_at_the_cue_frame_when_it_is_tracked(crops):
    built = ci.build_paste(room_frames(N), {"glass": stack(TOUCHED), "home_ink": stack(HOME)}, entry(), "ink",
                           SHEET, ci.load_crop(crops, "ink"))
    assert built["info"]["cue_frame"] == built["info"]["placement_frame"] == 6


def test_build_paste_refuses_a_touched_object_not_tracked_from_the_cue_on(crops):
    touched = np.zeros((N, H, W), bool)
    touched[:6] = TOUCHED                         # tracked only before the cue frame
    with pytest.raises(ci.ControlInputError, match="not tracked at or after the cue frame 6"):
        ci.build_paste(room_frames(N), {"glass": touched, "home_ink": stack(HOME)}, entry(), "ink", SHEET,
                       ci.load_crop(crops, "ink"))


def test_breath_paste_records_the_cue_frame_and_no_placement_frame(crops):
    sheet = {**SHEET, "events": [{**SHEET["events"][1], "cue": "breath"}]}
    built = ci.build_paste(room_frames(N), {"home_ink": stack(HOME), "page": stack(PAGE)},
                           {"crop": "ink", "touched_mask": None, "home_mask": "home_ink", "page_mask": "page"},
                           "ink", sheet, ci.load_crop(crops, "ink"))
    assert built["info"]["cue_frame"] == 6 and built["info"]["placement_frame"] is None


# Ruling 3: the glass take's gold and paper renders have sheets of their own, cues/<take>-<material>.json.
def test_sheet_path_prefers_the_renders_own_sheet(tmp_path):
    (tmp_path / "cues").mkdir()
    (tmp_path / "cues/t01.json").write_text("{}")
    assert ci.sheet_path(tmp_path, "t01", "gold") == tmp_path / "cues/t01.json"
    (tmp_path / "cues/t01-gold.json").write_text("{}")
    assert ci.sheet_path(tmp_path, "t01", "gold") == tmp_path / "cues/t01-gold.json"
    assert ci.sheet_path(tmp_path, "t01", "ink") == tmp_path / "cues/t01.json"


def test_paste_cli_reads_the_renders_own_sheet_by_default(tree, crops, tmp_path):
    gold = {**SHEET, "events": [{**e, "target": "gold" if e["target"] else None} for e in SHEET["events"]]}
    (tree / "cues/t01-gold.json").write_text(json.dumps(gold))
    masks.save_masks(tree / "masks_t01.npz", {"glass": stack(TOUCHED), "home_ink": stack(HOME),
                                              "home_gold": stack(rect(40, 60, 200, 220)), "page": stack(PAGE)}, take="t01")
    rows = json.loads((tree / "takes.json").read_text())
    rows.append({**rows[0], "target_material": "gold", "target_position": "centre", "paste": entry(home_mask="home_gold")})
    (tree / "takes.json").write_text(json.dumps(rows))
    out = tmp_path / "t01-gold.paste.npz"
    rc = ci.main(["paste", "--take", "t01", "--material", "gold", "--take-id", "t01a", "--root", str(tree),
                  "--takes", str(tree / "takes.json"), "--masks", str(tree / "masks_t01.npz"), "--crops", str(crops),
                  "--size", f"{W}x{H}", "--heights", "720", "--out", str(out)])
    assert rc == 0
    with np.load(out) as z:
        meta = json.loads(str(z["meta"]))
    assert meta["material"] == "gold" and meta["window"]["i0"] == 6
    assert meta["placement"]["cue_frame"] == 6 and meta["placement"]["placement_frame"] == 6


# Ruling 2: alongside the registered shift control, the share of room cells that read the whole take moved by (3, 3) as redrawn.
def test_shift_room_runs_through_the_lines_job(tmp_path):
    p = ci.write_shift_input(tmp_path / "s.npz", grid_frames(6), ci.shift_region(rect(0, 4, 0, 4), 32, 6),
                             meta={"render": "t01-ink", "m": 32})
    out = tmp_path / "room.json"
    lines_job.cmd_shift_room(SimpleNamespace(input=str(p), kappa=0.8, out=str(out)), _fake_job())
    r = json.loads(out.read_text())
    assert r["kappa"] == 0.8 and r["move"] == [3, 3] and r["redrawn"] > 0.5 and r["n_room_cells"] > 0
    assert r["input_meta"]["render"] == "t01-ink"
    a = lines_job.build_parser().parse_args(["shift-room", "--input", "x.npz", "--kappa", "0.75", "--out", "y.json"])
    assert a.cmd == "shift-room" and a.kappa == 0.75
