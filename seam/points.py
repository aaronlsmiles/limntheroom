#!/usr/bin/env python3
"""Blind point prompts for SAM 2.1 (PREREGISTRATION §7): the take masks and the render masks.

Both are placed by the `blind-frame-picker` agent, in fresh folders, from frozen briefs, through
seam/dispatch.py; nobody edits a point. Every folder is a `prepared` attempt in a committed ledger before
it is dispatched (seam/blind.py), so no one can keep the answer they prefer.

Take masks (brief agents/briefs/take-mask-points.md):

    python seam/points.py take --video takes/t01a.analysis.mp4 --take t01a --cue glass
    python seam/dispatch.py run --code bXXXXXXXXXX                   -> masks/prompts/t01a.json
    python seam/points.py reject-take --take t01a --reason wrong-object

  The folder holds the brief, `objects.txt` (opaque letters with plain descriptions: no mask or material
  names), `stills.txt` and every TAKE_STRIDE-th analysis frame (2.5 a second) at 1280x720 with the
  labelled grid. Every file must be read. Aaron checks the tracks on a contact sheet (plan 2.1); a
  rejection, by a reason from a fixed list, sets the prompt file aside and allows the second attempt.

Render masks (brief agents/briefs/render-mask-points.md), after the blind prompt-frame pick:

    python seam/points.py render --video <render> --render t01-ink --take-masks masks/t01a.npz
    python seam/dispatch.py run ...           -> masks/prompts/render/t01-ink.p1.json (one point)
    python -m seam.masks track --prompts masks/prompts/render/t01-ink.p1.json ...       (first track)
    python seam/points.py render-check --video ... --render t01-ink --take-masks ... --masks <first track>
    python seam/dispatch.py run ...           -> masks/prompts/render/t01-ink.json (final)
    python -m seam.masks track --prompts masks/prompts/render/t01-ink.json ...          (final track)
    python seam/points.py track-done --render t01-ink --masks <final track>

  `place` sees only the prompt frame, plain and gridded, with the acting creature's home drawn as a
  dashed outline (call 108). `check` always runs, in a fresh folder: the same frame with the first
  track's outline; the agent accepts it, or gives the one second point the registration allows. Only the
  check writes the final prompt file (if both check attempts are invalid, the first point stands). A null
  place answer leaves the render with no render mask. `track-done` logs the final track's digest and file
  hash; the pair writer (seam/render_pair.py) computes both from the track file it is given and carries
  them as `meta.render_mask_digest` and `meta.render_mask_file_sha256`; seam/assemble.py and the lines
  job check them (`custody`).

Logs (committed): agents/logs/take-mask-points/<take>.json (registration manifest) and
agents/logs/render-mask-points/<render>.json (addendum A1, before the lines job).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from seam import blind, frame_pick  # noqa: E402

SCHEMA = "p47-mask-points/2"
TAKE_BRIEF = blind.BRIEFS / "take-mask-points.md"
RENDER_BRIEF = blind.BRIEFS / "render-mask-points.md"
PROMPTS = ROOT / "masks" / "prompts"
TAKE_STRIDE = 6        # every 6th analysis frame, 2.5 a second (hub call 130): on the textured desk, 65
                       # stills at every 3rd overflowed the session (call 129); 33 fit the 15 MB t01d proved
MAX_POINTS = 6
GRID_STEP = 64
OUTLINE = (0, 255, 255)
CROSS = (255, 255, 0)
BASE_OBJECTS = ["page", "home_ink", "home_gold", "home_paper", "hand"]
CUE_OBJECTS = {"glass": ["glass"], "torch": ["torch", "standing_object"], "pen": ["pen"], "breath": [],
               "note": ["note"], "hand": [], "curtain call": ["torch"]}
DESCRIPTIONS = {
    "page": "the page the three drawings sit on (a point on blank page, away from the drawings and anything lying on it)",
    "home_ink": "the drawing on the left of the page, where it sits in still 001",
    "home_gold": "the drawing in the centre of the page, where it sits in still 001",
    "home_paper": "the drawing on the right of the page, where it sits in still 001",
    "hand": "any hand or arm (one object for every hand and arm in the video)",
    "glass": "the glass of water",
    "torch": "the torch (a small hand lamp)",
    "standing_object": "the object standing on its edge on the desk",
    "pen": "the pen",
    "note": "the handwritten note (a small card with writing on it)",
}
REJECT_REASONS = {"wrong-object": "a track follows the wrong object",
                  "lost": "a track loses its object while it is still in view",
                  "spill": "a track spills onto a neighbour",
                  "missing": "an object in view has no track"}
LETTERS = "abcdefghijklmnopqrstuvwxyz"


def take_objects(cue: str) -> list[str]:
    if cue not in CUE_OBJECTS:
        raise blind.BlindError(f"cue {cue!r}: want one of {sorted(CUE_OBJECTS)}")
    return BASE_OBJECTS + CUE_OBJECTS[cue]


def _log_path(kind: str, ident: str) -> Path:
    """The one ledger per take or render (the root is fixed: blind.LOGS)."""
    frame_pick.check_id(ident)
    if kind == "render":
        frame_pick.home_name(ident)
    sub = "take-mask-points" if kind == "take" else "render-mask-points"
    return Path(blind.LOGS) / sub / f"{ident}.json"


def load_log(kind, ident) -> dict | None:
    p = _log_path(kind, ident)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _step(log: dict | None, step: str) -> dict:
    return ((log or {}).get("steps") or {}).get(step) or blind.new_step()


def _write_json(p: Path, d: dict) -> None:
    blind.save_json(p, d)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v)


def _point_problems(pt, w, h, where) -> list[str]:
    if not (_num(pt.get("x")) and _num(pt.get("y"))):
        return [f"{where}: x and y must be numbers"]
    if not (0 <= pt["x"] < w and 0 <= pt["y"] < h):
        return [f"{where}: outside the {w}x{h} frame"]
    return []


# --- prepare ------------------------------------------------------------------------------------
def _prepare(files, *, kind, step, ident, video_sha256, brief, extra) -> dict:
    lp = _log_path(kind, ident)
    blind.require_clean_or_new(lp)
    blind.require_clean_or_new(blind.registry_path())
    log = load_log(kind, ident) or {"schema": SCHEMA, "kind": kind, "id": ident, "video_sha256": video_sha256,
                                              "brief": frame_pick._rel(brief), "brief_sha256": blind.sha256_path(brief),
                                              "agent_sha256": blind.sha256_path(blind.PICKER), "steps": {},
                                              "rejections": []}
    for k, v in (("video_sha256", video_sha256), ("brief_sha256", blind.sha256_path(brief)),
                 ("agent_sha256", blind.sha256_path(blind.PICKER))):
        if log[k] != v:
            raise blind.BlindError(f"{ident}: {k} differs from the ledger's")
    s = log["steps"].setdefault(step, blind.new_step())
    blind.check_registry(s, f"{kind}-{step}", ident)
    blind.check_can_prepare(s, f"{ident} {step}")
    code = blind.new_code()
    folder = Path(blind.NEUTRAL_ROOT) / code
    inv = blind.write_folder(folder, files)
    dispatch = blind.dispatch_prompt(folder.resolve())
    st = {"schema": frame_pick.FOLDER_SCHEMA, "kind": f"{kind}-{step}", "code": code, "id": ident,
          "folder": str(folder.resolve()), "inventory": inv, "dispatch": dispatch,
          "agent": str(blind.PICKER.resolve()), "ledger": {"path": str(lp.resolve()), "step": step},
          "transcripts": str(blind.TRANSCRIPTS), **extra}
    blind.write_state(blind.STATE, code, st)
    blind.register(st["kind"], ident, code)
    s["attempts"].append(blind.prepared_attempt(code, dispatch, inv))
    blind.save_json(lp, log)
    blind.commit_ledger(lp, st["kind"], code, "prepared")
    return st


def build_take_folder(frames, *, take: str, objects, video_sha256: str, stride: int = TAKE_STRIDE,
                      step_px: int = GRID_STEP) -> dict:
    """The take-mask folder: gridded stills at the frames' own size (the 1280x720 analysis grid)."""
    from seam import masks
    objects = list(objects)
    if len(set(objects)) != len(objects) or not objects or len(objects) > len(LETTERS):
        raise blind.BlindError("objects must be distinct, 1 to 26 of them")
    if any(o not in DESCRIPTIONS for o in objects):
        raise blind.BlindError("an object has no description")
    letters = {LETTERS[i]: o for i, o in enumerate(objects)}
    idx = frame_pick.still_indices(len(frames), stride)
    names = [f"{k:03d}.png" for k in range(1, len(idx) + 1)]
    files = {blind.BRIEF_NAME: TAKE_BRIEF.read_bytes(),
             "objects.txt": "".join(f"{k}: {DESCRIPTIONS[o]}\n" for k, o in letters.items()).encode(),
             "stills.txt": ("\n".join(names) + "\n").encode()}
    for n, i in zip(names, idx):
        files[n] = blind.png_bytes(masks.grid_overlay(np.asarray(frames[i], np.uint8), step_px))
    h, w = np.asarray(frames[0]).shape[:2]
    return _prepare(files, kind="take", step="place", ident=take, video_sha256=video_sha256, brief=TAKE_BRIEF,
                    extra={"letters": letters, "stride": stride, "size": [int(h), int(w)],
                           "stills": [{"name": n, "frame": i} for n, i in zip(names, idx)]})


