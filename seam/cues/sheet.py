"""Assemble and validate a take's cue sheet, ``cues/<take>.json`` in ``p47-cues/1``:

    {take, fps, n_frames, size, events: [{id, t, t_end, cue, what, target, source, evidence}], vlm_log}

- ``t`` is when the cue becomes available to the creature (a hand enters, a prop settles, the torch
  spot appears, a breath starts, the note becomes readable); ``t_end`` is when it ends, or null.
- ``source`` is ``detector:<name>`` or ``hand`` (entered by hand).
- ``target`` is the acting creature's material for events of the take's own cue, and null for
  context events (for example the hand that sets a prop down), which fire no law.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA = "p47-cues/1"
CUES = ("water", "light", "pen", "breath", "note", "hand")
MATERIALS = ("ink", "gold", "paper")
TOP_KEYS = {"schema", "take", "fps", "n_frames", "size", "events", "vlm_log"}
EVENT_KEYS = {"id", "t", "t_end", "cue", "what", "target", "source", "evidence"}
_SOURCE = re.compile(r"^(hand|detector:[a-z][a-z0-9_]*)$")


def _r(x):
    return None if x is None else round(float(x), 3)


def make_event(*, t, t_end, cue, what, source, evidence) -> dict:
    """An event without an id; ``assemble`` numbers them."""
    return {"t": _r(t), "t_end": _r(t_end), "cue": cue, "what": what, "target": None,
            "source": source, "evidence": evidence}


def assemble(*, take, fps, n_frames, size, events, fires=None, target=None, vlm_log=()) -> dict:
    """Sort events by (t, cue, source), number them e01…, give ``target`` to events whose cue is
    ``fires``, validate, and return the sheet. Inputs are not modified."""
    evs = [copy.deepcopy(e) for e in events]
    for e in evs:
        e.pop("id", None)
        if fires is not None and e["cue"] == fires:
            e["target"] = target
    evs.sort(key=lambda e: (e["t"], e["cue"], e["source"], e["what"]))
    ordered = [{"id": f"e{i:02d}", **e} for i, e in enumerate(evs, start=1)]
    s = {"schema": SCHEMA, "take": take, "fps": fps, "n_frames": int(n_frames), "size": list(size),
         "events": ordered, "vlm_log": list(vlm_log)}
    validate_sheet(s)
    return s


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate_sheet(s: dict) -> dict:
    def bad(msg):
        raise ValueError(f"cue sheet: {msg}")

    if not isinstance(s, dict) or set(s) != TOP_KEYS:
        bad(f"top-level keys must be exactly {sorted(TOP_KEYS)}")
    if s["schema"] != SCHEMA:
        bad(f"schema must be {SCHEMA}")
    if not isinstance(s["take"], str) or not s["take"]:
        bad("take must be a non-empty string")
    if not _num(s["fps"]) or s["fps"] <= 0:
        bad("fps must be positive")
    if isinstance(s["n_frames"], bool) or not isinstance(s["n_frames"], int) or s["n_frames"] < 1:
        bad("n_frames must be a positive integer")
    if not (isinstance(s["size"], list) and len(s["size"]) == 2 and all(isinstance(v, int) and v > 0 for v in s["size"])):
        bad("size must be [width, height]")
    if not isinstance(s["events"], list) or not isinstance(s["vlm_log"], list):
        bad("events and vlm_log must be lists")
    length = s["n_frames"] / s["fps"]
    last = None
    for i, e in enumerate(s["events"], start=1):
        where = f"event {i}"
        if not isinstance(e, dict) or set(e) != EVENT_KEYS:
            bad(f"{where}: keys must be exactly {sorted(EVENT_KEYS)}")
        if e["id"] != f"e{i:02d}":
            bad(f"{where}: id must be e{i:02d} (events are numbered in time order)")
        if e["cue"] not in CUES:
            bad(f"{where}: cue {e['cue']!r} is not one of {CUES}")
        if not _num(e["t"]) or not 0 <= e["t"] <= length + 1e-6:
            bad(f"{where}: t must lie within the take (0-{length:.3f} s)")
        if e["t_end"] is not None and (not _num(e["t_end"]) or e["t_end"] < e["t"] or e["t_end"] > length + 1e-6):
            bad(f"{where}: t_end must be null or between t and the take's end")
        if last is not None and e["t"] < last:
            bad(f"{where}: events must be in time order")
        last = e["t"]
        if not isinstance(e["what"], str) or not e["what"].strip():
            bad(f"{where}: what must be a non-empty string")
        if e["target"] is not None and e["target"] not in MATERIALS:
            bad(f"{where}: target must be null or one of {MATERIALS}")
        if not isinstance(e["source"], str) or not _SOURCE.match(e["source"]):
            bad(f"{where}: source must be 'hand' or 'detector:<name>'")
        if not isinstance(e["evidence"], dict):
            bad(f"{where}: evidence must be an object")
        try:
            json.dumps(e["evidence"], allow_nan=False)
        except (TypeError, ValueError) as err:
            bad(f"{where}: evidence must be plain JSON without NaN or infinity ({err})")
    for v in s["vlm_log"]:
        if not isinstance(v, dict) or set(v) != {"t", "text"}:
            bad("vlm_log entries are {t, text}")
    return s


def dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def write_sheet(path, s: dict) -> Path:
    validate_sheet(s)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dumps(s), encoding="utf-8")
    return p


def load_sheet(path) -> dict:
    return validate_sheet(json.loads(Path(path).read_text(encoding="utf-8")))


# --- the take orchestrator ------------------------------------------------------
# Which detectors run for a take, by the take's own cue. Hands run everywhere (the hand that sets a
# prop down is a context event); the note take reads the note by OCR only, so the note's arrival is
# not fired twice (once by props, once by OCR).
DEFAULT_DETECTORS = {
    "water": ("hands", "props"),
    "light": ("hands", "torch"),
    "pen": ("hands", "props"),
    "breath": ("hands", "breath"),
    "note": ("hands", "note"),
    "hand": ("hands",),
}


def from_take(*, take, frames, fps, fires, target, masks=None, objects=None, wav=None, page_box=None,
              note_box=None, hands_presence=None, detectors=None, vlm_log=()) -> dict:
    """Run the enabled detectors on one take and assemble its sheet.

    ``frames``: analysis frames (n, h, w, 3) RGB at ``fps``. ``masks``: {object: (n, h, w) bool};
    ``objects``: {object: cue} for the props detector. ``hands_presence`` replaces MediaPipe with a
    given presence list (tests). ``detectors`` defaults to ``DEFAULT_DETECTORS[fires]``."""
    from . import breath, hands, note, props, torch

    detectors = tuple(detectors if detectors is not None else DEFAULT_DETECTORS[fires])
    unknown = set(detectors) - {"hands", "props", "torch", "breath", "note"}
    if unknown:
        raise ValueError(f"unknown detector(s) {sorted(unknown)}")
    n, h, w = frames.shape[:3]
    events: list[dict] = []
    if "hands" in detectors:
        events += (hands.detect_from_presence(hands_presence, fps) if hands_presence is not None
                   else hands.detect(frames, fps))
    if "props" in detectors:
        for obj, cue in sorted((objects or {}).items()):
            m = (masks or {}).get(obj)
            if m is None:
                raise ValueError(f"props: no mask for object {obj!r}")
            if m.shape != (n, h, w):
                raise ValueError(f"props: mask for {obj!r} is {m.shape}, frames are {(n, h, w)}")
            events += props.detect_masks(m, fps=fps, obj=obj, cue=cue)
    if "torch" in detectors:
        if not masks or "page" not in masks:
            raise ValueError("torch: the take's masks with the page track are required (call 132)")
        for name, m in masks.items():
            if m.shape != (n, h, w):
                raise ValueError(f"torch: mask for {name!r} is {m.shape}, frames are {(n, h, w)}")
        events += torch.detect(frames, fps, masks=masks)
    if "breath" in detectors:
        if wav is None:
            raise ValueError("breath: the take's WAV is required")
        events += breath.detect(wav, frames=frames, fps=fps, page_box=page_box)
    if "note" in detectors:
        if note_box is None:
            if not masks or "note" not in masks:
                raise ValueError("note: the note's track (or an explicit note box) is required (call 132)")
            note_box = note.box_from_track(masks["note"])
        events += note.detect(frames, fps, box=note_box)
    return assemble(take=take, fps=fps, n_frames=n, size=[w, h], events=events, fires=fires,
                    target=target, vlm_log=vlm_log)


def _box(s):
    v = [int(x) for x in s.split(",")]
    if len(v) != 4:
        raise argparse.ArgumentTypeError("a box is x,y,w,h")
    return tuple(v)


def _kv(s):
    if "=" not in s:
        raise argparse.ArgumentTypeError("expected name=value")
    k, v = s.split("=", 1)
    return k, v


def main(argv=None) -> int:
    from ..masks import ANALYSIS_FPS, load_masks, sample_frames

    ap = argparse.ArgumentParser(prog="python -m seam.cues.sheet", description="Detect cues on one take; write its p47-cues/1 sheet.")
    ap.add_argument("--take", required=True)
    ap.add_argument("--video", required=True, help="the 1280x720 analysis copy")
    ap.add_argument("--fires", required=True, choices=CUES, help="the take's own cue")
    ap.add_argument("--target", required=True, choices=MATERIALS, help="the acting creature's material")
    ap.add_argument("--masks", help="masks/<take>.npz (p47-masks/1)")
    ap.add_argument("--object", action="append", type=_kv, default=[], help="object=cue for the props detector")
    ap.add_argument("--wav")
    ap.add_argument("--page-box", type=_box)
    ap.add_argument("--note-box", type=_box)
    ap.add_argument("--detectors", help="comma-separated; default by the take's cue")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    frames = sample_frames(a.video, fps=ANALYSIS_FPS)
    m = load_masks(a.masks)[1] if a.masks else None
    s = from_take(take=a.take, frames=frames, fps=ANALYSIS_FPS, fires=a.fires, target=a.target, masks=m,
                  objects=dict(a.object), wav=a.wav, page_box=a.page_box, note_box=a.note_box,
                  detectors=a.detectors.split(",") if a.detectors else None)
    write_sheet(a.out, s)
    print(json.dumps({"out": a.out, "events": [[e["id"], e["t"], e["cue"], e["target"]] for e in s["events"]]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
