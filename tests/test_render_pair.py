"""seam/render_pair.py: the render pair carries the custody the lines job and the assembler check, and is
written only from a full, committed chain on the picked video under a passing gate."""
import argparse
import json
from pathlib import Path

import numpy as np
import pytest

from blindkit import commit, run
from seam import align, blind, frame_pick, lines_job, masks, pairs, points, render_pair, video
from test_align import page, room

N, H, W = 6, 720, 1280
RENDER = "t01-ink"
SHIFT = (2.0, -1.0)


def rect(y0, y1, x0, x1):
    m = np.zeros((H, W), bool)
    m[y0:y1, x0:x1] = True
    return m


HOME = rect(300, 340, 560, 620)                         # inside the page (rows 260-460, cols 520-760)


def creature_at(i):
    return HOME if i < 3 else rect(380, 420, 640, 700)  # leaves its home at frame 3


def shifted(img):
    import cv2
    M = np.float32([[1, 0, SHIFT[0]], [0, 1, SHIFT[1]]])
    return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


class Chain:
    """A take and a render on disk, the take masks, ρ and the gate, and a committed blind custody."""

    def __init__(self, tmp, custody=True):
        tmp = Path(tmp)
        tmp.mkdir(parents=True, exist_ok=True)
        self.tmp = tmp
        base = room(0)
        take = np.repeat(base[None], N, axis=0)
        take[:, HOME] = 30
        rend = []
        for i in range(N):
            f = base.copy()
            f[creature_at(i)] = 30
            rend.append(shifted(f))
        self.take_video = tmp / "t01a.analysis.mp4"
        self.video = tmp / f"{RENDER}.mp4"
        video.write_video(self.take_video, take, 15)
        video.write_video(self.video, np.stack(rend), 15)
        self.take = masks.analysis_frames(self.take_video)
        self.rend = masks.analysis_frames(self.video)
        pg = np.repeat(page()[None], N, axis=0)
        self.tm = {"page": pg, "home_ink": np.repeat(HOME[None], N, axis=0), "home_gold": np.zeros_like(pg),
                   "home_paper": np.zeros_like(pg), "glass": np.zeros_like(pg)}
        self.take_masks = tmp / "t01a.npz"
        masks.save_masks(self.take_masks, self.tm, take="t01a")
        self.gate = self.write_gate()
        self.creature = np.stack([shifted(creature_at(i).astype(np.uint8)) > 0 if i >= 3 else np.zeros((H, W), bool)
                                  for i in range(N)])
        if custody:
            self.custody()

    def write_gate(self, name="gate.json", **override):
        rho = align.rho_record(self.take, self.take, self.tm)["rho"]
        g = align.run_gate(self.take, self.rend, align.stream_pts(self.video), self.tm, rho)
        g = {"schema": align.GATE_SCHEMA, "render": RENDER, **g, **override,
             "inputs": {"take_sha256": blind.sha256_path(self.take_video), "video_sha256": blind.sha256_path(self.video),
                        "take_masks_sha256": blind.sha256_path(self.take_masks), "rho_sha256": "r" * 64}}
        p = self.tmp / name
        p.write_text(json.dumps(g))
        return p

    def custody(self, frame=4):
        home = frame_pick.load_home(self.take_masks, RENDER)
        vsha = blind.sha256_path(self.video)
        st = frame_pick.build_folder(self.rend, render=RENDER, home=home, video_sha256=vsha, stride=2)
        run(frame_pick.record, st, self.tmp, json.dumps({"pick": frame // 2 + 1}), name="pick")
        kw = dict(render=RENDER, home=home, video_sha256=vsha)
        st = points.build_render_folder(self.rend, step="place", **kw)
        run(points.record, st, self.tmp, json.dumps({"x": 672.0, "y": 399.0}), name="place")
        p1 = Path(points.PROMPTS) / "render" / f"{RENDER}.p1.json"
        first = self.tmp / "first.npz"
        masks.save_masks(first, {"creature": self.creature}, take=RENDER,
                         extra={"prompts_sha256": blind.sha256_path(p1), "video_sha256": vsha})
        st = points.build_render_folder(self.rend, step="check", masks_path=first, **kw)
        run(points.record, st, self.tmp, '{"covers": true}', name="check")
        self.prompts = Path(points.PROMPTS) / "render" / f"{RENDER}.json"
        self.track = self.tmp / "track.npz"
        masks.save_masks(self.track, {"creature": self.creature}, take=RENDER,
                         extra={"prompts_sha256": blind.sha256_path(self.prompts), "video_sha256": vsha})
        points.record_track(RENDER, self.track)
        commit()

    def build(self, out="pair.npz", **kw):
        a = dict(render=RENDER, take_video=self.take_video, video=self.video, take_masks=self.take_masks,
                 track=self.track, prompts=self.prompts, gate=self.gate, m=32, take_frames=self.take,
                 render_frames=self.rend)
        a.update(kw)
        p = self.tmp / out
        render_pair.build_render_pair(p, **a)
        return p


def check(p, prompts):
    lines_job.check_custody(argparse.Namespace(pair=str(p), render=RENDER, prompts=str(prompts)))


@pytest.fixture
def chain(tmp_path):
    return Chain(tmp_path / "chain")


def test_a_full_committed_chain_writes_a_pair_the_lines_job_accepts(chain):
    p = chain.build()
    P = pairs.read_pair(p)
    m = P["meta"]
    assert m["render"] == RENDER and m["home"] == "home_ink" and m["prompt_frame"] == 4 and m["m"] == 32
    assert m["render_mask_digest"] == masks.mask_digest({"creature": chain.creature})
    assert m["render_mask_file_sha256"] == blind.sha256_path(chain.track)
    assert m["video_sha256"] == blind.sha256_path(chain.video) and m["gate"]["pass"] is True
    assert m["gate"]["sha256"] == blind.sha256_json(json.loads(chain.gate.read_text()))
    # warped onto the take: the render's creature lands back on the take's grid, about SHIFT away
    ys, xs = np.nonzero(P["creature"][5])
    assert abs(xs.min() - 640) <= 1 and abs(ys.min() - 380) <= 1
    assert np.abs(P["render"][0].astype(int) - P["take"][0].astype(int))[~align.exclusion(page())].mean() < 3
    assert list(P["valid"]) == [True] * N and P["R"].shape == (N, H, W)
    assert not P["R"][0][HOME].any() and sorted(P["homes"]) == ["home_gold", "home_ink", "home_paper"]
    # the render shows the room SHIFT = (2, -1) px off: warped back, the right 2 columns and the top row have
    # no render pixel behind them, so they are out of R(t) (call 126)
    cov = P["cover"]
    assert cov.shape == (N, H, W) and not cov[:, :, W - 2:].any() and not cov[:, 0, :].any()
    assert cov[:, 1:, :W - 2].all() and not (P["R"] & ~cov).any()
    check(p, chain.prompts)


def _speckle(seed=5):
    """A white desk with 4 % dark specks: enough line pixels in every cell, and no two cells alike."""
    rng = np.random.default_rng(seed)
    img = np.full((H, W, 3), 235, np.uint8)
    img[rng.random((H, W)) < 0.04] = 20
    return img


def test_uncovered_border_scores_no_cell_and_does_not_drag_kappa(tmp_path):
    """A no-op-like render: the room unchanged, framed 40 px to the right. Warped back, every covered pixel is
    the take's; the border strip the warp fills is uncovered, scores no cell, and κ_render_p1 is 1, not ~0."""
    import cv2
    take = _speckle()
    rend = cv2.warpAffine(take, np.float64([[1, 0, 40], [0, 1, 0]]), (W, H), flags=cv2.INTER_NEAREST,
                          borderMode=cv2.BORDER_REPLICATE)
    M = np.float64([[1, 0, -40], [0, 1, 0]])              # render -> take, as the gate fits it
    warped, _, cov = render_pair._warp_all(rend[None], np.zeros((1, H, W), bool), [M.tolist()], (W, H))
    cov = cov[0]
    assert not cov[:, W - 40:].any() and np.array_equal(warped[0][cov], take[cov])

    def extract(frames):
        return [np.asarray(f)[..., 0] < 128 for f in frames]

    def run(name, R, cover):
        pp = pairs.write_pair(tmp_path / f"{name}.npz", take=take[None], render=warped, valid=np.ones(1, bool),
                              R=R[None], t=np.zeros(1), cover=None if cover is None else cover[None])
        return lines_job.measure(pp, kappa=0.5, extract=extract, chamfer=None, seam_path=tmp_path / f"{name}.bin")

    old = run("old", np.ones((H, W), bool), None)        # before call 126: the strip is in R
    assert old["kappa_render_p1"] < 0.25 and old["cell_counts"][0]["redrawn"] > 0
    new = run("new", cov, cov)
    assert new["kappa_render_p1"] == 1.0 and new["cell_counts"][0]["redrawn"] == 0
    assert new["cell_counts"][0]["creature"] == 0
    from seam import cells
    rows, cols = cells.grid_shape()
    codes = cells.unpack((tmp_path / "new.bin").read_bytes(), rows, cols)[0]
    touched = cells.cell_sums(~cov) > 0                   # every cell with an uncovered pixel
    assert touched[:, -2:].all() and (codes[touched] == cells.NONE).all()
    with pytest.raises(ValueError, match="did not cover"):
        pairs.write_pair(tmp_path / "bad.npz", take=take[None], render=warped, valid=np.ones(1, bool),
                         R=np.ones((1, H, W), bool), t=np.zeros(1), cover=cov[None])


def test_the_digests_come_from_the_track_file_not_the_caller(chain):
    """The writer has no digest argument: the only way in is the track file, and it must be the logged one."""
    import inspect
    params = inspect.signature(render_pair.build_render_pair).parameters
    assert not {"render_mask_digest", "digest", "meta"} & set(params)
    other = chain.tmp / "other.npz"
    c2 = chain.creature.copy()
    c2[5, 0, 0] = True
    masks.save_masks(other, {"creature": c2}, take=RENDER,
                     extra={"prompts_sha256": blind.sha256_path(chain.prompts), "video_sha256": blind.sha256_path(chain.video)})
    with pytest.raises(render_pair.PairError, match="logged final track"):
        chain.build(track=other)


def test_a_missing_pick_writes_no_pair(tmp_path):
    c = Chain(tmp_path / "nochain", custody=False)
    c.prompts, c.track = tmp_path / "p.json", tmp_path / "t.npz"
    with pytest.raises(blind.BlindError, match="no pick"):
        c.build()


def test_an_uncommitted_ledger_writes_no_pair(chain):
    lp = points._log_path("render", RENDER)
    lp.write_text(lp.read_text() + " ")
    with pytest.raises(render_pair.PairError, match="not committed|changes"):
        chain.build()


def test_the_wrong_video_writes_no_pair(chain):
    other = chain.tmp / "other.mp4"
    video.write_video(other, chain.rend[::-1], 15)
    with pytest.raises(blind.BlindError, match="video"):
        chain.build(video=other)


def test_a_failed_gate_writes_no_pair(chain):
    ok = [False] + [True] * (N - 1)               # 5/6 < 90 %: consistent, failed
    bad = chain.write_gate("bad.json", ok=ok, frames_ok=float(np.mean(ok)), **{"pass": False},
                           reason="fewer than 90 % of frames pass")
    with pytest.raises(render_pair.PairError, match="failed the alignment gate"):
        chain.build(gate=bad)
    lied = chain.write_gate("lied.json", ok=ok, frames_ok=float(np.mean(ok)))     # pass: true over a failing ok list
    with pytest.raises(ValueError, match="pass"):
        chain.build(gate=lied)


def test_a_gate_on_other_inputs_writes_no_pair(chain):
    g = json.loads(chain.gate.read_text())
    g["inputs"]["take_masks_sha256"] = "0" * 64
    p = chain.tmp / "elsewhere.json"
    p.write_text(json.dumps(g))
    with pytest.raises(render_pair.PairError, match="other inputs"):
        chain.build(gate=p)


def test_a_pair_edited_after_writing_is_refused(chain):
    p = chain.build()
    P = pairs.read_pair(p)
    c = P["creature"].copy()
    c[5, 0, 0] = True
    q = pairs.write_pair(chain.tmp / "edited.npz", take=P["take"], render=P["render"], valid=P["valid"], R=P["R"],
                         t=P["t"], creature=c, homes=P["homes"], meta=P["meta"])
    with pytest.raises(SystemExit, match="writer recorded"):
        check(q, chain.prompts)
    for k in ("gate", "video_sha256", "prompts_sha256"):
        q = pairs.write_pair(chain.tmp / f"no-{k}.npz", take=P["take"], render=P["render"], valid=P["valid"], R=P["R"],
                             t=P["t"], creature=P["creature"], homes=P["homes"],
                             meta={x: v for x, v in P["meta"].items() if x != k})
        with pytest.raises(SystemExit, match="refuse"):
            check(q, chain.prompts)


def test_the_null_pair_holds_the_same_take(chain, tmp_path):
    p = render_pair.build_null_pair(tmp_path / "null.npz", take_video=chain.take_video, render_input=chain.take_video,
                                    height=720, take_frames=chain.take)
    N_ = pairs.read_pair(tmp_path / "null.npz")
    assert p["height"] == 720 and np.array_equal(N_["take"], chain.take) and N_["valid"].all()


# --- review finding 2 (call 135): the no-op pair, and the null on the same span ------------------------------------------
def test_the_noop_pair_measures_the_room_outside_every_home_where_the_warp_reached(chain, tmp_path):
    out = tmp_path / "noop.npz"
    gate = chain.write_gate("noop-gate.json", render=lines_job.NOOP_ID)
    meta = render_pair.build_noop_pair(out, take_video=chain.take_video, video=chain.video,
                                       take_masks=chain.take_masks, gate=gate, m=32,
                                       take_frames=chain.take, render_frames=chain.rend)
    p = pairs.read_pair(out)
    assert meta["render"] == lines_job.NOOP_ID and meta["m"] == 32 and meta["span"] == {"start_frame": 0, "frames": N}
    g = json.loads(gate.read_text())
    assert p["valid"].tolist() == [bool(v) for v in g["ok"]]                 # its aligned frames
    from seam import regions
    union = np.zeros((H, W), bool)
    for k in ("home_ink", "home_gold", "home_paper"):
        union |= chain.tm[k][0]
    want = ~regions.dilate(union, 32)
    for i in range(N):
        assert np.array_equal(p["R"][i], want & p["cover"][i])               # R_noop(t) ∩ cover(t)
    assert not p["cover"][0].all()                                            # the warp left a strip uncovered


def test_the_noop_pair_refuses_a_failed_gate(chain, tmp_path):
    bad = chain.write_gate("bad.json", render=lines_job.NOOP_ID, ok=[False] * N, frames_ok=0.0, **{"pass": False},
                           reason="frames")
    with pytest.raises(render_pair.PairError, match="failed the alignment gate"):
        render_pair.build_noop_pair(tmp_path / "x.npz", take_video=chain.take_video, video=chain.video,
                                    take_masks=chain.take_masks, gate=bad, m=32, take_frames=chain.take,
                                    render_frames=chain.rend)


def test_a_spanned_gate_writes_a_spanned_noop_pair_and_null(chain, tmp_path):
    span = (2, 3)
    rho = align.rho_record(chain.take, chain.take, chain.tm)["rho"]
    rend = chain.rend[2:5]
    g = align.run_gate(chain.take, rend, np.arange(3) / 15, chain.tm, rho, span=span)
    g = {"schema": align.GATE_SCHEMA, "render": lines_job.NOOP_ID, **g,
         "inputs": {"take_sha256": blind.sha256_path(chain.take_video), "video_sha256": blind.sha256_path(chain.video),
                    "take_masks_sha256": blind.sha256_path(chain.take_masks), "rho_sha256": "r" * 64}}
    gp = tmp_path / "g.json"
    gp.write_text(json.dumps(g))
    out = tmp_path / "noop.npz"
    meta = render_pair.build_noop_pair(out, take_video=chain.take_video, video=chain.video, take_masks=chain.take_masks,
                                       gate=gp, m=32, take_frames=chain.take, render_frames=rend)
    p = pairs.read_pair(out)
    assert meta["span"] == {"start_frame": 2, "frames": 3} and len(p["take"]) == 3
    assert np.array_equal(p["take"], chain.take[2:5]) and np.allclose(p["t"], np.arange(2, 5) / 15)
    null = tmp_path / "null.npz"
    render_pair.build_null_pair(null, take_video=chain.take_video, render_input=chain.take_video, height=720,
                                take_frames=chain.take, span=span)
    assert np.array_equal(pairs.read_pair(null)["take"], p["take"])         # the null's take is the pair's, frame for frame


def test_the_lines_job_measures_kappa_keep_on_the_noop_pair(chain, tmp_path):
    gate = chain.write_gate("noop-gate.json", render=lines_job.NOOP_ID)
    out = tmp_path / "noop.npz"
    render_pair.build_noop_pair(out, take_video=chain.take_video, video=chain.video, take_masks=chain.take_masks,
                                gate=gate, m=32, take_frames=chain.take, render_frames=chain.rend)
    null = tmp_path / "null.npz"
    render_pair.build_null_pair(null, take_video=chain.take_video, render_input=chain.take_video, height=720,
                                take_frames=chain.take)
    dark = lambda frames: [np.asarray(f)[..., 0] < 100 for f in frames]               # noqa: E731
    rec = lines_job.measure(out, null=null, extract=dark, chamfer=lines_job.chamfer_all)
    assert rec["kappa_render_p1"] is not None and rec["n_room_cells_render"] > 0       # κ_keep, over its aligned frames
    assert rec["kappa_codec"] is not None and rec["meta"]["render"] == lines_job.NOOP_ID


# --- review finding 9 (call 135): the touched object's interior excluded (a registered secondary) -------------------------
def test_a_pair_can_exclude_the_touched_objects_take_mask_from_R(chain, tmp_path):
    plain = pairs.read_pair(chain.build("plain.npz"))
    glass = np.zeros((N, H, W), bool)
    glass[:, 400:440, 600:660] = True
    ex = pairs.read_pair(chain.build("ex.npz", exclude=glass))
    for i in range(N):
        assert np.array_equal(ex["R"][i], plain["R"][i] & ~glass[i])
    assert ex["meta"]["variant"] == "interior_excluded" and "variant" not in plain["meta"]
    assert ex["valid"].tolist() == plain["valid"].tolist()
