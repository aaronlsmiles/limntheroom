import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from skimage.morphology import binary_dilation, disk

from seam import cells, regions

INKSTAB = Path("/Users/aaron/projects/stilldrawn/metrics/inkstab.py")
H, W = 720, 1280


def vlines(shift=0, spacing=16, h=H, w=W):
    m = np.zeros((h, w), bool)
    m[:, 10 + shift::spacing] = True
    return m


def test_grid_shape():
    assert cells.grid_shape() == (23, 40)


def test_identical_maps_all_kept():
    L = vlines()
    codes, iou = cells.classify(L, L, np.ones((H, W), bool), kappa=0.8)
    assert codes.shape == (23, 40)
    assert (codes == cells.KEPT).all()           # every cell holds two lines
    assert np.nanmin(iou) == 1.0


def test_three_px_shift_redrawn():
    codes, iou = cells.classify(vlines(), vlines(3), np.ones((H, W), bool), kappa=0.8)
    assert (codes[iou < 0.4] == cells.REDRAWN).all() and (codes == cells.REDRAWN).mean() > 0.9


def test_uncovered_cells_have_no_verdict_and_are_not_creature():
    # the warp did not cover the last 8 columns: they are out of R(t) but are not the creature's
    cover = np.ones((H, W), bool)
    cover[:, W - 8:] = False
    R = cover.copy()
    R[100:140, 100:140] = False                   # the creature's region A(t)
    codes, iou = cells.classify(vlines(), vlines(3), R, kappa=0.8, cover=cover)
    assert (codes[:, -1] == cells.NONE).all() and np.isnan(iou[:, -1]).all()
    assert (codes[3:5, 3:5] == cells.CREATURE).all()
    assert (codes[:, :-1][codes[:, :-1] != cells.CREATURE] == cells.REDRAWN).all()
    assert not np.isnan(cells.room_ious(iou, codes)).any() and len(cells.room_ious(iou, codes)) == 23 * 39 - 4
    # without cover the same R would call the strip creature
    old, _ = cells.classify(vlines(), vlines(3), R, kappa=0.8)
    assert (old[:, -1] == cells.CREATURE).all()


def test_sparse_cells_have_no_verdict():
    Lt = np.zeros((H, W), bool)
    Lt[5, 0:19] = True                            # 19 px in cell (0, 0)
    Lr = np.zeros((H, W), bool)
    Lr[6, 0:19] = True
    codes, iou = cells.classify(Lt, Lr, np.ones((H, W), bool), kappa=0.8)
    assert codes[0, 0] == cells.NONE and np.isnan(iou[0, 0])
    Lt[5, 19] = True                              # 20 px in the take: scored
    codes, iou = cells.classify(Lt, Lr, np.ones((H, W), bool), kappa=0.5)
    assert codes[0, 0] == cells.KEPT and not np.isnan(iou[0, 0])


def test_cell_touching_outside_R_is_creature():
    R = np.ones((H, W), bool)
    R[40, 70] = False                             # one pixel of cell (1, 2)
    codes, _ = cells.classify(vlines(), vlines(), R, kappa=0.8)
    assert codes[1, 2] == cells.CREATURE and (codes == cells.CREATURE).sum() == 1


def test_between_thresholds_is_none():
    # a shift whose IoU lands between kappa/2 and kappa
    codes, iou = cells.classify(vlines(), vlines(1), np.ones((H, W), bool), kappa=0.9)
    v = iou[0, 0]
    assert 0.45 <= v < 0.9 and codes[0, 0] == cells.NONE


def test_invalid_frame_all_none():
    assert (cells.empty_codes() == cells.NONE).all()


@pytest.mark.skipif(not INKSTAB.exists(), reason="no stilldrawn checkout")
def test_single_cell_equals_tol_iou():
    spec = importlib.util.spec_from_file_location("p47_inkstab_cells", INKSTAB)
    inkstab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inkstab)
    rng = np.random.default_rng(4)
    for _ in range(10):
        a, b = rng.random((64, 64)) < 0.03, rng.random((64, 64)) < 0.03
        _, iou = cells.classify(b, a, np.ones((64, 64), bool), kappa=0.5, cell=64, min_px=1)
        assert iou[0, 0] == inkstab._tol_iou(a, b, 2)


def test_pack_round_trip():
    rng = np.random.default_rng(0)
    seq = rng.integers(0, 4, size=(7, 23, 40)).astype(np.uint8)
    data = cells.pack(seq)
    assert len(data) == 7 * 230
    assert np.array_equal(cells.unpack(data, 23, 40), seq)
    assert data[0] == (seq[0, 0, 0] | seq[0, 0, 1] << 2 | seq[0, 0, 2] << 4 | seq[0, 0, 3] << 6)
    odd = rng.integers(0, 4, size=(3, 3, 3)).astype(np.uint8)   # 9 cells -> 3 bytes per frame
    assert len(cells.pack(odd)) == 9 and np.array_equal(cells.unpack(cells.pack(odd), 3, 3), odd)


def test_room_ious():
    codes = np.array([[cells.KEPT, cells.CREATURE], [cells.NONE, cells.REDRAWN]], np.uint8)
    iou = np.array([[0.9, np.nan], [0.6, 0.1]])
    assert cells.room_ious(iou, codes) == [0.9, 0.6, 0.1]


def test_dilate_matches_disk():
    m = np.zeros((101, 101), bool)
    m[50, 50] = True
    m[10, 80] = True
    for r in (2, 8, 24):
        assert np.array_equal(regions.dilate(m, r), binary_dilation(m, disk(r)))
    assert not regions.dilate(np.zeros((5, 5), bool), 3).any()


def test_measured_region_and_contact():
    creature = np.zeros((100, 100), bool)
    creature[40:50, 40:50] = True
    home = np.zeros((100, 100), bool)
    home[0:5, 0:5] = True
    R = regions.measured_region(creature, home, m=10)
    assert not R[45, 45] and not R[45, 59] and R[45, 61] and not R[2, 2] and R[50, 0]
    touched = np.zeros((100, 100), bool)
    touched[45, 57] = True                       # 8 px from the creature edge at x=49
    hand = np.zeros((100, 100), bool)
    assert regions.contact(creature, touched, hand, d=8)
    assert not regions.contact(creature, touched, hand, d=7)
    assert regions.contact(creature, np.zeros_like(hand), creature, d=0)


def test_unpack_checks_length_and_cell_sums_is_public():
    data = cells.pack(np.zeros((2, 23, 40), np.uint8))
    with pytest.raises(ValueError):
        cells.unpack(data[:-1], 23, 40)
    assert cells.cell_sums(np.ones((64, 64), bool), 32).tolist() == [[1024, 1024], [1024, 1024]]
