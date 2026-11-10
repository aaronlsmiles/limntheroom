"""Props cue: a prop arrives (onset) and comes to rest (settle), read from its take mask over time.

- **Onset:** the first frame of a run of ``on_frames`` frames with mask area >= ``min_area``.
- **Settle:** the first frame of a run where, for ``settle_frames`` consecutive steps, the area changes
  by at most ``area_tol`` (relative) and the centroid moves at most ``move_px`` per frame. The event
  time ``t`` is the settle frame: the moment the prop is set down and available to the creature.
- One event per appearance. A dip while settled (a hand passing in front) is not a new appearance;
  a new one needs the mask to vanish for ``off_frames`` frames first.
"""
from __future__ import annotations

import math

import numpy as np

from .sheet import make_event

# Defaults, in 15 fps analysis frames on the 1280x720 grid.
MIN_AREA = 50          # px: smaller is mask noise (a pen nib alone is several hundred px at 720p)
ON_FRAMES = 3          # 0.2 s present before a prop counts as arrived
OFF_FRAMES = 5         # 0.33 s gone before a new appearance can start (a passing hand is not one)
SETTLE_FRAMES = 5      # 0.33 s of stillness = set down (the protocol has the hand let go, then withdraw)
AREA_TOL = 0.05        # relative area change per frame still counted as still (SAM edge jitter)
MOVE_PX = 3.0          # centroid motion per frame still counted as still


def areas_centroids(mask_stack) -> tuple[list[float], list[tuple[float, float] | None]]:
    """Per-frame area (pixels) and centroid (x, y), or None for an empty frame."""
    areas, cents = [], []
    for m in np.asarray(mask_stack, bool):
        ys, xs = np.nonzero(m)
        areas.append(float(xs.size))
        cents.append((float(xs.mean()), float(ys.mean())) if xs.size else None)
    return areas, cents


def _steady(a0, a1, c0, c1, area_tol, move_px, min_area) -> bool:
    if a0 < min_area or a1 < min_area or c0 is None or c1 is None:
        return False
    return abs(a1 - a0) / a0 <= area_tol and math.dist(c0, c1) <= move_px


def detect(areas, centroids, *, fps: float, obj: str, cue: str, min_area: float = MIN_AREA,
           on_frames: int = ON_FRAMES, off_frames: int = OFF_FRAMES, settle_frames: int = SETTLE_FRAMES,
           area_tol: float = AREA_TOL, move_px: float = MOVE_PX) -> list[dict]:
    n = len(areas)
    present = [a >= min_area for a in areas]
    out, i = [], 0
    while i < n:
        if not all(present[i:i + on_frames]) or i + on_frames > n:
            i += 1
            continue
        onset, settle, j = i, None, i + 1
        while j + settle_frames <= n:
            if all(_steady(areas[k - 1], areas[k], centroids[k - 1], centroids[k], area_tol, move_px, min_area)
                   for k in range(j, j + settle_frames)):
                settle = j - 1
                break
            j += 1
        if settle is None:
            break
        out.append(make_event(
            t=settle / fps, t_end=None, cue=cue, what=f"the {obj} is set down", source="detector:props",
            evidence={"object": obj, "onset_frame": onset, "settle_frame": settle,
                      "area_px": round(float(areas[settle]), 1),
                      "centroid": [round(c, 1) for c in centroids[settle]]}))
        # the next appearance needs the mask gone for off_frames frames
        k, gone = settle, 0
        while k < n and gone < off_frames:
            gone = gone + 1 if not present[k] else 0
            k += 1
        i = k
    return out


def detect_masks(mask_stack, *, fps: float, obj: str, cue: str, **kw) -> list[dict]:
    areas, cents = areas_centroids(mask_stack)
    return detect(areas, cents, fps=fps, obj=obj, cue=cue, **kw)
