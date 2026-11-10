#!/usr/bin/env python3
"""The creature crops from the flat scan: one RGBA PNG per material and creature/scan/crops.json.

    uv run python tools/make_crops.py raw/scan-a.JPG [--out creature/scan]

The scan is one top-down photo of the final page (capture/PROTOCOL.md, "The flat scan"). The three creatures
sit in a row, ink left, gold centre, paper right. Each is found as the largest blob in its third of the page:
  ink    dark pixels (the drawn line), closed and filled, so the cut-out is the drawing's whole silhouette;
  gold   pixels clearly off the page's white in saturation (the paint), filled;
  paper  the same for the cut paper.
The alpha channel is that silhouette (255 inside, 0 outside); the RGB is the scan itself. Each crop is the
silhouette's bounding box plus a 12 px margin. The source scan's SHA-256 and the boxes go into crops.json, so
a re-run on the same file gives the same crops. Nothing here is generated: it is a cut-out of the photo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
MARGIN = 12
MATERIALS = ("ink", "gold", "paper")


def page_box(bgr):
    """The sheet: the largest bright, low-saturation region."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    white = ((hsv[..., 1] < 40) & (hsv[..., 2] > 170)).astype(np.uint8)
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(white)
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    x, y, w, h = st[i, :4]
    return x, y, w, h


def silhouette(fg):
    """Close small gaps, fill holes, keep the largest component."""
    k = max(5, int(round(min(fg.shape) * 0.01)) | 1)
    fg = cv2.morphologyEx(fg.astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(fg)
    if n < 2:
        raise SystemExit("no creature found in a third of the page")
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    one = (lab == i).astype(np.uint8)
    cnts, _ = cv2.findContours(one, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    filled = np.zeros_like(one)
    cv2.drawContours(filled, cnts, -1, 1, thickness=cv2.FILLED)
    return filled.astype(bool)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scan", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "creature" / "scan")
    a = ap.parse_args(argv)
    bgr = cv2.imread(str(a.scan), cv2.IMREAD_COLOR)
    if bgr is None:
        raise SystemExit(f"cannot read {a.scan}")
    px, py, pw, ph = page_box(bgr)
    page = bgr[py:py + ph, px:px + pw]
    hsv = cv2.cvtColor(page, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
    # the creatures sit in the far half of the page (protocol: centres 70 mm from the far edge of 210 mm)
    band = slice(0, ph // 2)
    a.out.mkdir(parents=True, exist_ok=True)
    crops = {}
    for k, name in enumerate(MATERIALS):
        x0, x1 = k * pw // 3, (k + 1) * pw // 3
        roi_hsv, roi_gray = hsv[band, x0:x1], gray[band, x0:x1]
        if name == "ink":
            fg = roi_gray < 110
        else:
            fg = (roi_hsv[..., 1] > 45) & (roi_hsv[..., 2] > 60)
        sil = silhouette(fg)
        ys, xs = np.nonzero(sil)
        y0 = max(0, ys.min() - MARGIN); y1 = min(sil.shape[0], ys.max() + 1 + MARGIN)
        xa = max(0, xs.min() - MARGIN); xb = min(sil.shape[1], xs.max() + 1 + MARGIN)
        rgb = page[band, x0:x1][y0:y1, xa:xb]
        alpha = (sil[y0:y1, xa:xb] * 255).astype(np.uint8)
        rgba = np.dstack([rgb, alpha])
        f = f"{name}.png"
        cv2.imwrite(str(a.out / f), rgba)
        crops[name] = {"file": f, "box_in_scan": [int(px + x0 + xa), int(py + y0), int(xb - xa), int(y1 - y0)],
                       "area_px": int(sil.sum())}
    rec = {"schema": "p47-crops/1", "scan": a.scan.name,
           "scan_sha256": hashlib.sha256(a.scan.read_bytes()).hexdigest(), "page_box_in_scan": [int(px), int(py), int(pw), int(ph)],
           "method": "tools/make_crops.py: largest blob per third of the page's far half; ink by dark line, closed and "
                     "filled; gold and paper by saturation; alpha is the filled silhouette", "crops": crops}
    (a.out / "crops.json").write_text(json.dumps(rec, indent=1) + "\n")
    for n, c in crops.items():
        print(f"{n:6s} box {c['box_in_scan']} area {c['area_px']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
