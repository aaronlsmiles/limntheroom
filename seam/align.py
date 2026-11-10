"""The alignment gate (R0.3): lag check, per-frame similarity fit, ρ from the round trip, warp.

Time. Motion energy e(t) = mean |grey_t − grey_{t−1}| (grey 0–255) inside the take's hand and
prop masks at t, for the take and for the render (on the same masks). The best lag maximises
Pearson r over lags −5…+5 analysis frames; positive = the render is late, i.e.
render(t + lag) ≈ take(t). Ties go to the smaller |lag|, then the negative one. Pass iff
|lag| ≤ 1.

Space. Per frame, a similarity transform render → take: ORB (4,000 features, one pyramid level,
keypoints refined with cv2.cornerSubPix in an 11×11 window, both greys blurred by a Gaussian
of sigma 1 px first) on both frames
under one mask, the frame minus the page dilated by 64 px; Hamming brute-force matching with
cross-check; cv2.estimateAffinePartial2D with RANSAC (3 px, 2,000 iterations, confidence
0.999, 10 refine iterations; RNG seeded 20261031 before each fit). Residual = RMS
reprojection error of the inliers. Fewer than 20 matches or inliers: no fit (the frame scores
None). A frame passes iff residual ≤ ρ and |scale − 1| ≤ 0.01, with
ρ = max(1.0 px, 2 × P99 of the residuals on the take's own 720p round trip).

A render is aligned iff at least 90 % of its frames pass, it covers the take's analysis span, and
the lag check passes. The take's mean motion energy is taken over the frames where its hand or prop
masks are non-empty (call 126: a hand that moves for 2 s of 11 is not diluted by the 9 s it is
away). A take with no such frame (the breath take) has nothing to time: its lag check is "not
applicable", and so is one whose mean energy over those frames is below ENERGY_FLOOR. Either way
the reason is recorded and the gate rests on duration and the spatial test.

Uncovered pixels. The warp leaves a strip along the take's border that the render frame does not
reach (filled by replicating the render's edge). `cover` marks the pixels the render does reach;
the pair writer removes the rest from R(t) (call 126), so they are never scored as kept or redrawn.
"""
import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

SIZE = (1280, 720)
PAGE_MARGIN = 64
ORB_FEATURES = 4000
ORB_LEVELS = 1           # full resolution only: scale must be 1 ± 0.01 anyway, and pyramid
                         # levels quantise keypoint positions to coarse pixels
SUBPIX_WIN = 5           # half-window: 11×11
PRE_BLUR = 1.0           # Gaussian sigma (px) on both greys before detection and refinement
SUBPIX_ITERS = 30
SUBPIX_EPS = 0.01
RANSAC_PX = 3.0
RANSAC_ITERS = 2000
RANSAC_CONF = 0.999
REFINE_ITERS = 10
MIN_POINTS = 20
RNG_SEED = 20261031
SCALE_TOL = 0.01
MIN_FRAC = 0.90
MAX_LAG = 5
LAG_TOL = 1
ENERGY_FLOOR = 1.0       # mean grey levels per frame, over the frames with a hand or prop mask: below
                         # it the take barely moves there and the lag check is "not applicable" (to be
                         # confirmed on the real takes before Gate R)

PARAMS = {
    "page_margin_px": PAGE_MARGIN, "orb_features": ORB_FEATURES, "orb_levels": ORB_LEVELS, "pre_blur_sigma": PRE_BLUR,
    "subpix": f"cv2.cornerSubPix win {2 * SUBPIX_WIN + 1}x{2 * SUBPIX_WIN + 1}, {SUBPIX_ITERS} iters, eps {SUBPIX_EPS}", "ransac_px": RANSAC_PX,
    "ransac_iters": RANSAC_ITERS, "ransac_conf": RANSAC_CONF, "refine_iters": REFINE_ITERS,
    "min_points": MIN_POINTS, "rng_seed": RNG_SEED, "scale_tol": SCALE_TOL, "min_frac": MIN_FRAC,
    "max_lag": MAX_LAG, "lag_tol": LAG_TOL, "energy_floor": ENERGY_FLOOR,
    "lag_source": "the take's hand and prop masks; not applicable when no frame has one (the breath take)",
    "lag_energy_mean": "over the frames where the hand or prop masks are non-empty",
    "rho": "max(1.0, 2 * P99 round-trip residual)",
}


@dataclass
class Fit:
    M: np.ndarray          # 2×3, render -> take
    scale: float
    residual: float        # RMS inlier reprojection error, px
    n_matches: int
    n_inliers: int


