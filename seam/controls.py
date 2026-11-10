"""The registered controls (R0.3), as functions over line maps, so the lines job can run them on
real takes with the frozen extractor and the tests can run them with synthetic extractors.

Paste. The acting creature's scan crop is alpha-composited onto the take at its planned
contact spot through the cue window (the room untouched, no re-encode, so the control isolates
creature lines leaking across the margin). For each m in (32, 48, 64):
R_m(t) = ~dilate(paste_mask(t) ∪ home, m); D(t) = frame rule (composite vs take) in R_m;
D0(t) = frame rule (codec null vs take) in R_m; threshold = P95 (linear) of D0's non-None
values; pass iff at least 95 % of the frames with D not None have D ≤ threshold. m is the
smallest that passes; if none passes, H is registered as not testable. The caller passes only
the cue-window frames. The codec null is the take re-encoded at the render model's own output
resolution (1080p for aleph2, which keeps the input resolution; 720p for kling_4, seedance2_5
and gemini_omni_flash_1.1). At least 20 frames must be scored, else H is not testable.

Shift. A 64×64 room patch at a cell-aligned origin has its content moved by (3, 3) px
(3 px on each axis, so strokes in every direction are displaced). The patch must have no
dominant stroke orientation: structure-tensor coherence over its line pixels below 0.5. A frame
passes if all four of the patch's cells are redrawn under κ_keep; the control passes iff at
least 90 % of the frames pass (a cell with no verdict counts as a failure).
"""
import numpy as np

from seam import cells, regions
from seam.maskrule import edt_of, frame_rule, frame_rule_dt

M_CHOICES = (32, 48, 64)
MIN_SCORED = 20          # the paste control needs at least 20 scored frames, else "not testable"
# The paste control's codec null is encoded at the render's own output resolution (call 64):
# aleph2 keeps the input resolution (the 1080p render input); the others return 720p.
NULL_HEIGHT = {"aleph2": 1080, "kling_4": 720, "seedance2_5": 720, "gemini_omni_flash_1.1": 720}
PASTE_NEED = 0.95
SHIFT_NEED = 0.90
PATCH = 64
COHERENCE_MAX = 0.5      # patches whose strokes share one orientation are rejected (call 61)
COHERENCE_SIGMA = 1.0
SHIFT = (3, 3)           # diagonal, so strokes in every direction are displaced (call 57)


def paste(frames, rgba, xy, window):
    """(composited frames, paste masks); rgba is placed with its top-left at xy = (x, y)."""
    frames = np.asarray(frames)
    out = frames.copy()
    h, w = frames.shape[1:3]
    x, y = xy
    ph, pw = rgba.shape[:2]
    alpha = rgba[..., 3].astype(np.float32) / 255.0
    y0, y1, x0, x1 = max(y, 0), min(y + ph, h), max(x, 0), min(x + pw, w)
    sub_a = alpha[y0 - y:y1 - y, x0 - x:x1 - x, None]
    sub_c = rgba[y0 - y:y1 - y, x0 - x:x1 - x, :3].astype(np.float32)
    masks = np.zeros(frames.shape[:3], bool)
    for i in window:
        region = out[i, y0:y1, x0:x1].astype(np.float32)
        out[i, y0:y1, x0:x1] = np.clip(np.rint(sub_a * sub_c + (1 - sub_a) * region), 0, 255).astype(np.uint8)
        masks[i, y0:y1, x0:x1] = rgba[y0 - y:y1 - y, x0 - x:x1 - x, 3] > 127
    return out, masks


def d_series(maps_a, maps_b, region_seq):
    return [frame_rule(a, b, R) for a, b, R in zip(maps_a, maps_b, region_seq)]


def p95(xs):
    v = [x for x in xs if x is not None]
    return float(np.percentile(v, 95)) if v else None


def null_height(model):
    try:
        return NULL_HEIGHT[model]
    except KeyError:
        raise ValueError(f"no codec-null resolution registered for model {model!r}") from None


def paste_control(take_maps, paste_maps, null_maps, paste_masks, home, model, m_choices=M_CHOICES,
                  need=PASTE_NEED, min_scored=MIN_SCORED):
    """null_maps must come from the take re-encoded at null_height(model) (seam.video.reencode),
    decoded onto the analysis grid."""
    h = null_height(model)
    per_m = {}
    chosen = None
    # each frame's distance transforms once, shared across the margins
    et = [edt_of(m) for m in take_maps]
    ep = [edt_of(m) for m in paste_maps]
    e0 = [edt_of(m) for m in null_maps]
    from scipy.ndimage import distance_transform_edt
    ea = [distance_transform_edt(~(np.asarray(pm, bool) | np.asarray(home, bool)))
          if (np.asarray(pm, bool) | np.asarray(home, bool)).any() else None for pm in paste_masks]
    for m in m_choices:
        R = [~(d <= m) if d is not None else np.ones(np.shape(home), bool) for d in ea]
        D = [frame_rule_dt(a, b, eb, eaa, r) for a, b, eb, eaa, r in zip(paste_maps, take_maps, et, ep, R)]
        D0 = [frame_rule_dt(a, b, eb, eaa, r) for a, b, eb, eaa, r in zip(null_maps, take_maps, et, e0, R)]
        thr = p95(D0)
        scored = [d for d in D if d is not None]
        frac = float(np.mean([d <= thr for d in scored])) if (scored and thr is not None) else 0.0
        ok = bool(len(scored) >= min_scored and thr is not None and frac >= need)
        per_m[m] = {"threshold": thr, "frac": frac, "n_scored": len(scored), "pass": ok}
        if ok and chosen is None:
            chosen = m
    reason = None
    if chosen is None:
        if all(v["n_scored"] < min_scored for v in per_m.values()):
            reason = f"fewer than {min_scored} scored frames"
        else:
            reason = "no margin passes"
    return {"m": chosen, "testable": chosen is not None, "reason": reason, "need": need,
            "min_scored": min_scored, "model": model, "null_height": h, "per_m": per_m}


