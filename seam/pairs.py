"""The npz contract between the repo venv (which aligns, warps and masks) and the lines job
(which runs in the ComfyUI venv). Uncompressed np.savez; meta as a JSON string.

Keys: take, render (N,H,W,3) uint8 on the take grid (the render already warped); valid (N,) bool
(frames that passed the gate); R (N,H,W) bool; t (N,) float seconds; optional creature (N,H,W)
bool (the render's creature mask, warped); cover (N,H,W) bool (the pixels the warp reached inside
the render frame; the rest are already out of R, and their cells get no verdict); homes {name:
(H,W) bool}; scan (h,w,3) uint8 (the acting creature's scan crop); meta (dict).
"""
import json
from pathlib import Path

import numpy as np


def write_pair(path, *, take, render, valid, R, t, creature=None, cover=None, homes=None, scan=None, meta=None):
    take = np.asarray(take, np.uint8)
    render = np.asarray(render, np.uint8)
    valid = np.asarray(valid, bool)
    R = np.asarray(R, bool)
    t = np.asarray(t, float)
    n = take.shape[0]
    if n == 0:
        raise ValueError("a pair needs at least one frame")
    if render.shape != take.shape or valid.shape != (n,) or R.shape != take.shape[:3] or t.shape != (n,):
        raise ValueError("pair arrays disagree in shape")
    arrs = {"take": take, "render": render, "valid": valid, "R": R, "t": t,
            "meta": np.array(json.dumps(meta or {}, sort_keys=True))}
    if creature is not None:
        creature = np.asarray(creature, bool)
        if creature.shape != R.shape:
            raise ValueError("creature mask shape")
        arrs["creature"] = creature
    if cover is not None:
        cover = np.asarray(cover, bool)
        if cover.shape != R.shape:
            raise ValueError("cover mask shape")
        if (R & ~cover).any():
            raise ValueError("R holds pixels the warp did not cover")
        arrs["cover"] = cover
    for name, m in sorted((homes or {}).items()):
        arrs[f"home__{name}"] = np.asarray(m, bool)
    if scan is not None:
        arrs["scan"] = np.asarray(scan, np.uint8)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)       # as every other writer here (found by the rehearsal)
    np.savez(path, **arrs)
    return path


REQUIRED = ("take", "render", "valid", "R", "t", "meta")


def read_pair(path):
    with np.load(path, allow_pickle=False) as z:
        d = {k: z[k] for k in z.files}
    missing = [k for k in REQUIRED if k not in d]
    if missing:
        raise ValueError(f"{path}: missing keys {missing}")
    if d["take"].shape[0] == 0:
        raise ValueError(f"{path}: no frames")
    return {
        "take": d["take"], "render": d["render"], "valid": d["valid"].astype(bool), "R": d["R"].astype(bool),
        "t": d["t"], "creature": d["creature"].astype(bool) if "creature" in d else None,
        "cover": d["cover"].astype(bool) if "cover" in d else None,
        "homes": {k[len("home__"):]: v.astype(bool) for k, v in d.items() if k.startswith("home__")},
        "scan": d.get("scan"), "meta": json.loads(str(d["meta"])),
    }
