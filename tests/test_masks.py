"""seam.masks: mask store, the R0.3 quality rule, grid frames, 15 fps sampling (fast tests)."""
import json
import math

import av
import numpy as np
import pytest

from seam import masks


def _rand_masks(seed=0, shape=(5, 37, 53)):
    rng = np.random.default_rng(seed)
    return {"glass": rng.random(shape) > 0.5, "hand": rng.random(shape) > 0.8}


def test_roundtrip_bitpacked(tmp_path):
    m = _rand_masks()
    p = tmp_path / "t01.npz"
    masks.save_masks(p, m, take="t01", fps=15)
    meta, back = masks.load_masks(p)
    assert meta["schema"] == "p47-masks/1"
    assert meta["fps"] == 15 and meta["take"] == "t01"
    assert (meta["n_frames"], meta["height"], meta["width"]) == (5, 37, 53)
    assert meta["objects"] == ["glass", "hand"]
    for k in m:
        assert back[k].dtype == bool
        assert np.array_equal(back[k], m[k])


def test_store_is_packed(tmp_path):
    p = tmp_path / "t.npz"
    masks.save_masks(p, _rand_masks(), take="t", fps=15)
    with np.load(p) as z:
        a = z["obj:glass"]
        assert a.dtype == np.uint8
        assert a.shape == (5, math.ceil(37 * 53 / 8))
        assert json.loads(str(z["meta"]))["schema"] == "p47-masks/1"


def test_save_rejects_mismatched_shapes(tmp_path):
    m = {"a": np.zeros((3, 4, 4), bool), "b": np.zeros((3, 4, 5), bool)}
    with pytest.raises(ValueError):
        masks.save_masks(tmp_path / "x.npz", m, take="x", fps=15)


def test_digest_stable_and_sensitive():
    a = _rand_masks()
    b = {k: v.copy() for k, v in a.items()}
    assert masks.mask_digest(a) == masks.mask_digest(b)
    b["glass"][2, 10, 10] = ~b["glass"][2, 10, 10]
    assert masks.mask_digest(a) != masks.mask_digest(b)


def test_quality_rule():
    # 140 -> 220 is +57 %; 0 is empty; 50 follows an empty frame; 50 -> 75 is exactly +50 %; 75 -> 112 is +49 %
    assert masks.quality_ok([100, 140, 220, 0, 50, 75, 112]) == [True, True, False, False, False, True, True]


def test_quality_rule_drop():
    assert masks.quality_ok([100, 49]) == [True, False]
    assert masks.quality_ok([100, 50]) == [True, True]
    assert masks.quality_ok([0]) == [False]
    assert masks.quality_ok([]) == []


def test_quality_from_masks():
    stack = np.zeros((3, 10, 10), bool)
    stack[0, :4, :4] = True   # 16
    stack[1, :4, :5] = True   # 20 (+25 %)
    # frame 2 empty
    assert masks.quality_ok(stack) == [True, True, False]


def test_load_prompts_validates(tmp_path):
    good = {"take": "t01", "frame_rate": 15,
            "objects": {"glass": [{"frame": 30, "x": 812, "y": 401, "positive": True},
                                  {"frame": 30, "x": 700, "y": 300, "positive": False}]}}
    p = tmp_path / "t01.json"
    p.write_text(json.dumps(good))
    pr = masks.load_prompts(p, size=(720, 1280))
    assert pr == {"glass": [(30, 812.0, 401.0, True), (30, 700.0, 300.0, False)]}

    bad_x = json.loads(json.dumps(good))
    bad_x["objects"]["glass"][0]["x"] = 1280
    p.write_text(json.dumps(bad_x))
    with pytest.raises(ValueError):
        masks.load_prompts(p, size=(720, 1280))

    missing = json.loads(json.dumps(good))
    del missing["objects"]["glass"][0]["positive"]
    p.write_text(json.dumps(missing))
    with pytest.raises(ValueError):
        masks.load_prompts(p, size=(720, 1280))

    no_positive = {"take": "t01", "frame_rate": 15,
                   "objects": {"glass": [{"frame": 0, "x": 1, "y": 1, "positive": False}]}}
    p.write_text(json.dumps(no_positive))
    with pytest.raises(ValueError):
        masks.load_prompts(p, size=(720, 1280))


def test_grid_overlay():
    f = np.full((720, 1280, 3), 128, np.uint8)
    g = masks.grid_overlay(f, step=64)
    assert g.shape == f.shape and g.dtype == f.dtype
    assert (f == 128).all(), "input must not be modified"
    for x in (64, 640, 1216):
        assert (g[300:400, x] != 128).any(axis=1).all()
    # a pixel run between grid lines (y 320 and 384, x 64 and 128), away from labels, is untouched
    assert (g[330:375, 100] == 128).all()


def test_write_grid_frames(tmp_path):
    frames = np.full((4, 72, 128, 3), 200, np.uint8)
    paths = masks.write_grid_frames(frames, [0, 3], tmp_path, step=32)
    assert [p.name for p in paths] == ["grid_0000.png", "grid_0003.png"]
    assert all(p.exists() for p in paths)


