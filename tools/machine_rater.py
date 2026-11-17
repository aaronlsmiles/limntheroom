#!/usr/bin/env python3
"""Prepare the machine rater's study rounds (§17, secondary) over the items the human study showed.

    uv run python tools/machine_rater.py prepare --round study-baseline
    uv run python tools/machine_rater.py prepare --round study-clips
    uv run python seam/dispatch.py run --code <code> --q2 sealed/q2-options.json
    uv run python tools/machine_rater.py csv --out sealed/machine-rater/study.csv

The items come from sealed/rating-manifest.json: each item's ringed baseline panel and its rating copy, the
files every human rater saw (rating/media/). The clips round's contact sheets are the rating copy's frames at
two a second (seam.blind.sheet_times over the copy's registered length). `prepare` prints the folder code and
counts only; refs stay in the sealed folder map.

`csv` writes the two valid rounds' answers in the blindpanel v0.2 export's columns (visitor `M`), so the
registered analysis/ratings.py scores the machine rater exactly as it scores a person; it is reported apart.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from seam import blind  # noqa: E402

MANIFEST = ROOT / "sealed" / "rating-manifest.json"
MEDIA = ROOT / "rating" / "media"
BRIEFS = {"study-baseline": ROOT / "sealed" / "briefs" / "study-baseline-rater.md",
          "study-clips": ROOT / "sealed" / "briefs" / "study-clips-rater.md"}
PARTS = {"study-baseline": ("baseline", {"q1b": "q1b", "q2b": "q2b"}),
         "study-clips": ("clips", {"q1": "q1", "q2": "q2"})}
COLUMNS = ["visitor", "instrument", "part", "position", "item", "question", "score", "flags", "option"]


def clip_sheets(path, seconds):
    from seam.video import nearest_indices, read_video
    frames, pts = read_video(path)
    times = blind.sheet_times(seconds)
    return blind.contact_sheets([frames[i] for i in nearest_indices(pts, times)], times)


def items_for(round_id, manifest):
    seconds = manifest["frames"] / manifest["fps"]
    out = []
    for it in manifest["items"]:
        item = {"ref": it["ref"], "panel": MEDIA / f"{it['panel_code']}.png"}
        if round_id == "study-clips":
            clip = MEDIA / f"{it['clip_code']}.mp4"
            if blind.sha256_path(clip) != it["clip_sha256"]:
                raise blind.BlindError("a rating copy is not the clip the study shows")
            item["sheets"] = clip_sheets(clip, seconds)
        out.append(item)
    return out


def prepare(round_id):
    manifest = blind.loads_strict(MANIFEST.read_text(encoding="utf-8"))
    st = blind.build_rater_folder(items_for(round_id, manifest), round_id=round_id, brief=BRIEFS[round_id])
    return {"round": round_id, "code": st["code"], "kind": st["kind"], "n_items": len(st["codes"]),
            "n_files": len(st["inventory"])}


def valid_record(round_id):
    log = json.loads(blind.rater_ledger_path(round_id).read_text(encoding="utf-8"))
    res = log.get("result") or {}
    if res.get("status") != "rated":
        return None
    rec = json.loads((blind.SEALED / "machine-rater" / f"{res['code']}.json").read_text(encoding="utf-8"))
    return rec if rec["valid"] and rec["round"] == round_id else None


def write_csv(out):
    rows, missing = [], []
    for round_id, (part, questions) in PARTS.items():
        rec = valid_record(round_id)
        if rec is None:
            missing.append(round_id)
            continue
        for pos, (code, ans) in enumerate(sorted(rec["output"]["items"].items()), 1):
            for field, qid in questions.items():
                rows.append({"visitor": "M", "instrument": "machine", "part": part, "position": pos,
                             "item": rec["refs"][code], "question": qid, "score": "", "flags": "",
                             "option": ans[field]})
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return {"rows": len(rows), "missing": missing, "sha256": blind.sha256_path(out)}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python tools/machine_rater.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--round", required=True, choices=sorted(PARTS))
    c = sub.add_parser("csv")
    c.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        print(json.dumps(prepare(a.round) if a.cmd == "prepare" else write_csv(a.out), sort_keys=True))
    except (blind.BlindError, OSError, ValueError) as e:
        print(f"machine_rater: refuse: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
