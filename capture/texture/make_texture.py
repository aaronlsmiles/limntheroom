#!/usr/bin/env python3
"""A printable desk texture for the takes: grey terrazzo chips on white, A4 at 300 dpi, two sheets.

    uv run python capture/texture/make_texture.py   # writes capture/texture/desk-texture-A4.pdf (+ a PNG per sheet)

Why (call 127): the alignment gate fits each render frame to its take on ORB features outside the page,
and a plain desk gives almost none (ρ undefined on four of six takes). Random, non-repeating chips give
plenty of corners at the analysis scale (about 3 px per mm) without a repeating grid that could match one
period off, and in mid greys they read as a stone desk, distinct from the creatures' black ink. Seeded,
so a re-run prints the same sheets.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

DPI, W_MM, H_MM = 300, 210, 297
PX = lambda mm: int(round(mm / 25.4 * DPI))
OUT = Path(__file__).resolve().parent


def sheet(seed):
    rng = np.random.default_rng(seed)
    w, h = PX(W_MM), PX(H_MM)
    im = Image.new("L", (w, h), 246)
    d = ImageDraw.Draw(im)
    n = 2600
    for _ in range(n):
        cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        r = PX(rng.choice([1.2, 2.0, 3.0, 4.5], p=[0.45, 0.3, 0.17, 0.08]))
        k = rng.integers(3, 7)
        ang = np.sort(rng.uniform(0, 2 * np.pi, k))
        rad = r * rng.uniform(0.55, 1.0, k)
        pts = [(cx + a * np.cos(t), cy + a * np.sin(t)) for a, t in zip(rad, ang)]
        d.polygon(pts, fill=int(rng.choice([70, 105, 140, 175], p=[0.2, 0.3, 0.3, 0.2])))
    return im


if __name__ == "__main__":
    sheets = [sheet(s) for s in (20261108, 20261109)]
    for i, s in enumerate(sheets, 1):
        s.save(OUT / f"desk-texture-{i}.png")
    sheets[0].save(OUT / "desk-texture-A4.pdf", "PDF", resolution=DPI, save_all=True, append_images=sheets[1:])
    print("wrote", OUT / "desk-texture-A4.pdf")
