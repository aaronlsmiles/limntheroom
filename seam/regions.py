"""Regions on the take grid (R0.3).

A(t) = dilate(creature_render(t) ∪ home, m), R(t) = ~A(t), with m from the paste control.
Contact c(t): dilate(creature_render(t), d) ∩ (touched object ∪ hand) ≠ ∅, d = 8 px.

Dilation by a Euclidean disk of radius r is computed as EDT(~mask) <= r, which equals
skimage binary_dilation(mask, disk(r)) (tested), and is fast at r = 64.
"""
import numpy as np

CONTACT_PX = 8
PROXIMITY_PX = 24


def dilate(mask, r):
    from scipy.ndimage import distance_transform_edt
    mask = np.asarray(mask, bool)
    if not mask.any():
        return np.zeros_like(mask)
    if r <= 0:
        return mask.copy()
    return distance_transform_edt(~mask) <= r


def measured_region(creature, home, m, at_home=False):
    """R(t). ``at_home``: a frame before the render mask's prompt frame, where the creature is still its
    drawing at home, so A(t) is the dilated home alone (the forward-only SAM track is empty there)."""
    a = np.asarray(home, bool) if at_home else np.asarray(creature, bool) | np.asarray(home, bool)
    return ~dilate(a, m)


def contact(creature, touched, hand, d=CONTACT_PX):
    other = np.asarray(touched, bool) | np.asarray(hand, bool)
    return bool((dilate(creature, d) & other).any())
