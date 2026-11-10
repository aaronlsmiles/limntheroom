#!/usr/bin/env python3
"""An end-to-end synthetic rehearsal of the whole measurement chain, before any footage exists.

    uv run python tools/rehearse.py [--seconds 11] [--lines comfy|fake] [--repo DIR] [--neutral DIR]
                                    [--no-rating] [--keep]

No real creature, take, render or law. A drawn page on a textured desk, three drawn shapes where
capture/PROTOCOL.md puts the creatures (ink 55 mm, gold 148 mm, paper 242 mm from the left edge, centres
70 mm from the far edge), a glass of water carried in by a hand and set down about 3 cm in front of the
gold shape. The "render" is the same scene at 24 fps and 1280x720 in which the left shape steps out of its
home, walks to the glass and touches it (the glass rim is redrawn 3 px wider while it does), under a slight
drifting similarity warp, with noise and a lossy re-encode. Laws are the fictional fixture laws.

Every stage runs in order, through the modules' own command lines where they have one:
  ingest -> take-mask points (stub agent) -> take masks (SAM 2.1, CPU) -> cue sheet -> compile + the
  offline estimate -> ρ -> gate -> the blind pick, place, first track, check, final track, track-done
  (stub agent answers through the test helpers' fake transcripts: no `claude -p`, no paid call) -> the
  render pair and the codec null pair -> the lines job (`--lines comfy`: the ComfyUI venv, for real,
  read-only; `fake`: a dark-pixel extractor in this venv) -> assemble -> H -> rating seal and build.

All git activity happens in a throwaway repo (default `blind/rehearsal/`, gitignored): the blind ledgers,
the registry, the prompt files and every output live there. The blind folders go under a neutral root in
the system temp directory (the project path holds the project name, which a blind path may not). Nothing
is written to the prototype's own agents/logs/, masks/, runs/ or sealed/. The lines job's cache stays in
the prototype's gitignored cache/lines/ as usual.

The stub agents answer from the scene's known truth (the agents' competence is not under test; the
chain is). Prints one line per stage with its wall time, and writes `<repo>/rehearsal.json`.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from seam import blind, points  # noqa: E402

COMFY_PY = Path.home() / "tools/ComfyUI/.venv/bin/python"
TAKE, ATTEMPT, RENDER, MATERIAL = "t01", "a", "t01-ink", "ink"
TAKE_ID = TAKE + ATTEMPT
W, H = 1280, 720                 # analysis grid; the "original" is 1.5x (1920x1080)
S_ORIG = 1.5
TAKE_FPS, RENDER_FPS = 30, 24
KAPPA = 0.5                      # a stand-in κ_keep: the real one comes from the no-op render after Gate P2
M = 32

# ---- the set, in analysis pixels (capture/PROTOCOL.md: A4 landscape, 297 x 210 mm) ----------------------
PX_MM = 2.9                      # across the page
FORE = 0.82                      # the page's depth foreshortened at a 55 degree look-down
PAGE_X0, PAGE_Y0 = 210, 140      # the far-left corner
PAGE = np.array([(PAGE_X0 + 18, PAGE_Y0), (PAGE_X0 + 297 * PX_MM - 18, PAGE_Y0),
                 (PAGE_X0 + 297 * PX_MM + 18, PAGE_Y0 + 210 * PX_MM * FORE), (PAGE_X0 - 18, PAGE_Y0 + 210 * PX_MM * FORE)])
CY = PAGE_Y0 + 70 * PX_MM * FORE
HOMES = {"ink": (PAGE_X0 + 55 * PX_MM, CY), "gold": (PAGE_X0 + 148 * PX_MM, CY), "paper": (PAGE_X0 + 242 * PX_MM, CY)}
BODY = (62, 22)                  # half-axes: a 50 mm loaf (with its head and legs, about 145 px)
GLASS_R = 34
GLASS = (HOMES["gold"][0], CY + BODY[1] + 30 * PX_MM * FORE + GLASS_R * 0.4)
T_ENTER, T_SET, T_HOLD, T_OUT = 1.0, 2.0, 2.3, 3.0


def timeline(T):
    """(leave, touch, release, back): the left shape's moments in the render, scaled to the take's length."""
    return 0.36 * T, 0.59 * T, 0.77 * T, 0.86 * T


def ease(f):
    f = min(1.0, max(0.0, f))
    return f * f * (3 - 2 * f)


def hand_glass(t):
    """(glass centre or None, hand anchor or None) at take time t."""
    gx, gy = GLASS
    if t < T_ENTER:
        return None, None
    if t < T_SET:
        y = gy + 420 * (1 - ease((t - T_ENTER) / (T_SET - T_ENTER)))
        return (gx, y), (gx, y)
    if t < T_HOLD:
        return (gx, gy), (gx, gy)
    if t < T_OUT:
        return (gx, gy), (gx, gy + 460 * ease((t - T_HOLD) / (T_OUT - T_HOLD)))
    return (gx, gy), None


def ink_centre(t, T):
    """Where the left shape sits in the render at time t (its home until it leaves)."""
    leave, touch, release, back = timeline(T)
    hx, hy = HOMES["ink"]
    tx, ty = GLASS[0] - GLASS_R - BODY[0] - 2, GLASS[1] - 6      # body edge 2 px from the rim: contact
    bx, by = (hx + tx) / 2 - 20, ty + 34
    if t < leave:
        return hx, hy
    if t < touch:
        f = ease((t - leave) / (touch - leave))
        return hx + f * (tx - hx), hy + f * (ty - hy) - 18 * math.sin(math.pi * f)
    if t < release:
        return tx, ty
    if t < back:
        f = ease((t - release) / (back - release))
        return tx + f * (bx - tx), ty + f * (by - ty)
    return bx, by


def touching(t, T):
    _, touch, release, _ = timeline(T)
    return touch <= t < release


# ---- drawing --------------------------------------------------------------------------------------------
def _pt(x, y, s):
    return int(round(x * s)), int(round(y * s))


def desk(s, seed=7):
    """A static textured desk (a fixed draw, so every frame and both videos share it). Its clutter is full
    contrast: a muted wood-like palette left ORB (FAST threshold 20 on the 1 px-blurred grey) about ten
    keypoints outside the page, so every round-trip fit failed (finding, 3 Nov)."""
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    img = np.empty((h, w, 3), np.uint8)
    img[:] = (112, 86, 64)
    for _ in range(900):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        c = tuple(int(v) for v in rng.integers(0, 256, 3))
        k = rng.integers(0, 3)
        if k == 0:
            cv2.rectangle(img, (x, y), (x + int(rng.integers(6, 50 * s)), y + int(rng.integers(6, 40 * s))), c, -1)
        elif k == 1:
            cv2.circle(img, (x, y), int(rng.integers(3, 22 * s)), c, -1)
        else:
            cv2.line(img, (x, y), (x + int(rng.integers(-90, 90)), y + int(rng.integers(-30, 30))), c, 2)
    return img


def draw_shape(img, cx, cy, material, s, mask=False):
    """The c05-like loaf on four stub legs, drawn by material: ink outline, gold paint, cut paper.
    mask=True draws the filled silhouette in white (for the truth masks)."""
    ink, gold_fill, gold_line = (28, 26, 34), (196, 156, 52), (140, 104, 26)
    paper_fill, paper_line = (236, 226, 204), (128, 118, 98)
    c = _pt(cx, cy, s)
    ax = (int(BODY[0] * s), int(BODY[1] * s))
    legs = [(cx + dx, cy + BODY[1] - 4) for dx in (-40, -15, 15, 40)]
    eye = _pt(cx + 44, cy - 7, s)
    if mask:
        cv2.ellipse(img, c, ax, 0, 0, 360, 255, -1)
        for lx, ly in legs:
            cv2.line(img, _pt(lx, ly, s), _pt(lx, ly + 16, s), 255, max(2, int(6 * s)))
        return img
    if material == "ink":
        cv2.ellipse(img, c, ax, 0, 0, 360, ink, max(2, int(3 * s)), cv2.LINE_AA)
        for lx, ly in legs:
            cv2.line(img, _pt(lx, ly, s), _pt(lx, ly + 16, s), ink, max(2, int(3 * s)), cv2.LINE_AA)
        cv2.circle(img, eye, max(2, int(3 * s)), ink, -1, cv2.LINE_AA)
        cv2.line(img, _pt(cx - 30, cy - 4, s), _pt(cx + 10, cy - 10, s), ink, max(1, int(2 * s)), cv2.LINE_AA)
    elif material == "gold":
        cv2.ellipse(img, c, ax, 0, 0, 360, gold_fill, -1, cv2.LINE_AA)
        cv2.ellipse(img, c, ax, 0, 0, 360, gold_line, max(2, int(3 * s)), cv2.LINE_AA)
        for lx, ly in legs:
            cv2.line(img, _pt(lx, ly, s), _pt(lx, ly + 16, s), gold_line, max(3, int(5 * s)), cv2.LINE_AA)
        cv2.circle(img, eye, max(2, int(3 * s)), (60, 40, 10), -1, cv2.LINE_AA)
    else:
        cv2.ellipse(img, c, ax, 0, 0, 360, paper_fill, -1, cv2.LINE_AA)
        cv2.ellipse(img, c, ax, 0, 0, 360, paper_line, max(1, int(2 * s)), cv2.LINE_AA)
        for lx, ly in legs:
            p0, p1 = _pt(lx - 4, ly, s), _pt(lx + 4, ly + 16, s)
            cv2.rectangle(img, p0, p1, paper_fill, -1)
            cv2.rectangle(img, p0, p1, paper_line, 1)
        cv2.circle(img, eye, max(2, int(3 * s)), paper_line, -1, cv2.LINE_AA)
    return img


def draw_glass(img, g, s, wider=0):
    r = int((GLASS_R + wider) * s)
    c = _pt(*g, s)
    over = img.copy()
    cv2.circle(over, c, r, (200, 224, 238), -1, cv2.LINE_AA)
    img[:] = cv2.addWeighted(over, 0.65, img, 0.35, 0)
    cv2.circle(img, c, r, (70, 92, 112), max(2, int((3 + (1 if wider else 0)) * s)), cv2.LINE_AA)
    cv2.circle(img, c, int(r * 0.62), (120, 150, 170), max(1, int(2 * s)), cv2.LINE_AA)
    cv2.ellipse(img, _pt(g[0] - 12, g[1] - 14, s), (int(8 * s), int(4 * s)), -35, 0, 360, (250, 252, 255), -1, cv2.LINE_AA)


def draw_hand(img, a, s):
    x, y = a
    poly = np.array([_pt(x - 46, H + 60, s), _pt(x - 30, y + 18, s), _pt(x + 30, y + 18, s), _pt(x + 46, H + 60, s)], np.int32)
    cv2.fillPoly(img, [poly], (204, 158, 128), cv2.LINE_AA)
    cv2.polylines(img, [poly], True, (150, 104, 84), max(1, int(2 * s)), cv2.LINE_AA)
    for dx in (-16, 0, 16):
        cv2.line(img, _pt(x + dx, y + 20, s), _pt(x + dx * 1.2, y + 70, s), (160, 112, 90), max(1, int(2 * s)), cv2.LINE_AA)


def scene(t, s, base, *, render=False, T=None):
    img = base.copy()
    cv2.fillPoly(img, [np.int32(PAGE * s)], (244, 243, 238), cv2.LINE_AA)
    for mat, (hx, hy) in HOMES.items():
        if render and mat == "ink":
            hx, hy = ink_centre(t, T)
        draw_shape(img, hx, hy, mat, s)
    g, a = hand_glass(t)
    if g is not None:
        draw_glass(img, g, s, wider=3 if (render and touching(t, T) and a is None) else 0)
    if a is not None:
        draw_hand(img, a, s)
    return img


def render_warp(t, T):
    """The render's drifting similarity (take -> render), 2x3."""
    ang = 0.08 + 0.04 * math.sin(2 * math.pi * t / T)
    sc = 1.002
    M_ = cv2.getRotationMatrix2D((W / 2, H / 2), ang, sc)
    M_[:, 2] += (2.3 + 0.4 * math.sin(2 * math.pi * t / T), -1.4 + 0.3 * math.cos(2 * math.pi * t / T))
    return M_


