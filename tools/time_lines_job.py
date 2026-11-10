#!/usr/bin/env python3
"""Time the lines job on one synthetic 150-frame pair (10 s at 15 fps, 1280×720).

    uv run python tools/time_lines_job.py OUT_DIR      # writes the pair and null npz, then runs the
                                                        # job under the ComfyUI venv and prints timings
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from seam import pairs, regions  # noqa: E402

COMFY = Path.home() / "tools/ComfyUI/.venv/bin/python"
N, H, W = 150, 720, 1280


def frames(seed, shift=0):
    rng = np.random.default_rng(seed)
    base = np.full((H, W, 3), 232, np.uint8)
    for _ in range(120):                                   # a desk of strokes
        x, y = int(rng.integers(0, W - 200)), int(rng.integers(0, H - 200))
        L = int(rng.integers(40, 200))
        if rng.random() < 0.5:
            base[y:y + 3, x:x + L] = 30
        else:
            base[y:y + L, x:x + 3] = 30
    out = np.repeat(base[None], N, axis=0)
    out = np.roll(out, shift, axis=2)
    for i in range(N):                                    # a creature crossing the desk
        cx = 200 + 6 * i
        out[i, 300:360, cx:cx + 50] = 20
    return out


def main(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    take, render = frames(0), frames(0, shift=2)
    creature = np.zeros((N, H, W), bool)
    for i in range(N):
        creature[i, 300:360, 200 + 6 * i:250 + 6 * i] = True
    home = np.zeros((H, W), bool)
    home[560:660, 1000:1100] = True
    R = np.stack([regions.measured_region(c, home, 32) for c in creature])
    t = np.arange(N) / 15
    pair = pairs.write_pair(out_dir / "pair.npz", take=take, render=render, valid=np.ones(N, bool), R=R, t=t,
                            creature=creature, homes={"rest": home}, scan=take[0, 300:360, 200:250],
                            meta={"render": "timing-fixture"})
    null = pairs.write_pair(out_dir / "null.npz", take=take, render=take, valid=np.ones(N, bool), R=R, t=t)
    t0 = time.time()
    r = subprocess.run([str(COMFY), str(REPO / "seam/lines_job.py"), "measure", "--pair", str(pair),
                        "--null", str(null), "--kappa", "0.8", "--out", str(out_dir / "lines.json"),
                        "--seam", str(out_dir / "seam.bin")], capture_output=True, text=True)
    wall = time.time() - t0
    if r.returncode:
        print(r.stderr[-3000:])
        sys.exit(r.returncode)
    rec = json.loads((out_dir / "lines.json").read_text())
    extracted = 3 * N + 1
    print(json.dumps({"frames": N, "wall_s": round(wall, 1), "measure_s": round(rec["seconds"], 1),
                      "s_per_analysis_frame_with_null": round(wall / N, 2),
                      "s_per_extracted_frame": round(wall / extracted, 2), "device": rec["device"],
                      "D_median": float(np.median([d for d in rec["D"] if d is not None]))}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