def grey(frame):
    f = np.asarray(frame)
    if f.ndim == 3:
        return cv2.cvtColor(f, cv2.COLOR_RGB2GRAY)
    return f.astype(np.uint8)


def exclusion(page_mask, margin=PAGE_MARGIN):
    """True where features are not used: the page dilated by `margin` px (EDT <= margin)."""
    from scipy.ndimage import distance_transform_edt
    page_mask = np.asarray(page_mask, bool)
    if not page_mask.any():
        return np.zeros_like(page_mask)
    return distance_transform_edt(~page_mask) <= margin


def motion_energy(frames, masks):
    """e[t-1] = mean |grey_t − grey_{t−1}| inside masks[t], t = 1..N−1 (0 for an empty mask)."""
    g = [grey(f).astype(np.float32) for f in frames]
    out = []
    for t in range(1, len(g)):
        m = np.asarray(masks[t], bool)
        out.append(float(np.abs(g[t] - g[t - 1])[m].mean()) if m.any() else 0.0)
    return np.asarray(out)


def _pearson(x, y):
    x = x - x.mean()
    y = y - y.mean()
    d = np.sqrt((x * x).sum() * (y * y).sum())
    return float((x * y).sum() / d) if d > 0 else None


def best_lag(e_take, e_render, max_lag=MAX_LAG):
    """(lag, r): render(t + lag) best matches take(t)."""
    e_take = np.asarray(e_take, float)
    e_render = np.asarray(e_render, float)
    best = None
    for lag in sorted(range(-max_lag, max_lag + 1), key=lambda L: (abs(L), L)):
        ts = np.arange(len(e_take))
        tr = ts + lag
        ok = (tr >= 0) & (tr < len(e_render))
        if ok.sum() < 3:
            continue
        r = _pearson(e_take[ts[ok]], e_render[tr[ok]])
        if r is None:
            continue
        if best is None or r > best[1] + 1e-12:
            best = (lag, r)
    return best if best is not None else (None, None)


def lag_ok(lag, tol=LAG_TOL):
    return lag is not None and abs(lag) <= tol


def duration_ok(render_pts, times):
    """The render covers the take's analysis span (to within half a render frame)."""
    from seam.video import covers
    return covers(render_pts, times)


def lag_check(take, render, act_masks, floor=ENERGY_FLOOR, max_lag=MAX_LAG):
    """The time half of the gate, with its source recorded.

    Motion energy is measured inside the take's hand and prop masks, for the take and the render.
    Its mean runs over the active frames only: those whose masks are non-empty (energy index t-1
    holds frame t). A take with no active frame (the breath take: no hand, no prop) is not
    applicable, as is one whose mean energy over its active frames is below `floor`; the gate then
    rests on duration and the spatial test. Pearson r for the lag runs over the whole series.
    Returns {applicable, source, lag, r, energy_mean, n_active, floor, reason}."""
    active = [] if act_masks is None else [bool(np.asarray(m, bool).any()) for m in act_masks][1:len(take)]
    n_active = int(sum(active))
    if not n_active:
        return {"applicable": False, "source": None, "lag": None, "r": None, "energy_mean": None, "n_active": 0,
                "floor": floor, "reason": "no frame with a hand or prop mask: alignment rests on the 90 % rule"}
    masks = list(act_masks)
    e_t = motion_energy(take, masks)
    mean = float(e_t[np.asarray(active, bool)].mean())
    if mean < floor:
        return {"applicable": False, "source": "hands_props", "lag": None, "r": None, "energy_mean": mean,
                "n_active": n_active, "floor": floor,
                "reason": f"take motion energy {mean:.3g} is below the floor {floor} (grey levels per frame) "
                          f"over the {n_active} frames with a hand or prop mask"}
    lag, r = best_lag(e_t, motion_energy(render, masks), max_lag)
    return {"applicable": True, "source": "hands_props", "lag": lag, "r": r, "energy_mean": mean,
            "n_active": n_active, "floor": floor,
            "reason": None if lag is not None else "lag undefined: no variation in motion energy"}