def _mask_outline(img, mask, point):
    import cv2
    cs, _ = cv2.findContours(np.asarray(mask, np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    img = np.ascontiguousarray(img.copy())
    cv2.drawContours(img, cs, -1, OUTLINE, 2, cv2.LINE_AA)
    x, y = int(round(point[0])), int(round(point[1]))
    cv2.line(img, (x - 8, y), (x + 8, y), CROSS, 2)
    cv2.line(img, (x, y - 8), (x, y + 8), CROSS, 2)
    return img


def build_render_folder(frames, *, render: str, home, video_sha256: str, step: str = "place", masks_path=None,
                        step_px: int = GRID_STEP) -> dict:
    """The render-mask folder for `place` or `check`: only the logged prompt frame, the home outlined. For
    `check`, `masks_path` is the first track: it must have been made from this render's .p1 prompt file and
    from the video the pick was made on."""
    from seam import masks
    f = frame_pick.verify(render)
    if f is None:
        raise blind.BlindError(f"{render}: the blind pick was none; there is no prompt frame")
    pick = frame_pick.load_log(render)
    home = np.asarray(home, bool)
    if pick["video_sha256"] != video_sha256 or pick["home_digest"] != blind.mask_digest(home):
        raise blind.BlindError(f"{render}: this video or home is not the one the pick was made on")
    if f >= len(frames):
        raise blind.BlindError(f"{render}: the prompt frame is past the video's frames")
    log = load_log("render", render)
    frame = blind.dashed_outline(np.asarray(frames[f], np.uint8), home)
    grid = masks.grid_overlay(frame, step_px)
    files = {blind.BRIEF_NAME: RENDER_BRIEF.read_bytes(), "task.txt": f"{step}\n".encode(),
             "frame.png": blind.png_bytes(frame), "frame.grid.png": blind.png_bytes(grid)}
    extra = {"frame": f, "size": list(frame.shape[:2])}
    if step == "check":
        place = _step(log, "place")
        if (place["result"] or {}).get("status") != "placed":
            raise blind.BlindError(f"{render}: the place step has no point to check")
        if masks_path is None:
            raise blind.BlindError(f"{render}: the check needs the first track")
        meta, mm = masks.load_masks(masks_path)
        p1_file = Path(PROMPTS) / "render" / f"{render}.p1.json"
        if meta.get("prompts_sha256") != blind.sha256_path(p1_file):
            raise blind.BlindError(f"{render}: the first track was not made from {p1_file.name}")
        if meta.get("video_sha256") != pick["video_sha256"]:
            raise blind.BlindError(f"{render}: the first track was not made on the video the pick was made on")
        m = np.asarray(mm.get("creature"), bool) if "creature" in mm else None
        if m is None or m.ndim != 3 or m.shape[0] <= f or m.shape[1:] != frame.shape[:2]:
            raise blind.BlindError(f"{render}: want the first track's creature mask covering the prompt frame")
        p1 = place["result"]["point"]
        files["mask.grid.png"] = blind.png_bytes(_mask_outline(grid, m[f], (p1["x"], p1["y"])))
        extra["mask_digest"] = blind.mask_digest(m[f])
        extra["first_track_sha256"] = blind.sha256_path(masks_path)
    elif step != "place":
        raise blind.BlindError(f"step {step!r}: want place or check")
    return _prepare(files, kind="render", step=step, ident=render, video_sha256=video_sha256, brief=RENDER_BRIEF,
                    extra=extra)


# --- parse (problems never echo what the agent wrote) -------------------------------------------
def parse_take(out: dict, *, letters, n_stills: int, size=(720, 1280)) -> tuple[dict, list[str]]:
    """({letter: [(still, x, y, positive)]}, problems) for a take-points answer."""
    h, w = size
    probs = blind.extra_fields(out, {"objects", "not_found"})
    objs, nf = out.get("objects"), out.get("not_found", [])
    if not isinstance(objs, dict) or not isinstance(nf, list):
        return {}, probs + ["want an objects map and a not_found list"]
    stray = [k for k in list(objs) + list(nf) if k not in letters]
    if stray:
        probs.append(f"{len(stray)} key(s) that are not letters in objects.txt")
    seen = list(objs) + list(nf)
    for k in letters:
        if seen.count(k) != 1:
            probs.append(f"object {k}: must appear exactly once in objects or not_found")
    got = {}
    for k in letters:
        if k not in objs:
            continue
        pts = objs[k]
        if not isinstance(pts, list) or not pts or len(pts) > MAX_POINTS:
            probs.append(f"object {k}: 1 to {MAX_POINTS} points")
            continue
        rows = []
        for j, pt in enumerate(pts):
            where = f"object {k} point {j + 1}"
            if not isinstance(pt, dict) or set(pt) != {"still", "x", "y", "positive"}:
                probs.append(f"{where}: want exactly still, x, y, positive")
                continue
            s = pt["still"]
            if isinstance(s, bool) or not isinstance(s, int) or not 1 <= s <= n_stills:
                probs.append(f"{where}: still must be 1-{n_stills}")
                continue
            if not isinstance(pt["positive"], bool):
                probs.append(f"{where}: positive must be true or false")
                continue
            p = _point_problems(pt, w, h, where)
            probs += p
            if not p:
                rows.append((s, float(pt["x"]), float(pt["y"]), pt["positive"]))
        if rows:
            first = min(r[0] for r in rows)
            if not any(r[3] for r in rows if r[0] == first):
                probs.append(f"object {k}: its first still needs a positive point")
        got[k] = rows
    return got, probs


def parse_place(out: dict, size) -> tuple[dict | None, list[str]]:
    h, w = size
    if set(out) != {"x", "y"}:
        return None, ["want exactly x and y"]
    if out["x"] is None and out["y"] is None:
        return None, []
    p = _point_problems(out, w, h, "point")
    return (None, p) if p else ({"x": float(out["x"]), "y": float(out["y"])}, [])


def parse_check(out: dict, size) -> tuple[dict | None, list[str]]:
    h, w = size
    if out == {"covers": True}:
        return None, []
    if set(out) != {"covers", "x", "y", "positive"} or out["covers"] is not False or not isinstance(out["positive"], bool):
        return None, ['want {"covers": true} or {"covers": false, "x", "y", "positive"}']
    p = _point_problems(out, w, h, "point")
    return (None, p) if p else ({"x": float(out["x"]), "y": float(out["y"]), "positive": out["positive"]}, [])


# --- record -------------------------------------------------------------------------------------
def record(code: str, stream, store) -> dict:
    """Check a dispatched points attempt against its stream and session store (blind.Lost if untrustworthy)."""
    st = blind.read_state(blind.STATE, code)
    prompts_dir = Path(PROMPTS)
    kind, _, step = st["kind"].partition("-")
    if kind not in ("take", "render") or step not in ("place", "check"):
        raise blind.BlindError(f"{code} is not a points folder")
    ident = st["id"]
    log, s = blind.ledger_load(st)
    att = blind.find_attempt(s, code)
    agent = blind.agent_spec(st["agent"])
    evs, tevs, ident_, probs = blind.bound_session(st, att, stream, store, agent)
    kept = {"transcript_sha256": blind.sha256_path(blind.keep_transcript(stream, code, st["transcripts"])),
            "store_sha256": blind.sha256_path(blind.keep_transcript(store, code, st["transcripts"], ".store.jsonl"))}
    folder = Path(st["folder"])
    if blind.inventory(folder) != st["inventory"]:
        probs.append("the folder changed after it was written")
    rl = blind.read_log(folder, evs, [r["name"] for r in st["inventory"]], context_evs=tevs)
    probs += blind.attempt_problems(rl)
    if rl["unread"]:
        probs.append(f"{len(rl['unread'])} file(s) never read, first {rl['unread'][0]}")
    text = blind.final_text(evs)
    size = tuple(st["size"])
    parsed, got, p = None, None, []
    try:
        parsed = blind.parse_output(text)
        if kind == "take":
            got, p = parse_take(parsed, letters=list(st["letters"]), n_stills=len(st["stills"]), size=size)
        elif step == "place":
            got, p = parse_place(parsed, size)
        else:
            got, p = parse_check(parsed, size)
    except blind.BlindError as e:
        p = [str(e)]
    probs += p
    valid = not probs
    att.update(status="recorded", recorded_utc=blind.now(), read_log=rl, identity=ident_,
               output=parsed if valid else None, output_sha256=blind.sha256_bytes(text.encode()), problems=probs,
               valid=valid, **kept)
    source = {"log": frame_pick._rel(st["ledger"]["path"]), "brief_sha256": log["brief_sha256"],
              "agent_sha256": log["agent_sha256"], "code": code}
    if valid and kind == "take":
        frames = [x["frame"] for x in st["stills"]]
        objs = {st["letters"][k]: [{"frame": frames[r[0] - 1], "x": r[1], "y": r[2], "positive": r[3]} for r in rows]
                for k, rows in sorted(got.items())}
        nf = sorted(st["letters"][k] for k in parsed.get("not_found", []))
        _write_json(Path(prompts_dir) / f"{ident}.json", {"take": ident, "objects": objs, "not_found": nf, "source": source})
        s["result"] = {"status": "placed", "objects": sorted(objs), "not_found": nf}
    elif valid and step == "place":
        if got is None:
            s["result"] = {"status": "not_found", "point": None, "frame": st["frame"]}
        else:
            pt = {"frame": st["frame"], "x": got["x"], "y": got["y"], "positive": True}
            _write_json(Path(prompts_dir) / "render" / f"{ident}.p1.json",
                        {"take": ident, "objects": {"creature": [pt]}, "source": source})
            s["result"] = {"status": "placed", "point": pt, "frame": st["frame"]}
    elif valid:
        pts = [_step(log, "place")["result"]["point"]]
        if got is not None:
            pts.append({"frame": st["frame"], "x": got["x"], "y": got["y"], "positive": got["positive"]})
        _write_json(Path(prompts_dir) / "render" / f"{ident}.json", {"take": ident, "objects": {"creature": pts}, "source": source})
        s["result"] = {"status": "covers" if got is None else "second_point", "points": pts, "mask_digest": st["mask_digest"],
                       "first_track_sha256": st["first_track_sha256"]}
    elif kind == "render" and step == "check" and len(s["attempts"]) >= blind.MAX_ATTEMPTS:
        # the check only grants the optional second point; without a valid check the first point stands
        pts = [_step(log, "place")["result"]["point"]]
        _write_json(Path(prompts_dir) / "render" / f"{ident}.json", {"take": ident, "objects": {"creature": pts}, "source": source})
        s["result"] = {"status": "failed_kept_first", "points": pts, "mask_digest": st["mask_digest"],
                       "first_track_sha256": st["first_track_sha256"]}
    blind.close_if_spent(s)
    blind.ledger_save(st, log)
    return log


def reject_take(take: str, *, reason: str) -> dict:
    """Aaron's contact-sheet check failed: log the reason (from REJECT_REASONS), set the prompt file aside,
    and allow the second attempt."""
    if reason not in REJECT_REASONS:
        raise blind.BlindError(f"reason must be one of {sorted(REJECT_REASONS)}")
    log = load_log("take", take)
    s = _step(log, "place")
    if not log or (s["result"] or {}).get("status") != "placed":
        raise blind.BlindError(f"{take}: nothing placed to reject")
    if len(s["attempts"]) >= blind.MAX_ATTEMPTS:
        raise blind.BlindError(f"{take}: both attempts used; a rejection can't be re-placed")
    p = Path(PROMPTS) / f"{take}.json"
    n = len(log["rejections"]) + 1
    if p.exists():
        os.replace(p, p.with_name(f"{take}.rejected{n}.json"))
    log["rejections"].append({"utc": blind.now(), "reason": reason, "result": s["result"]})
    s["result"] = None
    log["steps"]["place"] = s
    blind.save_json(_log_path("take", take), log)
    blind.commit_ledger(_log_path("take", take), "take-place", take, f"rejected-{reason}")
    return log


# --- the final track and the render's custody ---------------------------------------------------
def record_track(render: str, masks_path) -> dict:
    """Log the final render-mask track: it must come from the final prompt file; its digest and file hash
    are what the pair writer carries as `meta.render_mask_digest` and `meta.render_mask_file_sha256`."""
    from seam import masks
    log = load_log("render", render)
    chk = _step(log, "check")
    if not log or (chk["result"] or {}).get("status") not in ("covers", "second_point", "failed_kept_first"):
        raise blind.BlindError(f"{render}: the check step has no final prompt file")
    if blind.open_attempts(chk) or "track" in log["steps"]:
        raise blind.BlindError(f"{render}: the check has an unrecorded attempt, or the track is already logged")
    final = Path(PROMPTS) / "render" / f"{render}.json"
    meta, m = masks.load_masks(masks_path)
    if meta.get("prompts_sha256") != blind.sha256_path(final):
        raise blind.BlindError(f"{render}: the track was not made from the final prompt file")
    if meta.get("video_sha256") != frame_pick.load_log(render)["video_sha256"]:
        raise blind.BlindError(f"{render}: the track was not made on the video the pick was made on")
    if "creature" not in m:
        raise blind.BlindError(f"{render}: the track has no creature mask")
    log["steps"]["track"] = {"result": {"status": "tracked", "render_mask_digest": masks.mask_digest({"creature": m["creature"]}),
                                        "masks_sha256": blind.sha256_path(masks_path), "prompts_sha256": meta["prompts_sha256"],
                                        "source_size": meta.get("source_size"), "utc": blind.now()}}
    blind.save_json(_log_path("render", render), log)
    blind.commit_ledger(_log_path("render", render), "render-track", render, "tracked")
    return log


def custody(render: str, *, prompts, pair_meta, creature) -> int:
    """Everything a render's D depends on, checked:
    - the pick ledger, the points ledger and the registry are committed and unmodified at HEAD, and each
      ledger's attempts are the registry's (no fork, no rewind);
    - a valid blind pick with no unrecorded attempt; the final prompt file equal to the logged points and
      starting at the pick; a logged final track;
    - the pair (seam/render_pair.py writes it): its render id; the render-mask digest and the hash of the
      track file it was built from, both equal to the logged track's; the final prompt file the track was made
      from; the video the pick was made on; a gate that passed; and its creature mask (`creature`, the warped
      track as the pair holds it) equal to the digest the writer recorded.
    A pair from anything else (a hand-made npz, an older writer) fails closed. Returns the prompt frame."""
    for path in (frame_pick.log_path(render), _log_path("render", render), blind.registry_path()):
        blind.require_committed(path)
    f = frame_pick.verify(render, prompts=prompts)
    if f is None:
        raise blind.BlindError(f"{render}: the blind pick was none (never clear of its home); no render mask")
    log = load_log("render", render)
    if not log or any(blind.open_attempts(s) for k, s in log["steps"].items() if k != "track"):
        raise blind.BlindError(f"{render}: no render-mask points logged, or an attempt is unrecorded")
    for step in ("place", "check"):
        blind.check_registry(_step(log, step), f"render-{step}", render)
    res = _step(log, "check")["result"] or {}
    d = blind.loads_strict(Path(prompts).read_text(encoding="utf-8"))
    if res.get("points") is None or d.get("objects") != {"creature": res["points"]}:
        raise blind.BlindError(f"{render}: the prompt file is not the logged final points")
    tr = (log["steps"].get("track") or {}).get("result")
    if not tr:
        raise blind.BlindError(f"{render}: the final track is not logged (points.py track-done)")
    meta = pair_meta or {}
    if meta.get("render") != render:
        raise blind.BlindError(f"{render}: the pair is for another render")
    if meta.get("render_mask_digest") != tr["render_mask_digest"] or \
            meta.get("render_mask_file_sha256") != tr["masks_sha256"]:
        raise blind.BlindError(f"{render}: the pair's creature mask is not the logged final track")
    if meta.get("prompts_sha256") != tr["prompts_sha256"] or blind.sha256_path(prompts) != tr["prompts_sha256"]:
        raise blind.BlindError(f"{render}: the pair's track was not made from the final prompt file")
    if meta.get("video_sha256") != frame_pick.load_log(render)["video_sha256"]:
        raise blind.BlindError(f"{render}: the pair was not built on the video the pick was made on")
    g = meta.get("gate")
    if not isinstance(g, dict) or g.get("pass") is not True or not g.get("sha256"):
        raise blind.BlindError(f"{render}: the pair's render did not pass the alignment gate")
    from seam import masks
    c = np.asarray(creature, bool) if creature is not None else None
    if c is None or c.ndim != 3 or meta.get("creature_digest") != masks.mask_digest({"creature": c}):
        raise blind.BlindError(f"{render}: the pair's creature mask is not the one its writer recorded")
    return f


# --- CLI ----------------------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python seam/points.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        pass

    t = sub.add_parser("take")
    t.add_argument("--video", required=True, help="the take's analysis copy")
    t.add_argument("--take", required=True)
    t.add_argument("--cue", required=True, choices=sorted(CUE_OBJECTS))
    common(t)
    for name in ("render", "render-check"):
        r = sub.add_parser(name)
        r.add_argument("--video", required=True, help="the render, as the frame pick saw it")
        r.add_argument("--render", required=True)
        r.add_argument("--take-masks", required=True)
        if name == "render-check":
            r.add_argument("--masks", required=True, help="the first track (p47-masks/1) from the .p1 prompts")
        common(r)
    td = sub.add_parser("track-done")
    td.add_argument("--render", required=True)
    td.add_argument("--masks", required=True)
    rj = sub.add_parser("reject-take")
    rj.add_argument("--take", required=True)
    rj.add_argument("--reason", required=True, choices=sorted(REJECT_REASONS))
    a = ap.parse_args(argv)
    try:
        if a.cmd in ("take", "render", "render-check"):
            from seam import masks
            frames = masks.analysis_frames(a.video)
            sha = blind.sha256_path(a.video)
            if a.cmd == "take":
                st = build_take_folder(frames, take=a.take, objects=take_objects(a.cue), video_sha256=sha)
            else:
                st = build_render_folder(frames, render=a.render, home=frame_pick.load_home(a.take_masks, a.render),
                                         video_sha256=sha, step="place" if a.cmd == "render" else "check",
                                         masks_path=a.masks if a.cmd == "render-check" else None)
            print(json.dumps({"code": st["code"], "next": f"python seam/dispatch.py run --code {st['code']}"}, indent=1))
        elif a.cmd == "track-done":
            record_track(a.render, a.masks)
            print(f"{a.render}: final track logged")
        else:
            reject_take(a.take, reason=a.reason)
            print(f"{a.take}: rejected ({a.reason}); one fresh placement allowed")
    except (blind.BlindError, OSError, ValueError, KeyError) as e:
        print(f"points: refuse: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