def _write_index_video(path, n=60, fps=30, w=64, h=48):
    with av.open(str(path), "w") as c:
        s = c.add_stream("libx264", rate=fps)
        s.width, s.height, s.pix_fmt = w, h, "yuv444p"
        s.options = {"crf": "0", "g": "1"}
        for i in range(n):
            img = np.full((h, w, 3), (i * 4) % 256, np.uint8)
            for pkt in s.encode(av.VideoFrame.from_ndarray(img, format="rgb24")):
                c.mux(pkt)
        for pkt in s.encode():
            c.mux(pkt)


def test_sample_frames(tmp_path):
    p = tmp_path / "idx.mp4"
    _write_index_video(p)
    fr = masks.sample_frames(p, fps=15)
    assert fr.shape == (30, 48, 64, 3) and fr.dtype == np.uint8
    idx = np.round(fr[:, 24, 32, 0].astype(float) / 4).astype(int)
    assert np.all(np.abs(idx - np.arange(0, 60, 2)) <= 1)


def test_sample_frames_resize(tmp_path):
    p = tmp_path / "idx.mp4"
    _write_index_video(p, n=10)
    fr = masks.sample_frames(p, fps=15, size=(24, 32))
    assert fr.shape[1:] == (24, 32, 3)


def test_load_prompts_checks_frame_bound(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"take": "t", "frame_rate": 15,
                             "objects": {"glass": [{"frame": 150, "x": 1, "y": 1, "positive": True}]}}))
    assert masks.load_prompts(p, size=(720, 1280))["glass"][0][0] == 150          # no bound given
    with pytest.raises(ValueError, match="frame"):
        masks.load_prompts(p, size=(720, 1280), n_frames=150)


def test_track_missing_checkpoint_is_clear(tmp_path):
    with pytest.raises(FileNotFoundError, match="MODELS.md"):
        masks.track(np.zeros((2, 8, 8, 3), np.uint8), {"a": [(0, 1.0, 1.0, True)]}, ckpt=tmp_path / "none.pt")


def test_track_missing_sam2_is_clear(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "sam2.build_sam", None)
    with pytest.raises(ImportError, match="MODELS.md"):
        masks.track(np.zeros((2, 8, 8, 3), np.uint8), {"a": [(0, 1.0, 1.0, True)]})


# --- the quality rule before the creature leaves the page (render masks) -------------
def test_quality_rule_from_prompt_frame():
    # SAM propagates forward only: frames before the prompt are empty, the creature still at home
    assert masks.quality_ok([0, 0, 0, 100, 120], start=3) == [True] * 5
    assert masks.quality_ok([0, 0, 0, 100, 200], start=3) == [True, True, True, True, False]   # +100 %
    # the prompt frame is valid by definition, even if SAM gave it an empty mask
    assert masks.quality_ok([0, 0, 0, 0, 50], start=3) == [True, True, True, True, False]
    # without a start, the rule is unchanged
    assert masks.quality_ok([0, 0, 0, 100, 120]) == [False, False, False, False, True]
    assert masks.quality_ok([], start=0) == []
    with pytest.raises(ValueError):
        masks.quality_ok([1, 2], start=5)


def test_prompt_frame():
    pr = {"creature": [(12, 1.0, 1.0, True), (9, 2.0, 2.0, False), (10, 3.0, 3.0, True)]}
    assert masks.prompt_frame(pr, "creature") == 9


def test_track_cli_refuses_a_source_that_is_not_16_9(tmp_path):
    """Any 16:9 source is sampled onto the 1280x720 grid, as the blind picker and placer sample it; a source
    of another shape cannot map onto the grid, so the CLI refuses it."""
    p = tmp_path / "small.mp4"
    _write_index_video(p, n=4)                                  # 64x48: 4:3
    prompts = tmp_path / "p.json"
    prompts.write_text('{"take": "x", "objects": {"a": [{"frame": 0, "x": 1, "y": 1, "positive": true}]}}')
    with pytest.raises(SystemExit, match="16:9"):
        masks.main(["track", "--video", str(p), "--prompts", str(prompts), "--out", str(tmp_path / "m.npz")])


def test_analysis_frames_put_any_16_9_source_on_the_grid(tmp_path):
    p = tmp_path / "wide.mp4"
    _write_index_video(p, n=6, w=64, h=36)
    assert masks.video_size(p) == (36, 64)
    fr = masks.analysis_frames(p)
    assert fr.shape[1:] == (720, 1280, 3)
    assert np.array_equal(fr, masks.sample_frames(p, size=(720, 1280)))


def test_save_masks_records_extra_meta(tmp_path):
    m = {"a": np.zeros((2, 4, 6), bool)}
    masks.save_masks(tmp_path / "m.npz", m, take="x", extra={"source_size": [1080, 1920], "prompts_sha256": "p"})
    meta, _ = masks.load_masks(tmp_path / "m.npz")
    assert meta["source_size"] == [1080, 1920] and meta["prompts_sha256"] == "p"