def fit_similarity(render, take, exclude):
    """Similarity render -> take, or None when there are too few matches or inliers."""
    mask = np.where(np.asarray(exclude, bool), 0, 255).astype(np.uint8)
    orb = cv2.ORB_create(nfeatures=ORB_FEATURES, nlevels=ORB_LEVELS)
    gr = cv2.GaussianBlur(grey(render), (0, 0), PRE_BLUR)
    gt = cv2.GaussianBlur(grey(take), (0, 0), PRE_BLUR)
    kr, dr = orb.detectAndCompute(gr, mask)
    kt, dt = orb.detectAndCompute(gt, mask)
    if dr is None or dt is None:
        return None
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(dr, dt)
    if len(matches) < MIN_POINTS:
        return None
    matches = sorted(matches, key=lambda m: (m.queryIdx, m.trainIdx))
    src = _subpix(gr, [kr[m.queryIdx].pt for m in matches])
    dst = _subpix(gt, [kt[m.trainIdx].pt for m in matches])
    cv2.setRNGSeed(RNG_SEED)
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=RANSAC_PX,
                                         maxIters=RANSAC_ITERS, confidence=RANSAC_CONF,
                                         refineIters=REFINE_ITERS)
    if M is None or inl is None:
        return None
    inl = inl.ravel().astype(bool)
    if inl.sum() < MIN_POINTS:
        return None
    proj = src[inl] @ M[:, :2].T + M[:, 2]
    res = float(np.sqrt(np.mean(np.sum((proj - dst[inl]) ** 2, axis=1))))
    scale = float(np.hypot(M[0, 0], M[1, 0]))
    return Fit(M=M, scale=scale, residual=res, n_matches=len(matches), n_inliers=int(inl.sum()))


def _subpix(g, pts):
    """Refine keypoint positions to sub-pixel corners (11×11 window); ORB's own are whole pixels."""
    p = np.float32(pts).reshape(-1, 1, 2)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, SUBPIX_ITERS, SUBPIX_EPS)
    cv2.cornerSubPix(g, p, (SUBPIX_WIN, SUBPIX_WIN), (-1, -1), crit)
    return p.reshape(-1, 2)


def rho_from_residuals(residuals):
    r = [x for x in residuals if x is not None]
    if not r:
        return None
    return max(1.0, 2.0 * float(np.percentile(r, 99)))


def round_trip_rho(take_frames, rt_frames, exclude):
    """(ρ, residuals, n_failed): fit each 720p round-trip frame onto its take frame; n_failed
    counts the frames with no fit (None residuals). ρ is None when every fit failed."""
    res = []
    for rt, tk in zip(rt_frames, take_frames):
        f = fit_similarity(rt, tk, exclude)
        res.append(None if f is None else f.residual)
    return rho_from_residuals(res), res, sum(r is None for r in res)


def versions():
    from importlib.metadata import version
    return {p: version(p) for p in ("opencv-python", "numpy", "av")}


def frame_ok(fit, rho, scale_tol=SCALE_TOL):
    """False when there is no fit, or when ρ is undefined (every round-trip fit failed)."""
    return fit is not None and rho is not None and fit.residual <= rho and abs(fit.scale - 1.0) <= scale_tol


def gate(fits, rho, lag=None, min_frac=MIN_FRAC, lag_check=None, duration_ok=True):
    """{pass, lag, rho, frames_ok, ok, reason, lag_source, lag_applicable, lag_reason, ...}.

    lag_check (from lag_check()) supersedes lag. When it is not applicable, the gate rests on
    duration and the spatial test. reason is None when the render is aligned."""
    ok = [bool(frame_ok(f, rho)) for f in fits]
    frac = float(np.mean(ok)) if ok else 0.0
    applicable, source, lag_reason = True, None, None
    if lag_check is not None:
        lag, applicable, source = lag_check["lag"], lag_check["applicable"], lag_check["source"]
        if not applicable:
            lag_reason = f"not applicable: {lag_check['reason']}"
        elif lag_check["reason"]:
            lag_reason = lag_check["reason"]
    if rho is None:
        reason = "rho undefined: no round-trip fit"
    else:
        reasons = []
        if applicable and not lag_ok(lag):
            reasons.append("lag check failed")
        if not duration_ok:
            reasons.append("render shorter than the analysis span (duration)")
        if frac < min_frac:
            reasons.append("fewer than 90 % of frames pass")
        reason = "; ".join(reasons) or None
    return {"pass": reason is None, "lag": lag, "rho": rho, "frames_ok": frac, "ok": ok, "reason": reason,
            "lag_source": source, "lag_applicable": applicable, "lag_reason": lag_reason,
            "lag_energy_mean": lag_check["energy_mean"] if lag_check else None,
            "lag_n_active": lag_check.get("n_active") if lag_check else None, "duration_ok": bool(duration_ok),
            "params": PARAMS, "versions": versions()}


