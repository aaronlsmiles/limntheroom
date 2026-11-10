"""The A9.4 masked-chamfer frame rule (P46 plan, docs/p46/plan-2026-10-31.md), reused by P47.

P47 reads it with a = the render's line map (warped onto the take grid), b = the take's line
map at the same analysis time, and R = the measured region R(t) = ~A(t).

  - None if a or b is entirely empty (as the frozen inkstab._chamfer);
  - if a∩R is empty while b∩R is not, the one-sided term EDT(~a)[b∩R].mean(), so lines
    that vanish from the region count as drift instead of dropping out;
  - otherwise 0.5·(EDT(~b)[a∩R].mean() + EDT(~a)[b∩R].mean()).

The A9.4 text leaves two cases undefined (a mean over an empty set). They follow P46's masked
rule (`metrics/masked.py`, as P46 states A9.4 in docs/p46/a9-must-state.md): lines that appear in
R where b has none score the mirror one-sided term EDT(~b)[a∩R].mean(); both empty in R gives None.

Distance transforms are full-frame. With R all-true the value equals inkstab._chamfer bit
for bit (tests/test_maskrule.py). Only numpy and scipy: it imports in both venvs.
"""
import numpy as np


def frame_rule_dt(a, b, da, db, R):
    """One frame, with shared distance transforms: da = EDT(~b), db = EDT(~a)."""
    if not a.any() or not b.any():
        return None
    aR, bR = a & R, b & R
    has_a, has_b = bool(aR.any()), bool(bR.any())
    if has_a and has_b:
        return float(0.5 * (da[aR].mean() + db[bR].mean()))
    if has_b:                       # take lines vanished from R in the render
        return float(db[bR].mean())
    if has_a:                       # render lines appeared in R where the take has none
        return float(da[aR].mean())
    return None


def frame_rule(a, b, R):
    """Masked chamfer of render map a against take map b over region R (bool arrays)."""
    from scipy.ndimage import distance_transform_edt
    a = np.asarray(a, bool)
    b = np.asarray(b, bool)
    R = np.asarray(R, bool)
    if not a.any() or not b.any():
        return None
    return frame_rule_dt(a, b, distance_transform_edt(~b), distance_transform_edt(~a), R)


def edt_of(m):
    """EDT(~m), the distance of every pixel to m's nearest line pixel; None for an empty map
    (frame_rule_dt returns None before reading it)."""
    from scipy.ndimage import distance_transform_edt
    m = np.asarray(m, bool)
    return distance_transform_edt(~m) if m.any() else None
