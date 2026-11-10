#!/usr/bin/env python3
"""Contact sheets of a take's SAM masks, for Aaron's check (agents/README.md, "The take masks", step 3).

    uv run python tools/mask_sheet.py --take t01d --out DIR [--every 1.0] [--cols 4]
    uv run python tools/mask_sheet.py --overview t01d,t02c,... --out DIR

Per take: one tile per `--every` seconds of the analysis copy (640x360), every object's mask filled in its own
colour with its outline, the object names and the second each track starts in a legend strip. The sheet is for
looking only: nothing it draws feeds a measurement. Overview: one row per take, its frame at 25 %, 50 % and the
last analysis frame.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seam import masks as M  # noqa: E402

COLOURS = {"page": (90, 90, 90), "home_ink": (255, 40, 40), "home_gold": (255, 200, 0), "home_paper": (40, 200, 255),
           "hand": (255, 0, 255), "glass": (0, 255, 120), "torch": (255, 120, 0), "standing_object": (0, 120, 255),
           "pen": (0, 255, 120), "note": (0, 255, 120)}
TILE = (640, 360)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def overlay(frame, m, i, draw_page=True):
    img = frame.astype(np.float32).copy()
    for k in sorted(m, key=lambda k: (k != "page", k)):
        if k == "page" and not draw_page:
            continue
        mk = m[k][i]
        if not mk.any():
            continue
        c = np.array(COLOURS.get(k, (255, 255, 255)), np.float32)
        a = 0.12 if k == "page" else 0.38
        img[mk] = (1 - a) * img[mk] + a * c
    img = np.clip(img, 0, 255).astype(np.uint8)
    for k in m:
        mk = m[k][i]
        if mk.any():
            cs, _ = cv2.findContours(mk.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(img, cs, -1, COLOURS.get(k, (255, 255, 255)), 2)
    return img


def tile(frame, m, i, fps, label=None):
    t = cv2.resize(overlay(frame, m, i), TILE, interpolation=cv2.INTER_AREA)
    txt = label or f"{i / fps:.1f} s"
    cv2.rectangle(t, (0, 0), (8 + 11 * len(txt), 22), (0, 0, 0), -1)
    cv2.putText(t, txt, (4, 16), FONT, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return t


def legend(m, fps, width, title):
    rows = [title] + [f"{k}: from {np.flatnonzero(v.any(axis=(1, 2)))[0] / fps:.1f} s, "
                      f"{int(v.any(axis=(1, 2)).sum())}/{len(v)} frames non-empty, "
                      f"{sum(M.quality_ok(v))} pass the quality rule" if v.any() else f"{k}: never tracked"
                      for k, v in sorted(m.items())]
    out = np.full((26 * len(rows) + 8, width, 3), 24, np.uint8)
    for j, r in enumerate(rows):
        k = r.split(":")[0]
        if j:
            cv2.rectangle(out, (8, 8 + 26 * j), (24, 24 + 26 * j), COLOURS.get(k, (255, 255, 255)), -1)
        cv2.putText(out, r, (32 if j else 8, 22 + 26 * j), FONT, 0.55, (235, 235, 235), 1, cv2.LINE_AA)
    return out


def load(take):
    frames = M.analysis_frames(ROOT / "takes" / f"{take}.analysis.mp4")
    meta, m = M.load_masks(ROOT / "masks" / f"{take}.npz")
    if meta["n_frames"] != len(frames):
        raise SystemExit(f"{take}: masks have {meta['n_frames']} frames, the video {len(frames)}")
    return frames, meta, m


def sheet(take, every, cols):
    frames, meta, m = load(take)
    fps = meta["fps"]
    idx = list(range(0, len(frames), max(1, int(round(every * fps)))))
    if idx[-1] != len(frames) - 1:
        idx.append(len(frames) - 1)
    tiles = [tile(frames[i], m, i, fps) for i in idx]
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    grid = np.vstack([np.hstack(tiles[r:r + cols]) for r in range(0, len(tiles), cols)])
    head = legend(m, fps, grid.shape[1], f"{take}: SAM 2.1 take masks (masks/{take}.npz, digest {M.mask_digest(m)[:12]})")
    return np.vstack([head, grid])


def overview(takes):
    rows = []
    for take in takes:
        frames, meta, m = load(take)
        n = len(frames)
        rows.append(np.hstack([tile(frames[i], m, i, meta["fps"], f"{take} {i / meta['fps']:.1f} s")
                               for i in (n // 4, n // 2, n - 1)]))
    keys = sorted(COLOURS)
    key = np.full((34, rows[0].shape[1], 3), 24, np.uint8)
    x = 8
    for k in keys:
        cv2.rectangle(key, (x, 10), (x + 14, 24), COLOURS[k], -1)
        cv2.putText(key, k, (x + 18, 23), FONT, 0.5, (235, 235, 235), 1, cv2.LINE_AA)
        x += 26 + 10 * len(k)
    return np.vstack([key] + rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--take")
    ap.add_argument("--overview", help="comma-separated take ids")
    ap.add_argument("--out", required=True)
    ap.add_argument("--every", type=float, default=1.0)
    ap.add_argument("--cols", type=int, default=4)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.take:
        p = out / f"{a.take}-masks.jpg"
        img = sheet(a.take, a.every, a.cols)
    elif a.overview:
        p = out / "overview-masks.jpg"
        img = overview(a.overview.split(","))
    else:
        ap.error("--take or --overview")
    cv2.imwrite(str(p), cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(json.dumps({"out": str(p), "size": [img.shape[1], img.shape[0]]}))


if __name__ == "__main__":
    main()
