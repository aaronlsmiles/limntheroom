#!/usr/bin/env python3
"""Synthetic fixture for the seam-view sketch (card P47, Limn the Room).

Everything here is SYNTHETIC: drawn with OpenCV polylines, no real take, no AI
generation of any kind, no laws. A "take" (a desk in fine ink line art) and a
"render" (the same, plus an abstract ink scribble that walks off the page and
touches a glass; lines near the glass are redrawn while it does) are encoded as
H.264 and measured with a simplified form of the plan's R0.3 seam-cell rule.

Writes to web/public/sketch/:
  take.mp4, render.mp4   10 s, 15 fps, 1280x720, H.264
  seam.bin               2 bits per cell per frame (see FORMAT below)
  seam.json              cols, rows, fps, cue events, the drift series

Run:  uv run python tools/make_sketch_fixture.py [--out DIR]

Simplifications against R0.3 (the real rule lives in seam/): line maps are a
luma threshold on the decoded frames, not StillDrawn's _line_maps; there is no
alignment gate because both clips share one camera path; tolerant IoU is the
symmetric soft form below; "creature" cells are those touched by the dilated
creature strokes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from scipy.interpolate import PchipInterpolator

W, H, FPS, SECONDS = 1280, 720, 15, 10
N = FPS * SECONDS
CELL, TAU, KEEP = 32, 2, 0.6
LIMN = KEEP / 2
MIN_PX = 20
COLS, ROWS = W // CELL, -(-H // CELL)  # 40 x 23 (the last row is 16 px tall)
CAP = 16.0  # chamfer cap, px
CREATURE_PAD = 16  # px of dilation around the creature's strokes

# 2-bit codes in seam.bin
NONE, KEPT, LIMNED, CREATURE = 0, 1, 2, 3
FORMAT = (
    "frame-major, row-major; 4 cells per byte, cell i in bits 2*(i%4)..2*(i%4)+1 "
    "(little-endian within the byte); each frame padded to a whole byte; "
    "codes 0 none, 1 kept, 2 limned, 3 creature"
)

# glass: world position of its centre when set down, and the contact geometry
GX, GY = 660.0, 420.0
GLASS_RADIUS = 300.0
CONTACT = (4.0, 6.0)  # seconds; redrawing ramps in just after and out just after

# BGR
DESK = (203, 223, 230)
PAGE = (221, 236, 241)
INK = (31, 38, 42)

CUES = [
    {"id": "cue-1", "kind": "cue", "t": 3.0, "label": "cue 1: glass set down"},
    {"id": "contact", "kind": "contact", "t": CONTACT[0], "t_end": CONTACT[1], "label": "contact"},
    {"id": "cue-2", "kind": "cue", "t": 7.0, "label": "cue 2: glass lifted"},
]


# ----------------------------------------------------------------------------- geometry

def dense(pts, closed=False, step=4.0):
    p = np.asarray(pts, float)
    if closed:
        p = np.vstack([p, p[0]])
    out = []
    for a, b in zip(p[:-1], p[1:]):
        n = max(1, int(np.hypot(*(b - a)) // step))
        out.append(a + (b - a) * (np.arange(n) / n)[:, None])
    out.append(p[-1:])
    return np.vstack(out)


def ellipse(cx, cy, rx, ry, a0=0.0, a1=360.0, rot=0.0, step=4.0):
    n = max(8, int(np.pi * (rx + ry) * abs(a1 - a0) / 360.0 / step))
    a = np.radians(np.linspace(a0, a1, n))
    x, y = rx * np.cos(a), ry * np.sin(a)
    r = np.radians(rot)
    return np.stack([cx + x * np.cos(r) - y * np.sin(r), cy + x * np.sin(r) + y * np.cos(r)], 1)


class Stroke:
    def __init__(self, pts, seed, thick=2, closed=False, glass=False):
        self.pts, self.seed, self.thick, self.closed, self.glass = np.asarray(pts, float), seed, thick, closed, glass


def hand(pts, seed, amp=1.4, wl=110.0):
    """A fixed hand-drawn wobble along the stroke (fixed per stroke, same in take and render)."""
    rng = np.random.default_rng(seed)
    s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])
    ph = rng.uniform(0, 2 * np.pi, 2)
    return pts + np.stack([amp * np.sin(2 * np.pi * s / wl + ph[0]), amp * np.sin(2 * np.pi * s / (wl * 0.7) + ph[1])], 1)


def rot_pts(pts, centre, deg):
    r = np.radians(deg)
    c, s = np.cos(r), np.sin(r)
    q = np.asarray(pts, float) - centre
    return np.stack([q[:, 0] * c - q[:, 1] * s, q[:, 0] * s + q[:, 1] * c], 1) + centre


def build_scene():
    rng = np.random.default_rng(4717)
    strokes: list[Stroke] = []
    seed = [100]

    def add(pts, thick=2, closed=False, step=4.0, amp=1.4, glass=False):
        seed[0] += 1
        d = dense(pts, closed, step)
        strokes.append(Stroke(hand(d, seed[0], amp), seed[0], thick, closed, glass))

    # desk: two edge lines and long grain curves
    add([(0, 58), (W, 64)], 2, step=6)
    add([(0, 72), (W, 76)], 1, step=6)
    for i in range(7):
        y0 = 120 + i * 90 + rng.uniform(-12, 12)
        xs = np.linspace(-20, W + 20, 14)
        add(np.stack([xs, y0 + 7 * np.sin(xs / 190 + i) + rng.uniform(-2, 2, 14)], 1), 1, step=6, amp=0.8)

    # the page (portrait, tilted) with ruled "handwriting" and a doodle
    pc = np.array([350.0, 385.0])
    pw, ph_ = 350, 440
    corners = np.array([[-pw / 2, -ph_ / 2], [pw / 2, -ph_ / 2], [pw / 2, ph_ / 2], [-pw / 2, ph_ / 2]]) + pc
    page_poly = rot_pts(corners, pc, -4)
    add(page_poly, 2, closed=True)
    for li in range(10):
        y = pc[1] - ph_ / 2 + 56 + li * 34
        x = pc[0] - pw / 2 + 34
        x_end = pc[0] + pw / 2 - 34 - (rng.uniform(0, 90) if li % 3 == 2 else 0)
        while x < x_end - 30:
            wlen = rng.uniform(30, 80)
            xs = np.linspace(x, min(x + wlen, x_end), 18)
            ys = y + rng.uniform(2, 4.5) * np.sin(np.linspace(0, rng.uniform(5, 11), 18) + rng.uniform(0, 6)) + (xs - pc[0]) * 0.0698 * -1
            add(np.stack([xs, ys], 1), 1, step=3, amp=0.6)
            x += wlen + rng.uniform(10, 18)
    sp = np.linspace(0, 6.3 * 2.2, 90)
    add(np.stack([pc[0] + 60 + (6 + 5 * sp) * np.cos(sp), pc[1] + 135 + (6 + 5 * sp) * np.sin(sp)], 1) * 1.0, 1, step=3, amp=0.4)

    # a book standing up (left)
    bx, by, bw, bh = 62, 205, 86, 300
    book = np.array([[bx, by], [bx + bw, by + 10], [bx + bw, by + bh + 10], [bx, by + bh]])
    add(book, 2, closed=True)
    for k in (36, 52, bh - 56, bh - 40):
        add([(bx + 8, by + k + k * 0.03), (bx + bw - 8, by + k + 10 - k * 0.0 + k * 0.03)], 2, step=6, amp=0.8)
    add(ellipse(bx + bw / 2, by + 118, 20, 28), 1, step=3)
    add([(bx + bw, by + 10), (bx + bw + 16, by + 4), (bx + bw + 16, by + bh + 2), (bx + bw, by + bh + 10)], 2)
    for k in range(10, bh, 5):  # page edges
        add([(bx + bw + 1, by + 10 + k), (bx + bw + 15, by + 4 + k)], 1, step=6, amp=0.2)

    # the glass: rim, sides, base arc, water line, highlight
    gt, gb = -100.0, 100.0
    add(ellipse(GX, GY + gt, 62, 15), 2, glass=True)
    add([(GX - 62, GY + gt), (GX - 46, GY + gb)], 2, glass=True, step=5)
    add([(GX + 62, GY + gt), (GX + 46, GY + gb)], 2, glass=True, step=5)
    add(ellipse(GX, GY + gb, 46, 11, 0, 180), 2, glass=True)
    add(ellipse(GX, GY + 14, 54, 13), 1, glass=True, step=3)
    add([(GX - 38, GY + gt + 30), (GX - 33, GY + gb - 36)], 1, glass=True, step=5)
    add(ellipse(GX, GY + gb + 8, 74, 17, 10, 170), 1, glass=True, step=3)  # a faint ring on the desk

    # a mug (right)
    mx, my = 1040.0, 290.0
    add(ellipse(mx, my - 70, 52, 14), 2)
    add([(mx - 52, my - 70), (mx - 50, my + 62)], 2)
    add([(mx + 52, my - 70), (mx + 50, my + 62)], 2)
    add(ellipse(mx, my + 62, 50, 13, 0, 180), 2)
    add(ellipse(mx + 78, my - 4, 26, 36, -80, 100), 2)
    add(ellipse(mx, my - 62, 40, 9, 0, 180), 1, step=3)

    # a pencil, a ruler, a sticky note, a clip
    px, py = 930.0, 600.0
    add([(px, py), (px + 220, py - 34)], 2)
    add([(px, py + 14), (px + 220, py - 20)], 2)
    add([(px, py), (px - 36, py + 8), (px, py + 14)], 2, step=3)
    add([(px + 220, py - 34), (px + 220, py - 20)], 2)
    add([(px + 190, py - 29), (px + 190, py - 15)], 1)
    rx0, ry0 = 150.0, 660.0
    add([(rx0, ry0), (rx0 + 560, ry0 + 3), (rx0 + 560, ry0 + 34), (rx0, ry0 + 31)], 2, closed=True, step=6)
    for i in range(0, 71):
        tl = 16 if i % 5 == 0 else 9
        x = rx0 + 8 + i * 7.8
        add([(x, ry0 + 3 + i * 0.043), (x + 0.1, ry0 + 3 + tl + i * 0.043)], 1, step=6, amp=0.1)
    sn = np.array([[790, 108], [880, 104], [884, 196], [794, 200]], float)
    add(sn, 2, closed=True)
    for k in range(3):
        add([(sn[0, 0] + 12, sn[0, 1] + 30 + k * 22), (sn[1, 0] - 12, sn[1, 1] + 30 + k * 22)], 1, step=4, amp=0.7)
    add(ellipse(1180, 200, 14, 30, rot=20), 1, step=3)
    add(ellipse(1182, 206, 8, 20, rot=20), 1, step=3)
    return strokes, page_poly


def tag_layer():
    """The word 'synthetic' on a little tag, rendered once and warped with the camera each frame."""
    m = np.zeros((H, W), np.uint8)
    cv2.rectangle(m, (1010, 640), (1240, 690), 255, 2, cv2.LINE_AA)
    cv2.putText(m, "SYNTHETIC", (1024, 674), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 255, 2, cv2.LINE_AA)
    return m


# ----------------------------------------------------------------------------- motion

def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def glass_dy(t):
    """Lifted at the start, set down 2.2-3.0 s, lifted again 7.0-7.8 s."""
    down = smoothstep((t - 2.2) / 0.8)
    up = smoothstep((t - 7.0) / 0.8)
    return -70.0 * (1 - down) - 70.0 * up


def camera(t):
    s = 1 + 0.004 * np.sin(2 * np.pi * t / 4.0)
    tx = 2.0 * np.sin(2 * np.pi * t / 5.0)
    ty = 1.5 * np.sin(2 * np.pi * t / 3.3 + 1.0)
    return s, tx, ty


def cam_pts(pts, t):
    s, tx, ty = camera(t)
    c = np.array([W / 2, H / 2])
    return (pts - c) * s + c + np.array([tx, ty])


def boil(pts, k, seed, amp):
    rng = np.random.default_rng([seed, int(k)])
    ph = rng.uniform(0, 2 * np.pi, 3)
    x, y = pts[:, 0], pts[:, 1]
    dx = amp * (np.sin(0.045 * x + 0.031 * y + ph[0]) + 0.5 * np.sin(0.12 * x + 0.1 * y + ph[2]))
    dy = amp * (np.sin(0.037 * x - 0.05 * y + ph[1]) + 0.5 * np.sin(0.1 * x - 0.13 * y + ph[0]))
    return np.stack([dx, dy], 1)


def contact_env(t):
    return float(smoothstep((t - 3.9) / 0.6) * (1 - smoothstep((t - 5.6) / 0.6)))


# off the page's right edge, round under the glass, and up to touch its right-hand side at 4 s
_PATH_T = [0.0, 1.0, 2.0, 2.6, 3.0, 3.4, 3.7, 4.0, 6.0, 6.6, 7.4, 8.6, 10.0]
_PATH_X = [190.0, 270.0, 380.0, 490.0, 535.0, 610.0, 705.0, 750.0, 750.0, 790.0, 900.0, 1050.0, 1250.0]
_PATH_Y = [250.0, 300.0, 350.0, 420.0, 520.0, 600.0, 590.0, 478.0, 478.0, 560.0, 640.0, 630.0, 590.0]
_PX, _PY = PchipInterpolator(_PATH_T, _PATH_X), PchipInterpolator(_PATH_T, _PATH_Y)


def creature_strokes(f, t):
    """An abstract ink scribble: a few looped passes for a body, legs that swing, a flick for a tail."""
    cx, cy = float(_PX(t)), float(_PY(t))
    vx, vy = float(_PX(t, 1)), float(_PY(t, 1))
    speed = float(np.hypot(vx, vy))
    ang = np.arctan2(vy, vx) if speed > 8 else 0.0
    walk = np.clip(speed / 120.0, 0.25, 1.0)
    rng = np.random.default_rng([9001, f // 1])
    out = []
    R = 25.0
    th = np.linspace(0, 2 * np.pi * 1.12, 46)
    for j in range(3):
        ph = rng.uniform(0, 6.3, 2)
        r = R * (1 + 0.3 * np.sin(3 * th + ph[0]) + 0.18 * np.sin(5 * th + ph[1])) + rng.normal(0, 1.8, th.size)
        p = np.stack([1.3 * r * np.cos(th), r * np.sin(th)], 1)
        c, s = np.cos(ang), np.sin(ang)
        p = np.stack([p[:, 0] * c - p[:, 1] * s, p[:, 0] * s + p[:, 1] * c], 1) + (cx, cy)
        out.append(Stroke(p, 9100 + j, 2))
    c, s = np.cos(ang), np.sin(ang)
    for i in range(6):
        lat = (i - 2.5) * 11.0
        swing = np.sin(2 * np.pi * 1.8 * t + (i % 2) * np.pi) * 0.7 * walk
        base = np.array([0.6 * lat, 20.0 * np.sign(lat if lat else 1.0)])
        a = np.pi / 2 * np.sign(lat if lat else 1.0) + swing
        mid = base + 13 * np.array([np.sin(a * 0.4), np.sign(lat if lat else 1.0)])
        foot = mid + 11 * np.array([np.sin(a), np.cos(a) * np.sign(lat if lat else 1.0)])
        leg = np.array([base, mid, foot])
        leg = np.stack([leg[:, 0] * c - leg[:, 1] * s, leg[:, 0] * s + leg[:, 1] * c], 1) + (cx, cy)
        out.append(Stroke(dense(leg, step=3), 9200 + i, 2))
    tt = np.linspace(0, 1, 14)
    tail = np.stack([-34 - 20 * tt, 8 * np.sin(2 * np.pi * (1.4 * t + tt))], 1)
    tail = np.stack([tail[:, 0] * c - tail[:, 1] * s, tail[:, 0] * s + tail[:, 1] * c], 1) + (cx, cy)
    out.append(Stroke(dense(tail, step=3), 9300, 2))
    return out


# ----------------------------------------------------------------------------- drawing

def paper_grain():
    return np.random.default_rng(77).normal(0, 0.0, (H, W, 1)).astype(np.float32)


def draw_polys(img, items):
    for pts, thick, closed in items:
        p = np.round(pts * 16).astype(np.int32)
        cv2.polylines(img, [p], closed, INK, thick, cv2.LINE_AA, shift=4)


def frame_image(f, strokes, page_poly, tag, grain, with_render):
    t = f / FPS
    img = np.empty((H, W, 3), np.float32)
    img[:] = DESK
    pg = np.round(cam_pts(page_poly, t) * 16).astype(np.int32)
    base = img.astype(np.uint8)
    cv2.fillPoly(base, [pg], PAGE, cv2.LINE_AA, shift=4)
    img = base.astype(np.float32) + grain
    img = np.clip(img, 0, 255).astype(np.uint8)

    k = f // 2
    env = contact_env(t)
    items = []
    gdy = glass_dy(t)
    for st in strokes:
        pts = st.pts.copy()
        if st.glass:
            pts[:, 1] += gdy
        pts = pts + boil(pts, k, st.seed, 0.8)  # hand boil, held for two frames
        if with_render:
            pts = pts + boil(pts, f, st.seed + 7777, 0.8)  # the render's own small noise
            if env > 0:
                d = np.hypot(pts[:, 0] - GX, pts[:, 1] - GY)
                w = np.clip(1 - d / GLASS_RADIUS, 0, 1) ** 0.55 * env
                shift = np.array([11 * np.sin(2 * np.pi * 0.9 * t + 0.5), 7 * np.cos(2 * np.pi * 0.7 * t)])
                pts = pts + w[:, None] * (shift + boil(pts, f, st.seed + 31, 4.5))
        items.append((cam_pts(pts, t), st.thick, st.closed))
    draw_polys(img, items)

    s, tx, ty = camera(t)
    M = np.array([[s, 0, (1 - s) * W / 2 + tx], [0, s, (1 - s) * H / 2 + ty]], np.float32)
    tl = cv2.warpAffine(tag, M, (W, H), flags=cv2.INTER_LINEAR)
    img = np.where(tl[..., None] > 0, (img * (1 - tl[..., None] / 255.0) + np.array(INK) * (tl[..., None] / 255.0)), img).astype(np.uint8)

    mask = None
    if with_render:
        cr = []
        for st in creature_strokes(f, t):
            pts = st.pts + boil(st.pts, f, st.seed, 0.5)
            cr.append((cam_pts(pts, t), st.thick, st.closed))
        draw_polys(img, cr)
        layer = np.full((H, W, 3), 255, np.uint8)
        for pts, thick, closed in cr:
            cv2.polylines(layer, [np.round(pts * 16).astype(np.int32)], closed, (0, 0, 0), thick + 1, cv2.LINE_AA, shift=4)
        m = (layer[..., 0] < 250).astype(np.uint8)
        k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * CREATURE_PAD + 1,) * 2)
        mask = cv2.dilate(m, k2).astype(bool)
    return img, mask


# ----------------------------------------------------------------------------- video io

def encoder(path: Path, crf=23):
    return subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
         "-tune", "animation", "-bf", "0", "-g", str(FPS), "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
         "-movflags", "+faststart", "-an", "-metadata", "title=SYNTHETIC sketch fixture, not a real take",
         "-metadata", "comment=Synthetic: drawn with OpenCV for the Limn the Room seam-view sketch. No AI generation.", str(path)],
        stdin=subprocess.PIPE)


def decode_luma(path: Path):
    p = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True)
    a = np.frombuffer(p.stdout, np.uint8)
    assert a.size == N * W * H, (a.size, N * W * H)
    return a.reshape(N, H, W)


def reencode(src: Path, dst: Path, crf=34):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-c:v", "libx264", "-crf", str(crf), "-preset", "fast", "-pix_fmt", "yuv420p", str(dst)], check=True)


# ----------------------------------------------------------------------------- measures

DISK = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * TAU + 1, 2 * TAU + 1))


def lines_of(gray):
    return gray < 150


def cell_sum(a):
    pad = np.zeros((ROWS * CELL, COLS * CELL), np.float32)
    pad[:H, :W] = a
    return pad.reshape(ROWS, CELL, COLS, CELL).sum((1, 3))


def seam_cells(Lt, Lr, M):
    Dt = cv2.dilate(Lt.astype(np.uint8), DISK).astype(bool)
    Dr = cv2.dilate(Lr.astype(np.uint8), DISK).astype(bool)
    na, nb = cell_sum(Lt), cell_sum(Lr)
    inter = (cell_sum(Lt & Dr) + cell_sum(Lr & Dt)) / 2.0
    union = na + nb - inter
    iou = np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)
    code = np.full((ROWS, COLS), NONE, np.uint8)
    code[iou >= KEEP] = KEPT
    code[iou < LIMN] = LIMNED
    code[(na < MIN_PX) & (nb < MIN_PX)] = NONE
    code[cell_sum(M) > 0] = CREATURE
    return code


def drift(La, Lb, region):
    """Symmetric chamfer between two line maps, over the region, capped (px)."""
    da = cv2.distanceTransform(np.where(La, 0, 255).astype(np.uint8), cv2.DIST_L2, 3)
    db = cv2.distanceTransform(np.where(Lb, 0, 255).astype(np.uint8), cv2.DIST_L2, 3)
    pa, pb = Lb & region, La & region
    a = np.minimum(da[pa], CAP).mean() if pa.any() else 0.0
    b = np.minimum(db[pb], CAP).mean() if pb.any() else 0.0
    return float((a + b) / 2)


def pack(codes):  # (N, ROWS, COLS) uint8
    flat = codes.reshape(codes.shape[0], -1)
    pad = (-flat.shape[1]) % 4
    flat = np.pad(flat, ((0, 0), (0, pad))).reshape(codes.shape[0], -1, 4)
    return (flat[..., 0] | (flat[..., 1] << 2) | (flat[..., 2] << 4) | (flat[..., 3] << 6)).astype(np.uint8)


def unpack(buf, n_frames):
    b = np.asarray(buf, np.uint8).reshape(n_frames, -1)
    q = np.stack([(b >> (2 * i)) & 3 for i in range(4)], -1).reshape(n_frames, -1)
    return q[:, : ROWS * COLS].reshape(n_frames, ROWS, COLS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "web" / "public" / "sketch"))
    out = Path(ap.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)

    strokes, page_poly = build_scene()
    tag, grain = tag_layer(), paper_grain()
    ep_t, ep_r = encoder(out / "take.mp4"), encoder(out / "render.mp4")
    for f in range(N):
        a, _ = frame_image(f, strokes, page_poly, tag, grain, False)
        b, _ = frame_image(f, strokes, page_poly, tag, grain, True)
        ep_t.stdin.write(a.tobytes())
        ep_r.stdin.write(b.tobytes())
    for e in (ep_t, ep_r):
        e.stdin.close()
        if e.wait() != 0:
            sys.exit("ffmpeg failed")

    # measure on the decoded frames, as a browser would see them
    gt, gr = decode_luma(out / "take.mp4"), decode_luma(out / "render.mp4")
    with tempfile.TemporaryDirectory() as td:
        reencode(out / "take.mp4", Path(td) / "take_re.mp4")
        g0 = decode_luma(Path(td) / "take_re.mp4")
    # creature masks again (cheap: strokes only), so we need no per-frame storage above
    codes = np.zeros((N, ROWS, COLS), np.uint8)
    Dser, D0ser = [], []
    for f in range(N):
        t = f / FPS
        layer = np.full((H, W, 3), 255, np.uint8)
        for st in creature_strokes(f, t):
            pts = cam_pts(st.pts + boil(st.pts, f, st.seed, 0.5), t)
            cv2.polylines(layer, [np.round(pts * 16).astype(np.int32)], st.closed, (0, 0, 0), st.thick + 1, cv2.LINE_AA, shift=4)
        M = cv2.dilate((layer[..., 0] < 250).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * CREATURE_PAD + 1,) * 2)).astype(bool)
        Lt, Lr, L0 = lines_of(gt[f]), lines_of(gr[f]), lines_of(g0[f])
        codes[f] = seam_cells(Lt, Lr, M)
        Dser.append(drift(Lt, Lr, ~M))
        D0ser.append(drift(Lt, L0, np.ones((H, W), bool)))

    packed = pack(codes)
    assert np.array_equal(unpack(packed.ravel(), N), codes)
    (out / "seam.bin").write_bytes(packed.tobytes())

    ts = [round(f / FPS, 4) for f in range(N)]
    contact = [1 if CONTACT[0] <= t < CONTACT[1] else 0 for t in ts]
    meta = {
        "schema": "limn-sketch/1",
        "synthetic": True,
        "label": "synthetic sketch, not results",
        "note": ("A sketch of the seam view on synthetic data: two clips drawn by a script, a simplified seam rule on them, "
                 "no camera and no model. It shows how a real take and its regenerated render will be read. It is not a result."),
        "video": {"take": "take.mp4", "render": "render.mp4", "width": W, "height": H},
        "fps": FPS, "frames": N, "cell": CELL, "cols": COLS, "rows": ROWS,
        "tau": TAU, "kappa_keep": KEEP, "min_line_px": MIN_PX,
        "seam": {"file": "seam.bin", "format": FORMAT, "bytes_per_frame": packed.shape[1]},
        "cues": CUES,
        "series": {"t": ts, "D": [round(x, 4) for x in Dser], "D0": [round(x, 4) for x in D0ser], "contact": contact},
    }
    (out / "seam.json").write_text(json.dumps(meta, separators=(",", ":")))

    # self-check: the fixture must do what the sketch says it does
    kept, limned = (codes == KEPT).sum((1, 2)), (codes == LIMNED).sum((1, 2))
    pct = 100 * kept / np.maximum(kept + limned, 1)
    inside = np.array(contact, bool)
    away = ~inside
    print(f"cells {COLS}x{ROWS}, {packed.shape[1]} bytes/frame, seam.bin {packed.nbytes} B")
    print(f"kept% outside contact: mean {pct[away].mean():.1f}, min {pct[away].min():.1f}")
    print(f"kept% inside contact:  mean {pct[inside].mean():.1f}, min {pct[inside].min():.1f}")
    print(f"D outside contact mean {np.mean(np.array(Dser)[away]):.2f} px, inside {np.mean(np.array(Dser)[inside]):.2f} px, D0 mean {np.mean(D0ser):.2f} px")
    print(f"creature cells: min {int((codes == CREATURE).sum((1, 2)).min())}, max {int((codes == CREATURE).sum((1, 2)).max())}")
    ok = pct[away].mean() >= 97 and pct[inside].min() <= 90 and pct[away].min() >= 95
    print("self-check:", "ok" if ok else "FAILED (tune the fixture)")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