def warp(frame, M, size=SIZE):
    return cv2.warpAffine(np.asarray(frame), np.asarray(M, np.float64), tuple(size),
                          flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def cover(M, src_size=SIZE, size=SIZE):
    """(H, W) bool on the take grid: True where the warp samples inside the render frame, i.e. where the
    inverse transform of the pixel centre lands in [0, w-1] x [0, h-1] of the render. False on the
    border strip the warp fills by replicating the render's edge (call 126: it leaves R(t))."""
    M = np.asarray(M, np.float64)
    inv = cv2.invertAffineTransform(M)
    w, h = size
    xs, ys = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
    sx = inv[0, 0] * xs + inv[0, 1] * ys + inv[0, 2]
    sy = inv[1, 0] * xs + inv[1, 1] * ys + inv[1, 2]
    eps = 1e-6
    sw, sh = src_size
    return (sx >= -eps) & (sx <= sw - 1 + eps) & (sy >= -eps) & (sy <= sh - 1 + eps)


def warp_mask(mask, M, size=SIZE):
    out = cv2.warpAffine(np.asarray(mask, np.uint8), np.asarray(M, np.float64), tuple(size),
                         flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    return out.astype(bool)


# ---- runs over whole takes and renders (the files the pair writer and the assembler read) ------------------
RHO_SCHEMA = "p47-rho/1"
GATE_SCHEMA = "p47-gate/1"
FPS = 15


def lag_masks(take_masks):
    """The take's hand and prop tracks as one (n, H, W) stack: every object except the page and the homes.
    None when the take has none (the breath take: its lag check is not applicable)."""
    names = [k for k in sorted(take_masks) if k != "page" and not k.startswith("home_")]
    if not names:
        return None
    out = np.zeros(np.shape(take_masks[names[0]]), bool)
    for k in names:
        out |= np.asarray(take_masks[k], bool)
    return out


def _page(take_masks, n):
    if "page" not in take_masks:
        raise ValueError(f"the take masks have no page; they have {sorted(take_masks)}")
    page = np.asarray(take_masks["page"], bool)
    if len(page) != n:
        raise ValueError(f"the page track has {len(page)} frames, the take {n}")
    return page


def rho_record(take_frames, rt_frames, take_masks):
    """ρ for one take from its own 720p round trip, each frame fitted under its page exclusion."""
    n = len(take_frames)
    if len(rt_frames) != n:
        raise ValueError(f"the round trip has {len(rt_frames)} frames, the take {n}")
    page = _page(take_masks, n)
    res = []
    for i in range(n):
        f = fit_similarity(rt_frames[i], take_frames[i], exclusion(page[i]))
        res.append(None if f is None else f.residual)
    return {"schema": RHO_SCHEMA, "rho": rho_from_residuals(res), "residuals": res,
            "n_failed": sum(r is None for r in res), "n_frames": n, "params": PARAMS, "versions": versions()}


def span_frames(start_s, seconds, n_take):
    """(first take frame, frame count) of a trimmed input's span: the request's recorded trim (start_s, seconds)
    on the 15 fps grid. The compiler cuts frame-accurately from start_s, so render time 0 is take time start_s."""
    i0, n = int(round(float(start_s) * FPS)), int(round(float(seconds) * FPS))
    if i0 < 0 or n <= 0 or i0 + n > n_take:
        raise ValueError(f"span {start_s:g}+{seconds:g} s ({i0}+{n} frames) does not fit the take's {n_take} frames")
    return i0, n


def run_gate(take_frames, render_frames, render_pts, take_masks, rho, span=None):
    """The gate for one render on the take's analysis frames: per-frame fits (render frame i onto take frame i,
    both on the 15 fps grid), the lag check and the duration check. Adds the per-frame transforms (render ->
    take, 2x3, None where there is no fit), residuals, scales and inlier counts that the pair writer warps with.
    A render with fewer analysis frames than the take scores None on the missing frames (and fails duration).

    ``span`` = (first take frame, frame count): a render made from a trimmed input (the probe's and the no-op's
    first 10 s, a draft's window) is gated against that span of the take, its frames and masks, render frame j
    onto take frame first + j (review finding 2, call 135). The record carries the span."""
    take_frames = np.asarray(take_frames)
    if span is not None:
        i0, k = int(span[0]), int(span[1])
        if i0 < 0 or k <= 0 or i0 + k > len(take_frames):
            raise ValueError(f"span {i0}+{k} frames does not fit the take's {len(take_frames)} frames")
        take_frames = take_frames[i0:i0 + k]
        take_masks = {name: np.asarray(m)[i0:i0 + k] for name, m in take_masks.items()}
    n = len(take_frames)
    page = _page(take_masks, n)
    m = len(render_frames)
    fits = [fit_similarity(render_frames[i], take_frames[i], exclusion(page[i])) if i < m else None for i in range(n)]
    rend = render_frames[:n] if m >= n else np.concatenate([render_frames, np.repeat(render_frames[-1:], n - m, 0)])
    lc = lag_check(take_frames, rend, lag_masks(take_masks))
    g = gate(fits, rho, lag_check=lc, duration_ok=duration_ok(render_pts, np.arange(n) / FPS))
    g.update(transforms=[None if f is None else [[float(v) for v in row] for row in f.M] for f in fits],
             residuals=[None if f is None else f.residual for f in fits],
             scales=[None if f is None else f.scale for f in fits],
             inliers=[None if f is None else f.n_inliers for f in fits], lag_r=lc.get("r"))
    if span is not None:
        g["span"] = {"start_frame": int(span[0]), "frames": int(span[1])}
    return g


def stream_pts(path):
    """Presentation times (s, from the first) of a video's frames, from its packets (no decode)."""
    import av
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        pts = sorted(float(p.pts * s.time_base) for p in c.demux(s) if p.pts is not None)
    if not pts:
        raise ValueError(f"{path}: no video packets")
    return np.asarray(pts) - pts[0]


def _sha(p):
    from seam.util import sha256_file
    return sha256_file(p)


def main(argv=None):
    """python seam/align.py rho  --take T.analysis.mp4 --render-input T.render.mp4 --take-masks M.npz --out R.json
       python seam/align.py gate --render ID --video RENDER --take T.analysis.mp4 --take-masks M.npz --rho R.json --out G.json
           [--start S --seconds D]   a render from a trimmed input: gated against that span of the take (call 135)

    Both read every video onto the 1280x720 grid at 15 fps as the masks, the blind pick and the points are
    (seam.masks.analysis_frames), so frame i of the render is the frame its creature track holds at i."""
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from seam import masks
    ap = argparse.ArgumentParser(prog="python seam/align.py", description="ρ from the round trip; the alignment gate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rho")
    r.add_argument("--take", required=True, help="the take's 1280x720 analysis copy")
    r.add_argument("--render-input", required=True, help="the take's 1080p render input (re-encoded at 720p here)")
    r.add_argument("--take-masks", required=True)
    r.add_argument("--out", required=True)
    g = sub.add_parser("gate")
    g.add_argument("--render", required=True)
    g.add_argument("--video", required=True, help="the render, any 16:9 size")
    g.add_argument("--take", required=True)
    g.add_argument("--take-masks", required=True)
    g.add_argument("--rho", required=True, help="the take's p47-rho/1 file")
    g.add_argument("--start", type=float, help="a trimmed input's start, s (the request's trim.start_s)")
    g.add_argument("--seconds", type=float, help="a trimmed input's length, s (the request's trim.seconds)")
    g.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        take = masks.analysis_frames(a.take)
        _, tm = masks.load_masks(a.take_masks)
        if a.cmd == "rho":
            from seam import controls_inputs
            rt = controls_inputs.null_frames(a.render_input, (720,), n_frames=len(take))[720]
            rec = rho_record(take, rt, tm)
            rec["inputs"] = {"take_sha256": _sha(a.take), "render_input_sha256": _sha(a.render_input),
                             "take_masks_sha256": _sha(a.take_masks)}
        else:
            rr = json.loads(Path(a.rho).read_text())
            if rr.get("schema") != RHO_SCHEMA or rr.get("inputs", {}).get("take_sha256") != _sha(a.take):
                raise ValueError(f"{a.rho} is not this take's p47-rho/1 record")
            rend = masks.analysis_frames(a.video)
            if (a.start is None) != (a.seconds is None):
                raise ValueError("give --start and --seconds together (the request's trim), or neither")
            span = span_frames(a.start, a.seconds, len(take)) if a.seconds is not None else None
            rec = run_gate(take, rend, stream_pts(a.video), tm, rr["rho"], span=span)
            rec = {"schema": GATE_SCHEMA, "render": a.render, **rec,
                   "inputs": {"take_sha256": _sha(a.take), "video_sha256": _sha(a.video),
                              "take_masks_sha256": _sha(a.take_masks), "rho_sha256": _sha(a.rho)}}
    except (ValueError, OSError, KeyError) as e:
        print(f"align: refuse: {e}", file=sys.stderr)
        return 1
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1, sort_keys=True, allow_nan=False) + "\n")
    summary = {k: rec.get(k) for k in ("rho", "pass", "lag", "frames_ok", "reason", "n_failed")}
    print(json.dumps({k: v for k, v in summary.items() if v is not None or k in ("pass", "reason")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