def truth_creature(t, T):
    """The left shape's silhouette in render pixels at render time t."""
    m = np.zeros((H, W), np.uint8)
    draw_shape(m, *ink_centre(t, T), "ink", 1.0, mask=True)
    return cv2.warpAffine(m, render_warp(t, T), (W, H), flags=cv2.INTER_NEAREST) > 0


def _encode(path, frames_iter, size, fps, crf):
    w, h = size
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                          "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                          "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)
    for f in frames_iter:
        p.stdin.write(np.ascontiguousarray(f, np.uint8).tobytes())
    p.stdin.close()
    if p.wait():
        raise RuntimeError(f"ffmpeg failed writing {path}")


def make_take(path, T):
    base = desk(S_ORIG)
    rng = np.random.default_rng(1)
    n = int(round(T * TAKE_FPS))

    def frames():
        for k in range(n):
            f = scene(k / TAKE_FPS, S_ORIG, base).astype(np.int16)
            yield np.clip(f + rng.normal(0, 1.0, f.shape), 0, 255).astype(np.uint8)
    _encode(path, frames(), (int(W * S_ORIG), int(H * S_ORIG)), TAKE_FPS, 14)


def render_frame(t, T, base):
    """The render at time t: the scene drawn at the original's scale (the model sees the 1080p input), brought
    to 1280x720 by area interpolation, then the drifting warp. (Drawing it at 1280x720 directly gave a desk
    rasterised differently from the take's, which alone put every residual near 1.2 px, over ρ.)"""
    big = scene(t, S_ORIG, base, render=True, T=T)
    small = cv2.resize(big, (W, H), interpolation=cv2.INTER_AREA)
    return cv2.warpAffine(small, render_warp(t, T), (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def make_render(path, T):
    base = desk(S_ORIG)
    rng = np.random.default_rng(2)
    n = int(round((T + 0.25) * RENDER_FPS))

    def frames():
        for k in range(n):
            t = k / RENDER_FPS
            f = render_frame(t, T, base).astype(np.int16)
            yield np.clip(f + rng.normal(0, 2.0, f.shape), 0, 255).astype(np.uint8)
    _encode(path, frames(), (W, H), RENDER_FPS, 26)


def make_crops(folder):
    """Flat-scan crops of the three shapes on transparency (2 px per analysis px), and crops.json."""
    folder.mkdir(parents=True, exist_ok=True)
    s = 2.0
    out = {}
    for mat in HOMES:
        w, h = int(170 * s), int(80 * s)
        rgb = np.full((h, w, 3), 255, np.uint8)
        a = np.zeros((h, w), np.uint8)
        cx, cy = 85, 34
        draw_shape(rgb, cx, cy, mat, s)
        draw_shape(a, cx, cy, mat, s, mask=True)
        rgba = np.dstack([rgb, a])
        cv2.imwrite(str(folder / f"{mat}.png"), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
        out[mat] = {"file": f"{mat}.png"}
    (folder / "crops.json").write_text(json.dumps({"crops": out}, indent=1) + "\n")
    return folder / "crops.json"


# ---- the stub agent --------------------------------------------------------------------------------------
def stub(record_fn, code, answer, scratch):
    """Answer a prepared folder through the test helpers' fake stream and store (no live call)."""
    import blindkit
    blindkit.PER_MESSAGE = 10          # as a real agent batches its reads (one file per turn would pass maxTurns)
    st = blind.read_state(blind.STATE, code)
    return blindkit.run(record_fn, st, scratch, json.dumps(answer), name=f"stub-{code}")


def _cli(fn, argv):
    """Run a module's main(argv) in-process; (exit code, stdout)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(argv)
    out = buf.getvalue()
    sys.stdout.write(out)
    if rc:
        raise RuntimeError(f"{getattr(fn, '__module__', fn)} {argv[:1]} exited {rc}")
    return out


def _code(out):
    return json.loads(out[out.index("{"):])["code"]


def point_roots(repo, neutral):
    """Every root of seam/blind.py and seam/points.py at the throwaway repo (as tests/conftest.py does)."""
    blind.NEUTRAL_ROOT = Path(neutral)
    blind.GIT_ROOT = Path(repo)
    blind.LOGS = Path(repo) / "agents" / "logs"
    blind.STATE = Path(repo) / "blind"
    blind.TRANSCRIPTS = Path(repo) / "blind" / "transcripts"
    blind.SEALED = Path(repo) / "sealed"
    blind.SEALED_STATE = Path(repo) / "sealed" / "blind"
    blind.SEALED_TRANSCRIPTS = Path(repo) / "sealed" / "blind" / "transcripts"
    points.PROMPTS = Path(repo) / "masks" / "prompts"


def _iou(a, b):
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else None


# ---- the run --------------------------------------------------------------------------------------------
class Rehearsal:
    def __init__(self, repo, neutral, seconds, lines, rating=True, comfy=COMFY_PY):
        self.repo, self.neutral, self.T, self.lines, self.do_rating, self.comfy = \
            Path(repo), Path(neutral), float(seconds), lines, rating, Path(comfy)
        self.stages, self.findings = [], {}
        self.scratch = self.repo / "blind" / "stub"
        p = self.p
        self.laws = p("laws-fixture.json")
        self.original, self.render_video = p("raw", "IMG_0001.mp4"), p("renders", f"{RENDER}.mp4")
        self.crops = p("creature", "scan", "crops.json")
        self.analysis, self.render_input = p("takes", f"{TAKE_ID}.analysis.mp4"), p("takes", f"{TAKE_ID}.render.mp4")
        self.take_masks_path, self.sheet = p("masks", f"{TAKE_ID}.npz"), p("cues", f"{TAKE}.json")
        self.rho, self.gate = p("runs", "registration", f"{TAKE_ID}.rho.json"), p("runs", "gate", f"{RENDER}.json")
        self.final_prompts = p("masks", "prompts", "render", f"{RENDER}.json")
        self.track = p("masks", "render", f"{RENDER}.npz")
        self.pair_path, self.null_path = p("runs", "pairs", f"{RENDER}.npz"), p("runs", "pairs", f"{TAKE_ID}.null720.npz")
        self.lines_out, self.seam = p("runs", "lines", f"{RENDER}.json"), p("runs", "seam", f"{RENDER}.bin")
        self.measure = p("runs", "measure", f"{RENDER}.json")

    # paths
    def p(self, *a):
        return self.repo.joinpath(*a)

    def stage(self, name, fn):
        t0 = time.perf_counter()
        print(f"--- {name}", flush=True)
        try:
            note = fn()
            ok, err = True, None
        except Exception as e:      # noqa: BLE001 - a rehearsal records the failure and stops
            ok, err, note = False, f"{type(e).__name__}: {e}", None
        dt = time.perf_counter() - t0
        self.stages.append({"stage": name, "ok": ok, "seconds": round(dt, 2), "note": note, "error": err})
        print(f"    {'ok' if ok else 'FAILED'} in {dt:.1f} s{'' if ok else ': ' + err}" + (f" ({note})" if ok and note else ""),
              flush=True)
        if not ok:
            raise SystemExit(1)

    def restore(self):
        """Resume in an existing rehearsal repo: the roots, and what earlier stages left (for --resume-from)."""
        if self.neutral.exists():
            shutil.rmtree(self.neutral)
        self.neutral.mkdir(parents=True)
        point_roots(self.repo, self.neutral)
        self.scratch.mkdir(parents=True, exist_ok=True)
        old = self.repo / "rehearsal.json"
        if old.exists():
            prev = json.loads(old.read_text())
            self.findings = prev.get("findings", {})
            self.stages = [s_ for s_ in prev.get("stages", []) if s_["ok"]]
        from seam import masks
        if self.take_masks_path.exists():
            self.n = masks.load_masks(self.take_masks_path)[0]["n_frames"]
        pf = self.repo / "agents" / "logs" / "prompt-frame" / f"{RENDER}.json"
        if pf.exists() and (json.loads(pf.read_text()).get("result") or {}).get("frame") is not None:
            self.prompt_frame = json.loads(pf.read_text())["result"]["frame"]

    def setup(self):
        if self.repo.exists():
            shutil.rmtree(self.repo)
        self.repo.mkdir(parents=True)
        subprocess.run(["git", "-C", str(self.repo), "init", "-q", "-b", "main"], check=True)
        for k, v in (("user.email", "rehearsal@example.invalid"), ("user.name", "rehearsal"), ("commit.gpgsign", "false")):
            subprocess.run(["git", "-C", str(self.repo), "config", k, v], check=True)
        (self.repo / ".gitignore").write_text("blind/\nsealed/\nraw/\ntakes/\nrenders/\nruns/\ncache/\nrating/\n*.npz\n*.mp4\n")
        if self.neutral.exists():
            shutil.rmtree(self.neutral)
        self.neutral.mkdir(parents=True)
        blind.check_path_words(self.neutral)
        point_roots(self.repo, self.neutral)
        self.scratch.mkdir(parents=True, exist_ok=True)
        (self.p("capture")).mkdir()
        shutil.copy(ROOT / "capture" / "takes.json", self.p("capture", "takes.json"))     # read, never written
        from test_rating_prepare import fixture_laws
        self.laws.write_text(json.dumps(fixture_laws(), indent=1) + "\n")

    # 0
    def make_inputs(self):
        self.p("raw").mkdir()
        make_take(self.original, self.T)
        self.p("renders").mkdir()
        make_render(self.render_video, self.T)
        make_crops(self.crops.parent)
        return f"{self.T:g} s take at {TAKE_FPS} fps 1920x1080; render at {RENDER_FPS} fps 1280x720"

    # 1
    def ingest(self):
        from seam import ingest
        _cli(ingest.main, [str(self.original), "--take", TAKE, "--attempt", ATTEMPT, "--root", str(self.repo)])
        from seam import masks, video
        a = masks.analysis_frames(self.analysis)
        fr, pts = video.read_video(self.analysis)
        b = video.resample(fr, pts, video.analysis_times(pts[-1]))
        same = a.shape == b.shape and np.array_equal(a, b)
        self.findings["take_samplers_agree"] = bool(same)
        self.n = len(a)
        return f"{self.n} analysis frames; masks and video samplers agree on the take: {same}"

    # 2
    def take_points(self):
        from seam import points as pts_
        out = _cli(pts_.main, ["take", "--video", str(self.analysis), "--take", TAKE_ID, "--cue", "glass"])
        code = _code(out)
        st = blind.read_state(blind.STATE, code)

        def still_at(t):
            fr = int(round(t * 15))
            k = min(range(len(st["stills"])), key=lambda j: abs(st["stills"][j]["frame"] - fr))
            return k + 1, st["stills"][k]["frame"] / 15

        hs, ht = still_at(1.6)
        g_h, a_h = hand_glass(ht)
        gs, gt = still_at(2.6)
        want = {"page": [(1, 300, 600), (1, 1000, 600)],
                "home_ink": [(1, *HOMES["ink"])], "home_gold": [(1, *HOMES["gold"])], "home_paper": [(1, *HOMES["paper"])],
                "hand": [(hs, a_h[0], min(H - 2, a_h[1] + 80))], "glass": [(gs, *GLASS)]}
        ans = {"objects": {k: [{"still": s, "x": float(x), "y": float(y), "positive": True} for s, x, y in want[o]]
                           for k, o in st["letters"].items()}, "not_found": []}
        log = stub(pts_.record, code, ans, self.scratch)
        assert log["steps"]["place"]["result"]["status"] == "placed", log["steps"]["place"]["attempts"][-1]["problems"]
        return f"{len(st['stills'])} stills, {len(st['letters'])} objects placed"

    # 3
    def take_masks(self):
        from seam import masks
        _cli(masks.main, ["track", "--video", str(self.analysis), "--prompts", str(self.p("masks", "prompts", f"{TAKE_ID}.json")),
                          "--out", str(self.take_masks_path)])
        _, m = masks.load_masks(self.take_masks_path)
        # truth for the homes and the settled glass
        truth = {}
        for mat in HOMES:
            t_ = np.zeros((H, W), np.uint8)
            draw_shape(t_, *HOMES[mat], mat, 1.0, mask=True)
            truth[f"home_{mat}"] = t_ > 0
        g = np.zeros((H, W), np.uint8)
        cv2.circle(g, _pt(*GLASS, 1.0), GLASS_R, 255, -1)
        last = self.n - 1
        ious = {k: _iou(np.asarray(m[k][last]), v) for k, v in truth.items()}
        ious["glass"] = _iou(np.asarray(m["glass"][last]), g > 0)
        hand_frames = [i for i in range(self.n) if m["hand"][i].any()]
        self.findings["take_mask_iou_last_frame"] = {k: (round(v, 3) if v is not None else None) for k, v in ious.items()}
        self.findings["hand_track_frames"] = [hand_frames[0], hand_frames[-1]] if hand_frames else None
        return "IoU at the last frame " + ", ".join(f"{k} {v:.2f}" for k, v in ious.items() if v is not None)

    # 4
    def cues(self):
        from seam.cues import sheet
        _cli(sheet.main, ["--take", TAKE, "--video", str(self.analysis), "--fires", "water", "--target", MATERIAL,
                          "--masks", str(self.take_masks_path), "--object", "glass=water", "--out", str(self.sheet)])
        s = json.loads(self.sheet.read_text())
        fired = [e for e in s["events"] if e["target"] == MATERIAL]
        assert fired, "no event fires the acting creature's law"
        self.findings["cue_events"] = [[e["id"], e["t"], e["cue"], e["source"], e["target"]] for e in s["events"]]
        return f"{len(s['events'])} event(s); the glass settles at {fired[0]['t']} s (set down at {T_SET} s)"

    # 5
    def compile(self):
        from seam import compile as comp
        notes = []
        for model in ("aleph2", "kling_4"):
            out = self.p("runs", "requests", f"{RENDER}.{model}.json")
            argv = ["--sheet", str(self.sheet), "--laws", str(self.laws), "--takes", str(self.p("capture", "takes.json")),
                    "--take", TAKE, "--material", MATERIAL, "--model", model, "--video", str(self.render_input), "--out", str(out)]
            if comp.MODELS[model]["references"]:
                argv += ["--reference", str(self.crops.parent / f"{MATERIAL}.png")]
            _cli(comp.main, argv)
            env = {k: v for k, v in os.environ.items() if k != "RUNWAY_API_KEY"}
            r = subprocess.run([sys.executable, str(ROOT / "vendor" / "runway" / "runway_gen.py"), "estimate", str(out)],
                               capture_output=True, text=True, env=env, timeout=300)
            if r.returncode:
                raise RuntimeError(f"estimate {model}: {r.stderr.strip()[-300:]}")
            est = json.loads(r.stdout.strip().splitlines()[-1])
            notes.append(f"{model} {est['tier']} ~{est['estimate_credits']} credits")
            self.findings.setdefault("estimates", {})[model] = est
        return "; ".join(notes)

    # 6
    def rho_gate(self):
        from seam import align
        t0 = time.perf_counter()
        _cli(align.main, ["rho", "--take", str(self.analysis), "--render-input", str(self.render_input),
                          "--take-masks", str(self.take_masks_path), "--out", str(self.rho)])
        t_rho = time.perf_counter() - t0
        _cli(align.main, ["gate", "--render", RENDER, "--video", str(self.render_video), "--take", str(self.analysis),
                          "--take-masks", str(self.take_masks_path), "--rho", str(self.rho), "--out", str(self.gate)])
        g = json.loads(self.gate.read_text())
        self.findings["gate"] = {k: g.get(k) for k in ("pass", "rho", "lag", "frames_ok", "reason", "lag_source",
                                                        "lag_applicable", "lag_reason")}
        self.findings["rho_seconds"] = round(t_rho, 1)
        if not g["pass"]:
            raise RuntimeError(f"the synthetic render failed the gate: {g['reason']}")
        # the render through both samplers
        from seam import masks, video
        a = masks.analysis_frames(self.render_video)[:self.n]
        fr, pts = video.read_video(self.render_video)
        b = video.resample(fr, pts, np.arange(self.n) / 15)
        self.findings["render_samplers_agree"] = bool(a.shape == b.shape and np.array_equal(a, b))
        return f"ρ {g['rho']:.3f} px; pass {g['pass']}, lag {g['lag']}, frames ok {g['frames_ok']:.3f}"

    # 7
    def pick(self):
        from seam import frame_pick, masks
        out = _cli(frame_pick.main, ["prepare", "--video", str(self.render_video), "--render", RENDER,
                                     "--take-masks", str(self.take_masks_path)])
        code = _code(out)
        st = blind.read_state(blind.STATE, code)
        home = frame_pick.load_home(self.take_masks_path, RENDER)
        self.render_frames = masks.analysis_frames(self.render_video)
        pick = "none"                    # the truth at the nominal analysis times i / 15
        for k, s in enumerate(st["stills"], start=1):
            if not (truth_creature(s["frame"] / 15, self.T) & home).any():
                pick = k
                break
        log = stub(frame_pick.record, code, {"pick": pick}, self.scratch)
        self.prompt_frame = log["result"]["frame"]
        self.findings["prompt_frame"] = self.prompt_frame
        self.findings["prompt_frame_truth_s"] = round(timeline(self.T)[0], 2)
        return f"still {pick} -> analysis frame {self.prompt_frame} ({self.prompt_frame / 15:.2f} s)"

    # 8
    def place_track_check(self):
        from seam import masks, points as pts_
        f = self.prompt_frame
        tm = ["--video", str(self.render_video), "--render", RENDER, "--take-masks", str(self.take_masks_path)]
        code = _code(_cli(pts_.main, ["render", *tm]))
        cx, cy = ink_centre(f / 15, self.T)
        X, Y = render_warp(f / 15, self.T) @ np.array([cx, cy, 1.0])
        stub(pts_.record, code, {"x": float(X), "y": float(Y)}, self.scratch)
        prom = self.p("masks", "prompts", "render")
        first = self.p("masks", "render", f"{RENDER}.p1.npz")
        t0 = time.perf_counter()
        _cli(masks.main, ["track", "--video", str(self.render_video), "--prompts", str(prom / f"{RENDER}.p1.json"),
                          "--out", str(first)])
        t_first = time.perf_counter() - t0
        _, m1 = masks.load_masks(first)
        truth = truth_creature(f / 15, self.T)
        iou1 = _iou(m1["creature"][f], truth)
        code = _code(_cli(pts_.main, ["render-check", *tm, "--masks", str(first)]))
        if iou1 is not None and iou1 >= 0.6:
            ans = {"covers": True}
        else:   # the one second point: on the outline's top
            tx, ty = render_warp(f / 15, self.T) @ np.array([cx, cy - BODY[1], 1.0])
            ans = {"covers": False, "x": float(tx), "y": float(ty), "positive": True}
        log = stub(pts_.record, code, ans, self.scratch)
        _cli(masks.main, ["track", "--video", str(self.render_video), "--prompts", str(self.final_prompts), "--out", str(self.track)])
        _cli(pts_.main, ["track-done", "--render", RENDER, "--masks", str(self.track)])
        _, mf = masks.load_masks(self.track)
        ious = [_iou(mf["creature"][i], truth_creature(i / 15, self.T)) for i in range(f, min(self.n, len(mf["creature"])))]
        ious = [x for x in ious if x is not None]
        self.findings["render_track"] = {"first_iou_at_prompt": round(iou1, 3) if iou1 is not None else None,
                                         "check": log["steps"]["check"]["result"]["status"],
                                         "final_iou_median": round(float(np.median(ious)), 3) if ious else None,
                                         "final_iou_min": round(float(np.min(ious)), 3) if ious else None,
                                         "first_track_seconds": round(t_first, 1)}
        return (f"first IoU {iou1:.2f} at the prompt frame; check {log['steps']['check']['result']['status']}; "
                f"final track IoU median {np.median(ious):.2f}")

    # 9
    def pair(self):
        from seam import pairs, render_pair
        _cli(render_pair.main, ["render", "--render", RENDER, "--take", str(self.analysis), "--video", str(self.render_video),
                                "--take-masks", str(self.take_masks_path), "--track", str(self.track),
                                "--prompts", str(self.final_prompts), "--gate", str(self.gate), "--m", str(M),
                                "--crops", str(self.crops), "--out", str(self.pair_path)])
        _cli(render_pair.main, ["null", "--take", str(self.analysis), "--render-input", str(self.render_input),
                                "--height", "720", "--out", str(self.null_path)])
        P = pairs.read_pair(self.pair_path)
        self.findings["pair"] = {"frames": int(len(P["t"])), "valid": int(P["valid"].sum()),
                                 "bytes": self.pair_path.stat().st_size}
        return f"{int(P['valid'].sum())}/{len(P['t'])} frames scored; {self.pair_path.stat().st_size / 1e6:.0f} MB"

    # 10
    def lines_job(self):
        argv = ["measure", "--pair", str(self.pair_path), "--render", RENDER, "--prompts", str(self.final_prompts),
                "--null", str(self.null_path), "--kappa", str(KAPPA), "--out", str(self.lines_out), "--seam", str(self.seam)]
        if self.lines == "comfy":
            if not self.comfy.exists():
                raise RuntimeError(f"no ComfyUI venv at {self.comfy}")
            r = subprocess.run([str(self.comfy), str(ROOT / "tools" / "rehearse_lines.py"), "--repo", str(self.repo),
                                "--neutral", str(self.neutral), "--", *argv], cwd=str(ROOT))
            if r.returncode:
                raise RuntimeError(f"the lines job exited {r.returncode}")
        else:
            from seam import lines_job
            ns = lines_job.build_parser().parse_args(argv)
            lines_job.check_custody(ns)
            rec = lines_job.measure(ns.pair, null=ns.null, kappa=ns.kappa, seam_path=ns.seam, chamfer=lines_job.chamfer_all,
                                    extract=lambda fr: [np.asarray(f).min(axis=2) < 110 for f in fr])
            rec["extractor"] = "fake: min channel < 110 (rehearsal only)"
            lines_job._write(ns.out, rec)
        rec = json.loads(self.lines_out.read_text())
        self.findings["lines"] = {"seconds": rec.get("seconds"), "kappa_codec": rec.get("kappa_codec"),
                                  "kappa_render_p1": rec.get("kappa_render_p1"), "device": rec.get("device"),
                                  "extractor": rec.get("extractor", "StillDrawn inkstab")}
        return f"{rec['n_frames']} frames in {rec['seconds']:.0f} s; κ_codec {rec.get('kappa_codec')}"

    # 11
    def assemble(self):
        from seam import assemble
        _cli(assemble.main, ["--render", RENDER, "--pair", str(self.pair_path), "--lines", str(self.lines_out),
                             "--gate", str(self.gate), "--take-masks", str(self.take_masks_path), "--touched", "glass",
                             "--hand", "hand", "--m", str(M), "--kappa", str(KAPPA), "--kappa-source", "kappa_codec",
                             "--prompts", str(self.final_prompts), "--seam-root", str(self.repo), "--out", str(self.measure)])
        rec = json.loads(self.measure.read_text())
        s = rec["summary"]
        contact = [i for i, c in enumerate(rec["series"]["contact"]) if c]
        _, touch, release, _ = timeline(self.T)
        self.findings["measure"] = {k: s.get(k) for k in ("n_frames", "n_scored", "n_eligible", "n_contact",
                                                           "n_eligible_contact", "n_eligible_noncontact", "r")}
        self.findings["contact_frames"] = [contact[0], contact[-1]] if contact else None
        self.findings["contact_truth_frames"] = [math.ceil(touch * 15), math.ceil(release * 15) - 1]
        return f"{s['n_scored']}/{s['n_frames']} scored, {s['n_eligible']} eligible, {s['n_contact']} contact, r = {s['r']}"

    # 12
    def h_test(self):
        from analysis import h_contact
        meta = self.p("runs", "measure", "META.json")
        meta.write_text(json.dumps({RENDER: {"material": MATERIAL}}))
        out = self.p("analysis", "out", "h_contact.json")
        _cli(h_contact.main, [str(self.measure), "--meta", str(meta), "--out", str(out)])
        first = out.read_bytes()
        _cli(h_contact.main, [str(self.measure), "--meta", str(meta), "--out", str(out)])
        res = json.loads(out.read_text())
        self.findings["h"] = {"verdict": res["primary"].get("verdict"), "n_testable": res["primary"].get("n_testable"),
                              "per_render": res["per_render"], "byte_identical_rerun": first == out.read_bytes()}
        return f"verdict {res['primary'].get('verdict')} ({res['primary'].get('n_testable')} testable; one render)"

    # 13
    def rating(self):
        from rating import prepare
        sealed = self.p("sealed")
        _cli(prepare.main, ["seal", "--laws", str(self.laws), "--takes", str(self.p("capture", "takes.json")),
                            "--sealed", str(sealed)])
        clips = self.p("rating-src")
        clips.mkdir()
        rows = [r for r in json.loads(self.p("capture", "takes.json").read_text()) if r.get("rated")]
        entries = []
        for i, r in enumerate(rows):
            mat = r["target_material"]
            if (r["id"], mat) == (TAKE, MATERIAL):
                src = self.render_video
            else:            # stand-ins for the other seven renders: the synthetic one, hue-shifted
                src = clips / f"{r['id']}-{mat}.mp4"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(self.render_video), "-vf", f"hue=h={45 * i}",
                                "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", str(src)], check=True)
            e = {"take": r["id"], "material": mat, "render": os.path.relpath(src, self.repo),
                 "take_video": os.path.relpath(self.analysis, self.repo)}
            if (r["id"], mat) == (TAKE, MATERIAL):
                e["cues"] = os.path.relpath(self.sheet, self.repo)
            else:
                e["cue_s"] = 2.4
            entries.append(e)
        inputs = self.p("rating-inputs.json")
        inputs.write_text(json.dumps({"schema": "p47-rating-inputs/1", "entries": entries}, indent=1))
        argv = ["build", "--inputs", str(inputs), "--laws", str(self.laws), "--takes", str(self.p("capture", "takes.json")),
                "--sealed", str(sealed), "--out", str(self.p("rating")), "--raters", "2", "--seconds", "4"]
        bp = Path(prepare.DEFAULT_BLINDPANEL)
        if not (bp.exists() and shutil.which("node")):
            argv.append("--no-blindpanel")
        _cli(prepare.main, argv)
        man = json.loads((sealed / "rating-manifest.json").read_text())
        self.findings["rating"] = {"studies": len(man.get("studies", [])), "items": len(man.get("items", [])),
                                   "frames": man.get("frames"), "blindpanel": "--no-blindpanel" not in argv}
        return f"{len(man.get('studies', []))} studies, {len(man.get('items', []))} items, blindpanel {'--no-blindpanel' not in argv}"

    def run(self, resume_from=None):
        steps = [("make inputs", self.make_inputs), ("ingest", self.ingest), ("take-mask points (stub)", self.take_points),
                 ("take masks (SAM 2.1)", self.take_masks), ("cue sheet", self.cues), ("compile + estimate", self.compile),
                 ("rho + gate", self.rho_gate), ("blind pick (stub)", self.pick),
                 ("place, tracks, check, track-done", self.place_track_check), ("render pair + null pair", self.pair),
                 (f"lines job ({self.lines})", self.lines_job), ("assemble", self.assemble), ("H test", self.h_test)]
        if self.do_rating:
            steps.append(("rating seal + build", self.rating))
        if resume_from:
            names = [n for n, _ in steps]
            if resume_from not in names:
                raise SystemExit(f"--resume-from: want one of {names}")
            self.restore()
            steps = steps[names.index(resume_from):]
        else:
            self.setup()
        t0 = time.perf_counter()
        try:
            for name, fn in steps:
                self.stage(name, fn)
        finally:
            total = time.perf_counter() - t0
            rep = {"schema": "p47-rehearsal/1", "seconds": self.T, "lines": self.lines, "total_seconds": round(total, 1),
                   "stages": self.stages, "findings": self.findings,
                   "ledger_commits": subprocess.run(["git", "-C", str(self.repo), "log", "--oneline"], capture_output=True,
                                                    text=True).stdout.count("\n")}
            (self.repo / "rehearsal.json").write_text(json.dumps(rep, indent=1, sort_keys=True, default=str) + "\n")
            print(f"total {total:.0f} s; report {self.repo / 'rehearsal.json'}", flush=True)
        return rep


def default_neutral():
    for _ in range(20):
        d = Path(tempfile.mkdtemp(prefix="rehearse-nr-"))
        try:
            blind.check_path_words(d)
            return d
        except blind.BlindError:
            shutil.rmtree(d, ignore_errors=True)
    raise RuntimeError("no clean temporary directory name")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seconds", type=float, default=11.0, help="the take's length (6 or more)")
    ap.add_argument("--lines", choices=("comfy", "fake"), default="comfy")
    ap.add_argument("--repo", default=str(ROOT / "blind" / "rehearsal"), help="the throwaway git repo (rebuilt)")
    ap.add_argument("--neutral", help="the blind folders' root (default: a fresh temporary directory)")
    ap.add_argument("--no-rating", action="store_true")
    ap.add_argument("--keep", action="store_true", help="keep the neutral root afterwards")
    ap.add_argument("--resume-from", metavar="STAGE", help="rerun from this stage in the existing repo (debugging)")
    a = ap.parse_args(argv)
    if a.seconds < 6:
        ap.error("--seconds must be at least 6 (the glass is set down at 2 s)")
    neutral = Path(a.neutral) if a.neutral else default_neutral()
    r = Rehearsal(a.repo, neutral, a.seconds, a.lines, rating=not a.no_rating)
    try:
        r.run(resume_from=a.resume_from)
    finally:
        if not a.keep:
            shutil.rmtree(neutral, ignore_errors=True)
    return 0 if all(s["ok"] for s in r.stages) else 1


if __name__ == "__main__":
    sys.exit(main())
