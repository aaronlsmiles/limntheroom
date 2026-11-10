"""Stays drawn (R0.3, descriptive): line density and moment alignment onto the scan.

moment_align puts the render's creature lines onto the scan's line-map grid by translation
(centroids) and isotropic scale (radius of gyration, g = sqrt(mean |p − c|²)), no rotation:
a turned pose stays as drift. It maps inversely, sampling the source at the nearest pixel for
each reference pixel, so an enlargement leaves no holes. The caller then takes
inkstab._chamfer(aligned, scan_lines).
"""
import numpy as np


def _moments(m):
    ys, xs = np.nonzero(m)
    c = np.array([ys.mean(), xs.mean()])
    g = float(np.sqrt(((ys - c[0]) ** 2 + (xs - c[1]) ** 2).mean()))
    return c, g


def moment_align(src, ref):
    """src lines (any grid) -> bool mask on ref.shape; None if either is empty or degenerate."""
    src = np.asarray(src, bool)
    ref = np.asarray(ref, bool)
    if not src.any() or not ref.any():
        return None
    cs, gs = _moments(src)
    cr, gr = _moments(ref)
    if gs == 0 or gr == 0:
        return None
    k = gs / gr                                  # ref px -> src px
    qy, qx = np.mgrid[0:ref.shape[0], 0:ref.shape[1]]
    py = np.rint((qy - cr[0]) * k + cs[0]).astype(np.int64)
    px = np.rint((qx - cr[1]) * k + cs[1]).astype(np.int64)
    ok = (py >= 0) & (py < src.shape[0]) & (px >= 0) & (px < src.shape[1])
    out = np.zeros(ref.shape, bool)
    out[ok] = src[py[ok], px[ok]]
    return out


def density(lines, mask):
    """Line pixels inside the mask / mask area; None for an empty mask."""
    mask = np.asarray(mask, bool)
    n = int(mask.sum())
    if n == 0:
        return None
    return float((np.asarray(lines, bool) & mask).sum() / n)