def shift_patch(frames, xy, size=PATCH, dx=SHIFT[0], dy=SHIFT[1]):
    """Content of the size×size patch at xy moved by (dx, dy): out[y:y+s, x:x+s] = in[y-dy:..., x-dx:...]."""
    frames = np.asarray(frames)
    h, w = frames.shape[1:3]
    x, y = xy
    if min(x, y, x - dx, y - dy) < 0 or max(x, x - dx) + size > w or max(y, y - dy) + size > h:
        raise ValueError(f"shift patch at {xy} (size {size}, move {dx},{dy}) leaves the {w}x{h} frame")
    out = frames.copy()
    out[:, y:y + size, x:x + size] = frames[:, y - dy:y - dy + size, x - dx:x - dx + size]
    return out


def _tensor_cells(maps, cell=cells.CELL, sigma=COHERENCE_SIGMA):
    """Per-cell sums of the structure tensor (Jxx, Jyy, Jxy) over the line pixels (dilated by
    disk(2), so both flanks of a thin line count), summed over frames. Gradients are Sobel on the
    line map smoothed by a Gaussian of sigma 1 px, computed on the full frame (no patch-edge effects)."""
    from scipy.ndimage import gaussian_filter, sobel
    acc = None
    for m in maps:
        g = gaussian_filter(np.asarray(m, np.float64), sigma)
        gx, gy = sobel(g, axis=1), sobel(g, axis=0)
        w = cells.tol_dilate(m)
        parts = [cells.cell_sums_f(gx * gx * w, cell), cells.cell_sums_f(gy * gy * w, cell),
                 cells.cell_sums_f(gx * gy * w, cell)]
        acc = parts if acc is None else [a + p for a, p in zip(acc, parts)]
    return acc


def _coherence_from(jxx, jyy, jxy):
    tr = jxx + jyy
    if tr <= 0:
        return None
    return float(np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / tr)


def coherence(maps, xy, size=PATCH, cell=cells.CELL):
    """Structure-tensor coherence over the patch's line pixels, all frames together: 0 = no
    dominant orientation, 1 = one orientation. None if the patch holds no line structure."""
    jxx, jyy, jxy = _tensor_cells(maps, cell)
    x, y = xy
    r0, c0, k = y // cell, x // cell, size // cell
    return _coherence_from(*(j[r0:r0 + k, c0:c0 + k].sum() for j in (jxx, jyy, jxy)))


