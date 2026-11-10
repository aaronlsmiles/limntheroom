"""Torch cue: the onset of a bright spot (the torch's beam) and where it is aimed, from luminance.

Per analysis frame:
1. Luma, Gaussian-blurred (sigma 2). The baseline is the per-pixel median of the first
   ``baseline_frames`` frames (the torch is off at the start of every take; see the capture protocol).
2. Handheld takes shake, so the baseline is registered to each frame by phase correlation (translation)
   before differencing; otherwise page edges and ink lines would read as bright spots.
3. The spot is the largest connected component of ``(Y - baseline > delta) & (Y > min_luma)``.

Runs of frames with a spot are candidate torch events. A run counts only if it lasts at least
``min_on`` frames **and** is not a glint. A metal prop in shot can catch the beam and throw a small,
hard highlight that stays put on the object, so a glint is small (median area < ``glint_area`` px)
**and** stationary (it never moves more than ``min_travel`` px from where it appeared). The beam is
both larger and handheld, so it moves.

Evidence: ``aim`` (spot centroid at onset), ``path`` (every 3rd centroid), ``travel_px``,
``area_px`` (median), and ``lands_on``.

**Where light may count (hub call 132, Aaron, 9 Nov).** Given the take's masks, a lit pixel must lie on the
page (its track eroded by ``PAGE_ERODE_PX``) and off every hand and prop track (each dilated by
``TRACK_DILATE_PX``). On the printed terrazzo a hand or a glass over a dark chip is a luma rise as large as
a beam; on white paper only light is. ``lands_on`` is then the home with the largest mean lit share over
the run's first ``LANDS_FRAMES`` frames, if that share reaches ``LANDS_MIN_SHARE`` (``lands_share`` in the
evidence): a torch close to the page throws a wide pool whose centre can miss the creature it lights.
Without masks (unit fixtures only; the sheet requires them) the whole frame counts and ``lands_on`` is the
home box, if any, that contains the aim point.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from .sheet import make_event


# Thresholds (luma 0-255 on the 1280x720 analysis frames; frames at 15 fps).
BASELINE_FRAMES = 5    # the torch is off for the first 2 s of the take (capture protocol, t02), so 5 frames are unlit
LUMA_SIGMA = 2         # px: blur that removes sensor noise and fine texture before differencing
HIGHPASS_SIGMA = 6     # px: registration sees edges and lines, not the soft beam
DELTA = 40             # luma rise over the baseline that counts as lit
MIN_LUMA = 150         # absolute luma for a lit spot (shadows and dark desk never qualify)
MIN_SPOT_AREA = 4      # px: smaller components are noise
DEAD_ZONE_PX = 0.25    # registration shifts below this are treated as no shake
MAX_SHIFT_PX = 16      # px per frame: larger fitted shifts are distrusted (a hand-held phone shakes less)
MIN_ON = 5             # frames (0.33 s): the beam must stay on this long; glints flicker
GLINT_AREA = 150       # px: median area under which a still spot is a glint off a metal prop
MIN_TRAVEL = 12.0      # px: a glint never moves this far from where it appeared; the hand-held beam does
PAGE_ERODE_PX = 4      # px: a lit pixel lies at least this far inside the page track (call 132)
TRACK_DILATE_PX = 8    # px: and at least this far from every hand and prop track (call 132)
LANDS_FRAMES = 8       # frames (0.53 s): lands_on averages each home's lit share over the run's start
LANDS_MIN_SHARE = 0.05 # a home lit less than this on average is not landed on
NOT_TRACKS = ("page", "home_ink", "home_gold", "home_paper")   # every other track is a hand or a prop
HOMES = ("ink", "gold", "paper")


def _luma(frame: np.ndarray) -> np.ndarray:
    y = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY).astype(np.float32)
    return cv2.GaussianBlur(y, (0, 0), LUMA_SIGMA)


def _highpass(y: np.ndarray, sigma: float = HIGHPASS_SIGMA) -> np.ndarray:
    return y - cv2.GaussianBlur(y, (0, 0), sigma)


def _register(base: np.ndarray, y: np.ndarray, max_shift: float = MAX_SHIFT_PX) -> np.ndarray:
    """``base`` translated to line up with ``y``: phase correlation on Hann-windowed, high-passed luma,
    so edges and lines drive the fit and the soft beam does not. Shifts beyond ``max_shift`` are
    distrusted and ignored. NB: OpenCV 5.0.0.93's phaseCorrelate overwrites both inputs, so it gets copies."""
    win = cv2.createHanningWindow(base.shape[::-1], cv2.CV_32F)
    (dx, dy), _ = cv2.phaseCorrelate(_highpass(base).copy(), _highpass(y).copy(), win)
    if (abs(dx) < DEAD_ZONE_PX and abs(dy) < DEAD_ZONE_PX) or max(abs(dx), abs(dy)) > max_shift:
        return base
    m = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(base, m, base.shape[::-1], flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _lit(base, y, delta, min_luma, allowed=None):
    lit = (y - _register(base, y) > delta) & (y > min_luma)
    return lit if allowed is None else lit & allowed


def _largest(lit, min_area):
    n, _, stats, cents = cv2.connectedComponentsWithStats(lit.astype(np.uint8), connectivity=8)
    if n <= 1:
        return None
    k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    area = int(stats[k, cv2.CC_STAT_AREA])
    return (float(cents[k][0]), float(cents[k][1]), area) if area >= min_area else None


def region(masks: dict, n: int, erode: int = PAGE_ERODE_PX, dilate: int = TRACK_DILATE_PX):
    """Per frame (a generator): where a lit pixel may count, the page track eroded by ``erode`` px minus
    every hand and prop track dilated by ``dilate`` px. Homes are not obstacles: light lands on them."""
    if "page" not in masks:
        raise ValueError("torch: the take's page track is required (call 132)")
    k_e = np.ones((2 * erode + 1,) * 2, np.uint8)
    k_d = np.ones((2 * dilate + 1,) * 2, np.uint8)
    tracks = [m for name, m in sorted(masks.items()) if name not in NOT_TRACKS]
    for i in range(n):
        a = cv2.erode(np.asarray(masks["page"][i], np.uint8), k_e) > 0
        for m in tracks:
            a &= ~(cv2.dilate(np.asarray(m[i], np.uint8), k_d) > 0)
        yield a


def _shares(lit, masks):
    out = {}
    for h in HOMES:
        m = masks.get(f"home_{h}")
        if m is not None:
            area = int(m.sum())
            out[h] = float((lit & m).sum()) / area if area else 0.0
    return out


def _scan(frames, baseline_frames, delta, min_luma, min_area, masks=None):
    """(spots, shares): per frame the largest lit component, and, with masks, each home's lit share."""
    it = iter(frames)
    n_masks = len(masks["page"]) if masks is not None and "page" in masks else None
    allowed = region(masks, n_masks) if masks is not None else None
    head = []
    for f in it:
        head.append(_luma(f))
        if len(head) == baseline_frames:
            break
    if not head:
        return [], []
    base = np.median(np.stack(head), axis=0).astype(np.float32)
    sp, sh, i = [], [], 0

    def one(y):
        nonlocal i
        if allowed is not None and i >= n_masks:
            raise ValueError(f"torch: more frames than the masks' {n_masks}")
        a = next(allowed) if allowed is not None else None
        lit = _lit(base, y, delta, min_luma, a)
        sp.append(_largest(lit, min_area))
        sh.append(_shares(lit, {k: v[i] for k, v in masks.items() if k.startswith("home_")}) if masks else None)
        i += 1

    for y in head:
        one(y)
    del head
    for f in it:
        one(_luma(f))
    return sp, sh


def spots(frames, baseline_frames: int = BASELINE_FRAMES, delta: float = DELTA, min_luma: float = MIN_LUMA,
          min_area: int = MIN_SPOT_AREA, masks: dict | None = None) -> list[tuple[float, float, int] | None]:
    """Per frame: (cx, cy, area) of the largest bright component, or None. ``frames`` may be any
    iterable (a generator streams): only the first ``baseline_frames`` blurred lumas are buffered.
    With ``masks``, only pixels in ``region(masks)`` count (call 132)."""
    return _scan(frames, baseline_frames, delta, min_luma, min_area, masks)[0]


def _home_at(homes, x, y):
    for name, (hx, hy, hw, hh) in sorted((homes or {}).items()):
        if hx <= x < hx + hw and hy <= y < hy + hh:
            return name
    return None


def _lands_by_share(shares, i, j, frames=LANDS_FRAMES, min_share=LANDS_MIN_SHARE):
    """(home or None, {home: mean lit share}) over the run's first ``frames`` frames."""
    win = shares[i:min(j, i + frames)]
    mean = {h: round(float(np.mean([s[h] for s in win])), 3) for h in win[0]}
    best = max(mean, key=lambda h: (mean[h], h)) if mean else None
    return (best if best is not None and mean[best] >= min_share else None), mean


def detect(frames, fps: float, *, homes: dict | None = None, masks: dict | None = None, min_on: int = MIN_ON,
           glint_area: int = GLINT_AREA, min_travel: float = MIN_TRAVEL, baseline_frames: int = BASELINE_FRAMES,
           delta: float = DELTA, min_luma: float = MIN_LUMA, min_area: int = MIN_SPOT_AREA) -> list[dict]:
    """Torch events. With the take's ``masks`` (page, homes, hand and prop tracks) light counts only in
    ``region(masks)`` and ``lands_on`` goes by lit share (call 132); ``homes`` boxes are then unused."""
    sp, sh = _scan(frames, baseline_frames, delta, min_luma, min_area, masks)
    n, out, i = len(sp), [], 0
    while i < n:
        if sp[i] is None:
            i += 1
            continue
        j = i
        while j < n and sp[j] is not None:
            j += 1
        run = sp[i:j]
        x0, y0 = run[0][0], run[0][1]
        travel = max(math.dist((x0, y0), (x, y)) for x, y, _ in run)
        area = float(np.median([a for _, _, a in run]))
        glint = area < glint_area and travel < min_travel
        if len(run) >= min_on and not glint:
            share = None
            if masks is not None:
                lands, share = _lands_by_share(sh, i, j)
            else:
                lands = _home_at(homes, x0, y0)
            what = f"the torch's beam lands on the {lands} drawing" if lands else "a torch's beam comes on"
            out.append(make_event(
                t=i / fps, t_end=None if j >= n else j / fps, cue="light", what=what, source="detector:torch",
                evidence={"onset_frame": i, "off_frame": None if j >= n else j,
                          "aim": [round(x0, 1), round(y0, 1)],
                          "path": [[k + i, round(x, 1), round(y, 1)] for k, (x, y, _) in enumerate(run) if k % 3 == 0],
                          "travel_px": round(travel, 1), "area_px": round(area, 1), "lands_on": lands,
                          **({"lands_share": share, "region": f"page eroded {PAGE_ERODE_PX} px, hand and prop "
                              f"tracks dilated {TRACK_DILATE_PX} px"} if share is not None else {})}))
        i = j
    return out
