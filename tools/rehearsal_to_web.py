#!/usr/bin/env python3
"""The synthetic rehearsal's outputs, in the seam view's data format (web/public/rehearsal/).

    uv run python tools/rehearsal_to_web.py [--repo blind/rehearsal] [--out web/public/rehearsal]

Reads what tools/rehearse.py left in its throwaway repo: the aligned pair (runs/pairs/t01-ink.npz), the
lines job's 2-bit seam file (runs/seam/t01-ink.bin), the assembled p47-measure/1 record
(runs/measure/t01-ink.json) and the cue sheet (cues/t01.json). Writes take.mp4 and render.mp4 (the pair's
frames on the analysis grid, so the two clips and the cells line up frame for frame), seam.bin (copied
byte for byte) and seam.json in the sketch's limn-sketch/1 layout, labelled as the rehearsal.

Everything is still synthetic: drawn shapes, a stub agent, the fixture laws. The measurement chain is the
real one; the data it measured is not a take.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from seam import cells, pairs  # noqa: E402

RENDER, TAKE = "t01-ink", "t01"


def encode(frames: np.ndarray, fps: int, out: Path) -> None:
    n, h, w, _ = frames.shape
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "slow",
                          "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(out)],
                         stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(np.ascontiguousarray(f).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise SystemExit(f"ffmpeg failed on {out}")


def _num(x):
    return None if x is None else round(float(x), 4)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=ROOT / "blind" / "rehearsal")
    ap.add_argument("--out", type=Path, default=ROOT / "web" / "public" / "rehearsal")
    a = ap.parse_args(argv)
    runs = a.repo / "runs"
    P = pairs.read_pair(runs / "pairs" / f"{RENDER}.npz")
    rec = json.loads((runs / "measure" / f"{RENDER}.json").read_text())
    cue_sheet = json.loads((a.repo / "cues" / f"{TAKE}.json").read_text())
    seam_src = runs / "seam" / f"{RENDER}.bin"

    n, h, w, _ = P["take"].shape
    fps = int(cue_sheet["fps"])
    rows, cols = cells.grid_shape(h, w)
    bpf = -(-(rows * cols) // 4)
    if seam_src.stat().st_size != n * bpf:
        raise SystemExit(f"seam file is {seam_src.stat().st_size} bytes, expected {n} x {bpf}")

    s = rec["series"]
    contact = [1 if c else 0 for c in s["contact"]]
    on = [i for i, c in enumerate(contact) if c]
    events = [{"id": e["id"], "kind": "cue", "t": round(float(e["t"]), 3), "label": f"cue: {e['what']}"}
              for e in cue_sheet["events"]]
    if on:
        events.append({"id": "contact", "kind": "contact", "t": round(on[0] / fps, 3),
                       "t_end": round((on[-1] + 1) / fps, 3), "label": "contact"})
    events.sort(key=lambda e: e["t"])

    a.out.mkdir(parents=True, exist_ok=True)
    encode(P["take"], fps, a.out / "take.mp4")
    encode(P["render"], fps, a.out / "render.mp4")
    shutil.copyfile(seam_src, a.out / "seam.bin")
    D0 = s.get("D0") or [None] * n
    meta = {
        "schema": "limn-sketch/1", "synthetic": True, "source": "rehearsal",
        "label": "synthetic rehearsal, not results",
        "note": ("The end-to-end rehearsal of the measurement chain: drawn shapes on a drawn page, a stub "
                 "blind agent, the fixture laws, no camera and no model. The seam cells, drift and contact "
                 "window are the real pipeline's output on that synthetic pair."),
        "video": {"take": "take.mp4", "render": "render.mp4", "width": w, "height": h},
        "fps": fps, "frames": n, "cell": cells.CELL, "cols": cols, "rows": rows, "tau": cells.TAU,
        "kappa_keep": rec["params"].get("kappa"), "min_line_px": cells.MIN_PX,
        "seam": {"file": "seam.bin", "format": ("frame-major, row-major; 4 cells per byte, cell i in bits "
                                                "2*(i%4)..2*(i%4)+1 (little-endian within the byte); each frame "
                                                "padded to a whole byte; codes 0 none, 1 kept, 2 limned, 3 creature"),
                 "bytes_per_frame": bpf},
        "cues": events,
        "series": {"t": [round(i / fps, 4) for i in range(n)], "D": [_num(x) for x in s["D"]],
                   "D0": [_num(x) for x in D0], "contact": contact},
    }
    (a.out / "seam.json").write_text(json.dumps(meta) + "\n")
    print(f"{a.out}: {n} frames at {fps} fps, {cols}x{rows} cells, contact frames {on[:1] + on[-1:]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