def _patch_cells(xy, size=PATCH, cell=cells.CELL):
    x, y = xy
    return [(r, c) for r in range(y // cell, (y + size) // cell) for c in range(x // cell, (x + size) // cell)]


def choose_shift_patch(maps, region_seq, cell=cells.CELL, min_px=cells.MIN_PX, size=PATCH):
    """Cell-aligned origin of the 2×2-cell block fully inside R in every frame, with at least
    min_px line pixels per cell in every frame, structure-tensor coherence below 0.5 (no dominant
    stroke orientation, so a 45° hatch or a set of parallel strokes is rejected) and the most line
    pixels; first in row-major order on a tie. None if there is none."""
    h, w = maps[0].shape
    k = size // cell
    sums = np.stack([cells.cell_sums(m, cell) for m in maps])               # (n, rows, cols)
    outside = np.stack([cells.cell_sums(~R, cell) for R in region_seq]) > 0
    rows, cols = sums.shape[1:]
    jxx, jyy, jxy = _tensor_cells(maps, cell)
    best = None
    for r in range(rows - k + 1):
        for c in range(cols - k + 1):
            if (r + k) * cell > h or (c + k) * cell > w or (c * cell) < SHIFT[0] or (r * cell) < SHIFT[1]:
                continue
            block = sums[:, r:r + k, c:c + k]
            if outside[:, r:r + k, c:c + k].any() or (block < min_px).any():
                continue
            coh = _coherence_from(*(j[r:r + k, c:c + k].sum() for j in (jxx, jyy, jxy)))
            if coh is None or coh >= COHERENCE_MAX:
                continue
            total = int(block.sum())
            if best is None or total > best[0]:
                best = (total, (c * cell, r * cell))
    return None if best is None else best[1]


def shift_control(take_maps, shifted_maps, region_seq, xy, kappa, need=SHIFT_NEED):
    pc = _patch_cells(xy)
    per = []
    for Lt, Lr, R in zip(take_maps, shifted_maps, region_seq):
        codes, _ = cells.classify(Lt, Lr, R, kappa)
        per.append(all(codes[r, c] == cells.REDRAWN for r, c in pc))
    frac = float(np.mean(per)) if per else 0.0
    return {"xy": list(xy), "kappa": kappa, "coherence": coherence(take_maps, xy), "frac": frac, "pass": bool(per and frac >= need), "per_frame": per}


def move_frames(frames, dx=SHIFT[0], dy=SHIFT[1]):
    """(moved, cover): every frame's content moved by (dx, dy), out[y, x] = in[y - dy, x - dx] (call 133). The top
    dy rows and left dx columns have no source: they keep their own pixels and are marked uncovered."""
    frames = np.asarray(frames)
    out = frames.copy()
    out[:, dy:, dx:] = frames[:, :frames.shape[1] - dy, :frames.shape[2] - dx]
    cover = np.zeros(frames.shape[1:3], bool)
    cover[dy:, dx:] = True
    return out, cover


def room_shift_share(take_maps, moved_maps, region_seq, cover, kappa):
    """Descriptive, beside the registered shift control (call 133): the shares of room cells (§11) classed redrawn,
    kept and no verdict when the take is compared with itself moved by (3, 3), pooled over frames, under each
    frame's region minus the pixels the move left uncovered. It says how much of the room a 3 px move can show as
    redrawn at this κ; the shift control's one patch can fail where most of the room would not."""
    cover = np.asarray(cover, bool)
    counts = {cells.KEPT: 0, cells.REDRAWN: 0, cells.NONE: 0}
    per_frame = []
    for Lt, Lm, R in zip(take_maps, moved_maps, region_seq):
        codes, iou = cells.classify(Lt, Lm, np.asarray(R, bool) & cover, kappa, cover=cover)
        room = ~np.isnan(iou) & (codes != cells.CREATURE)
        c = codes[room]
        for k in counts:
            counts[k] += int((c == k).sum())
        per_frame.append(float((c == cells.REDRAWN).mean()) if c.size else None)
    n = sum(counts.values())
    share = (lambda k: counts[k] / n) if n else (lambda k: None)
    return {"kappa": kappa, "move": [SHIFT[0], SHIFT[1]], "n_room_cells": n, "redrawn": share(cells.REDRAWN),
            "kept": share(cells.KEPT), "none": share(cells.NONE), "per_frame_redrawn": per_frame}


def kappa_keep(ious):
    v = [x for x in ious if x is not None and not np.isnan(x)]
    return float(np.percentile(v, 1)) if v else None


def codec_null(take_maps, null_maps, homes, m, noop=False):
    """The registered codec-null floors for one take at one resolution (§9), from line maps.

    homes: {name: (H, W) bool}, each resting drawing's static home mask. For each home, D0(t) = the frame rule,
    codec null against take, in R0 = ~dilate(home, m), over every analysis frame; reported as the median and the
    linear 95th percentile of the non-None values. With ``noop`` (the glass take), κ_codec = the linear 1st
    percentile of the room-cell tolerant IoUs (§11) of the null against the take under R_noop = ~dilate(the union
    of the homes, m), every frame scored (no warp, so every pixel is covered)."""
    if m not in M_CHOICES:
        raise ValueError(f"m must be one of {M_CHOICES}, got {m!r}")
    if not homes:
        raise ValueError("no home masks")
    et = [edt_of(t) for t in take_maps]
    e0 = [edt_of(z) for z in null_maps]
    out = {"m": int(m), "n_frames": len(take_maps), "homes": {}}
    for name, home in sorted(homes.items()):
        R = ~regions.dilate(np.asarray(home, bool), m)
        d0 = [frame_rule_dt(z, t, a, b, R) for z, t, a, b in zip(null_maps, take_maps, et, e0)]
        v = [x for x in d0 if x is not None]
        out["homes"][name] = {"median": float(np.median(v)) if v else None,
                              "p95": float(np.percentile(v, 95)) if v else None, "n": len(v), "D0": d0}
    if noop:
        union = np.zeros(np.shape(next(iter(homes.values()))), bool)
        for h in homes.values():
            union |= np.asarray(h, bool)
        R = ~regions.dilate(union, m)
        ious = []
        for t, z in zip(take_maps, null_maps):
            codes, iou = cells.classify(t, z, R, 1.0)
            ious.extend(cells.room_ious(iou, codes))
        out["kappa_codec"] = float(np.percentile(ious, 1)) if ious else None
        out["n_room_cells"] = len(ious)
        out["noop_homes"] = sorted(homes)
    return out
