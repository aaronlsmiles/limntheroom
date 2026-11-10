#!/usr/bin/env python3
"""The ring's box for each rated row of capture/takes.json, from the acting creature's home mask.

    python tools/ring_boxes.py           # check: exit 1 if takes.json disagrees with the masks
    python tools/ring_boxes.py --write   # write the boxes into capture/takes.json

A row's box is its creature's static home (the majority vote over the chosen take's mask frames,
seam.controls_inputs.static_mask) bounded and padded by rating.prepare.RING_PAD_PX on the 1280x720
mask grid, as fractions of the frame (x0, y0, x1, y1): what rating/prepare.py rings on the cue-frame
still. Unrated rows get none. tests/test_rating_prepare.py checks the committed boxes against this.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rating.prepare import PrepareError, ring_bbox_from_mask  # noqa: E402

TAKES = ROOT / "capture" / "takes.json"
MASKS = ROOT / "masks"
# the keepers chosen on the printed terrazzo (9 Nov, STATUS.md S); masks/<id>.npz, p47-masks/1
CHOSEN = {"t01": "t01f", "t02": "t02e", "t03": "t03c", "t04": "t04d", "t05": "t05c", "t06": "t06c"}


def boxes(takes: list[dict], masks_dir=MASKS) -> list[list[float] | None]:
    """One entry per row of `takes`: the rated row's box as a list, None for an unrated row."""
    from seam.controls_inputs import static_mask
    from seam.masks import load_masks

    cache, out = {}, []
    for t in takes:
        if not t.get("rated"):
            out.append(None)
            continue
        who = f"{t['id']}/{t.get('target_material')}"
        if t["id"] not in CHOSEN:
            raise PrepareError(f"{who}: no chosen take for {t['id']}")
        name = f"home_{t['target_material']}"
        if (t.get("paste") or {}).get("home_mask", name) != name:
            raise PrepareError(f"{who}: paste.home_mask is {t['paste']['home_mask']!r}, not {name!r}")
        mid = CHOSEN[t["id"]]
        if mid not in cache:
            cache[mid] = load_masks(Path(masks_dir) / f"{mid}.npz")[1]
        if name not in cache[mid]:
            raise PrepareError(f"{who}: masks/{mid}.npz has no {name}")
        out.append(list(ring_bbox_from_mask(static_mask(cache[mid][name]))))
    return out


def render(takes: list[dict], bxs: list) -> str:
    """takes.json text with each rated row's ring_bbox on one line after target_position, otherwise the
    file's own formatting (json indent 2)."""
    rows = []
    for t, b in zip(takes, bxs):
        row = {k: v for k, v in t.items() if k != "ring_bbox"}
        if b is not None:
            keys = list(row)
            at = keys.index("target_position") + 1 if "target_position" in keys else len(keys)
            row = dict([*row.items()][:at] + [("ring_bbox", b)] + [*row.items()][at:])
        rows.append(row)
    text = json.dumps(rows, indent=2) + "\n"
    return re.sub(r'"ring_bbox": \[\s*([^\]]*?)\s*\]',
                  lambda m: '"ring_bbox": [' + ", ".join(v.strip() for v in m.group(1).split(",")) + "]", text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--takes", default=str(TAKES))
    ap.add_argument("--masks", default=str(MASKS))
    ap.add_argument("--write", action="store_true", help="write the boxes into the takes file")
    a = ap.parse_args(argv)
    path = Path(a.takes)
    takes = json.loads(path.read_text())
    bxs = boxes(takes, a.masks)
    for t, b in zip(takes, bxs):
        if b is not None:
            mark = "" if t.get("ring_bbox") == b else "   (differs from takes.json)"
            print(f"{t['id']}/{t['target_material']}: {b}{mark}")
    text = render(takes, bxs)
    if json.loads(text) != [{**{k: v for k, v in t.items() if k != "ring_bbox"}, **({"ring_bbox": b} if b else {})}
                            for t, b in zip(takes, bxs)]:
        raise SystemExit("ring_boxes: the rendered file does not round-trip")
    if a.write:
        path.write_text(text)
        print(f"wrote {path}")
        return 0
    stale = [t for t, b in zip(takes, bxs) if t.get("ring_bbox") != b]
    if stale:
        print(f"{len(stale)} row(s) disagree with the masks; run with --write", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
