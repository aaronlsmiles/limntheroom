"""Seam cells (R0.3) and the 2-bit seam file (p47-measure/1).

Cells are 32×32 px on the 1280×720 take grid: 40 columns × 23 rows, the bottom row 16 px tall.
Per cell and analysis frame:
  creature (3)  any pixel of the cell is in A(t), the creature's region (outside R(t) but
                covered by the warp);
  none (0)      any pixel of the cell is one the warp did not cover (the border strip filled
                by replicating the render's edge; call 126), or fewer than 20 line pixels in
                both the take and the render map (undilated, inside the cell), or the frame
                failed the alignment gate, or the tolerant IoU lies in [κ_keep/2, κ_keep);
  kept (1)      tolerant IoU ≥ κ_keep;
  redrawn (2)   tolerant IoU < κ_keep/2.
Tolerant IoU at τ = 2 px (StillDrawn's iou_tolerance_px): both full frames are dilated by
disk(τ) as in inkstab._tol_iou, then intersection and union are counted inside the cell.

Seam file: per frame, cells in row-major order, four per byte, c0 | c1<<2 | c2<<4 | c3<<6,
each frame padded to a whole byte; no header (cols and rows travel in p47-measure/1).
"""
import numpy as np

CELL = 32
TAU = 2
MIN_PX = 20
NONE, KEPT, REDRAWN, CREATURE = 0, 1, 2, 3
SIZE_HW = (720, 1280)


def grid_shape(h=SIZE_HW[0], w=SIZE_HW[1], cell=CELL):
    return (-(-h // cell), -(-w // cell))


def empty_codes(h=SIZE_HW[0], w=SIZE_HW[1], cell=CELL):
    return np.zeros(grid_shape(h, w, cell), np.uint8)


def tol_dilate(m, tau=TAU):
    from skimage.morphology import binary_dilation, disk
    return binary_dilation(np.asarray(m, bool), disk(tau))


def cell_sums(m, cell=CELL):
    """Sum of a bool map per cell (the last row/column may be partial)."""
    h, w = m.shape
    rows, cols = grid_shape(h, w, cell)
    pad = np.zeros((rows * cell, cols * cell), np.int64)
    pad[:h, :w] = m
    return pad.reshape(rows, cell, cols, cell).sum(axis=(1, 3))


def cell_sums_f(v, cell=CELL):
    """Float sums per cell (the last row/column may be partial)."""
    h, w = v.shape
    rows, cols = grid_shape(h, w, cell)
    pad = np.zeros((rows * cell, cols * cell), np.float64)
    pad[:h, :w] = v
    return pad.reshape(rows, cell, cols, cell).sum(axis=(1, 3))


def classify(Lt, Lr, R, kappa, tau=TAU, min_px=MIN_PX, cell=CELL, dt=None, dr=None, cover=None):
    """(codes uint8 (rows, cols), iou float (rows, cols), NaN where unscored).

    Lt = take line map, Lr = render line map, R = measured region, all bool on one grid.
    cover: the pixels the warp covered (None: all); R must exclude the rest. A cell with an
    uncovered pixel and none of A(t) has no verdict and is never a room cell.
    dt, dr: the maps already dilated by disk(tau) (tol_dilate), to share across calls."""
    Lt = np.asarray(Lt, bool)
    Lr = np.asarray(Lr, bool)
    R = np.asarray(R, bool)
    cover = np.ones(R.shape, bool) if cover is None else np.asarray(cover, bool)
    h, w = Lt.shape
    outside = cell_sums(~R & cover, cell) > 0
    uncovered = cell_sums(~cover, cell) > 0
    nt, nr = cell_sums(Lt, cell), cell_sums(Lr, cell)
    dt = tol_dilate(Lt, tau) if dt is None else dt
    dr = tol_dilate(Lr, tau) if dr is None else dr
    inter, union = cell_sums(dt & dr, cell), cell_sums(dt | dr, cell)
    scored = ~outside & ~uncovered & ((nt >= min_px) | (nr >= min_px)) & (union > 0)
    iou = np.full(inter.shape, np.nan)
    iou[scored] = inter[scored] / union[scored]
    codes = np.full(inter.shape, NONE, np.uint8)
    codes[scored & (iou >= kappa)] = KEPT
    codes[scored & (iou < kappa / 2)] = REDRAWN
    codes[outside] = CREATURE
    return codes, iou


def room_ious(iou, codes):
    """IoUs of the scored room cells (row-major), for κ_keep."""
    keep = ~np.isnan(iou) & (codes != CREATURE)
    return [float(x) for x in iou[keep]]


def pack(codes_seq):
    seq = np.asarray(codes_seq, np.uint8)
    n = seq.shape[0]
    flat = seq.reshape(n, -1)
    k = flat.shape[1]
    stride = -(-k // 4)
    pad = np.zeros((n, stride * 4), np.uint8)
    pad[:, :k] = flat
    q = pad.reshape(n, stride, 4)
    b = q[..., 0] | (q[..., 1] << 2) | (q[..., 2] << 4) | (q[..., 3] << 6)
    return b.astype(np.uint8).tobytes()


def unpack(data, rows, cols):
    k = rows * cols
    stride = -(-k // 4)
    b = np.frombuffer(data, np.uint8)
    if len(b) % stride:
        raise ValueError(f"seam data of {len(b)} bytes is not a whole number of {stride}-byte frames")
    n = len(b) // stride
    b = b[: n * stride].reshape(n, stride)
    q = np.stack([(b >> s) & 3 for s in (0, 2, 4, 6)], axis=-1).reshape(n, stride * 4)
    return q[:, :k].reshape(n, rows, cols).astype(np.uint8)
