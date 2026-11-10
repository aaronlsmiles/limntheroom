#!/usr/bin/env python3
"""The blind prompt-frame pick (calls 106 and 108; PREREGISTRATION §7).

A render mask is SAM 2.1 propagated forward from one positive point on the acting creature at its
prompt frame: the first analysis frame where **no part of the creature overlaps its home**, the spot
where it was drawn (call 108; "off the page" would make most picks "none", since the props sit on the
page). Frames before it count as the creature at home. The controller knows the laws, so it does not
choose that frame: the `blind-frame-picker` agent does, from numbered stills of the render on which the
acting creature's home is drawn as a thin grey dashed outline (from the take's home mask). The outline
marks a place, so it says nothing about a law. The pick is logged before any D is computed.

    python seam/frame_pick.py prepare --video <render, any 16:9 size> --render t01-ink --take-masks masks/t01a.npz
    python seam/dispatch.py run --code bXXXXXXXXXX          # runs the agent and records it (`record`)
    python seam/frame_pick.py verify --render t01-ink [--prompts masks/prompts/render/t01-ink.json]

The folder (directly under ~/.blind, under a random code) holds only:
  agent-brief.md   agents/briefs/prompt-frame.md, byte for byte;
  stills.txt       the still names, in time order;
  001.png ...      every 3rd analysis frame (15 fps on the 1280x720 grid, so 5 a second), or every 4th, 5th or
                   6th if that is the first whose folder fits the payload budget (choose_stride, call 135; the
                   ledger records it), the home outline drawn on, downscaled to 960x540.
Still k is analysis frame (k - 1) * stride. The pick may land up to stride - 1 frames late; those frames
count as at home, which adds creature lines to R away from contact, so the error works against H.

The ledger, `agents/logs/prompt-frame/<render>.json`: `prepare` appends a `prepared` attempt before the
folder can be dispatched, and refuses while any attempt is unrecorded; dispatch.py marks it
`dispatched` (with the session id) and then `record` reads that session's transcript. An attempt is valid
only if the transcript is bound to this dispatch, the agent, model, system prompt and tools are the
expected ones, no context file outside the allowlist loaded, the brief was read first, nothing else
outside the folder's list was read, the folder is unchanged, the answer is exactly `{"pick": n}` or
`{"pick": "none"}`, and every still up to the pick (all of them, for "none") was read. Two attempts in
all; a valid pick is final. "none" means the creature never leaves its home: no render mask, and the
render is not testable for H. The log goes into addendum A1 before the lines job runs; `verify`,
seam/assemble.py and the lines job refuse a log with an unrecorded attempt or a prompt frame that is
not the logged pick.
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

from seam import blind  # noqa: E402

SCHEMA = "p47-prompt-frame/2"
FOLDER_SCHEMA = "p47-blind-folder/2"
BRIEF = blind.BRIEFS / "prompt-frame.md"
STRIDES = (3, 4, 5, 6)   # call 135: every 3rd frame fits every terrazzo take (12.5-13.5 MB of the 16 MB budget; every
STRIDE = STRIDES[0]      # 2nd frame did not, 18.8-20.1 MB); a larger stride only if a render's folder would not fit
STILL_SIZE = (540, 960)
ANALYSIS_SIZE = (720, 1280)
MAX_ATTEMPTS = blind.MAX_ATTEMPTS
_RENDER = re.compile(r"t0[1-7]-(ink|gold|paper)")
_ID = re.compile(r"[a-z0-9][a-z0-9_.-]*")


def still_indices(n_frames: int, stride: int = STRIDE) -> list[int]:
    return list(range(0, n_frames, stride))


def _rel(p) -> str:
    p = Path(p).resolve()
    try:
        return str(p.relative_to(ROOT.resolve()))
    except ValueError:
        return p.name


def home_name(render: str) -> str:
    """The acting creature's home mask in the take masks: home_<material>."""
    if not _RENDER.fullmatch(render):
        raise blind.BlindError(f"render id {render!r}: want tNN-<material>")
    return "home_" + render.split("-")[1]


def check_id(ident: str) -> str:
    if not _ID.fullmatch(ident):
        raise blind.BlindError(f"id {ident!r}: lowercase letters, digits, - _ . only")
    return ident


def log_path(render: str) -> Path:
    """The one ledger for a render's pick (the root is fixed: blind.LOGS)."""
    home_name(render)
    return Path(blind.LOGS) / "prompt-frame" / f"{render}.json"


def load_log(render: str) -> dict | None:
    p = log_path(render)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# --- prepare ------------------------------------------------------------------------------------
def _stills(frames, home, stride, size):
    idx = still_indices(len(frames), stride)
    names = [f"{k:03d}.png" for k in range(1, len(idx) + 1)]
    imgs = {n: blind.png_bytes(blind.resize(blind.dashed_outline(frames[i], home), size)) for n, i in zip(names, idx)}
    return idx, names, imgs


def choose_stride(frames, home, size=STILL_SIZE, strides=STRIDES):
    """(stride, still indices, names, images): the first of `strides` whose stills fit the payload budget as a
    session receives them (blind.payload_bytes). Decided from the video alone, before any attempt, so every
    attempt on one render uses the same stride. No stride fits: refused (call 135)."""
    for s in strides:
        idx, names, imgs = _stills(frames, home, s, size)
        if blind.payload_bytes(imgs) <= blind.PAYLOAD_BUDGET:
            return s, idx, names, imgs
    raise blind.BlindError(f"no stride in {strides} fits the {blind.PAYLOAD_BUDGET} byte payload budget")


def build_folder(frames, *, render: str, home, video_sha256: str, stride: int | None = None, size=STILL_SIZE) -> dict:
    """Write the agent's folder from the render's analysis frames, with the home outlined on each, and
    append a `prepared` attempt to the ledger. `home`: the acting creature's static home mask (H, W).
    `stride` None (the registered rule): choose_stride; a test may pin one."""
    import numpy as np
    brief, agent = BRIEF, blind.PICKER
    frames = np.asarray(frames)
    home = np.asarray(home, bool)
    if home.shape != frames.shape[1:3] or not home.any():
        raise blind.BlindError(f"{render}: the home mask must be non-empty and match the frames' size")
    if stride is None:
        stride, idx, names, imgs = choose_stride(frames, home, size)
    else:
        idx, names, imgs = _stills(frames, home, stride, size)
    lp = log_path(render)
    blind.require_clean_or_new(lp)
    blind.require_clean_or_new(blind.registry_path())
    log = load_log(render) or {
        "schema": SCHEMA, "render": render, "video_sha256": video_sha256, "home_digest": blind.mask_digest(home),
        "stride": stride, "brief": _rel(brief), "brief_sha256": blind.sha256_path(brief),
        "agent_sha256": blind.sha256_path(agent), **blind.new_step()}
    for k, v in (("video_sha256", video_sha256), ("home_digest", blind.mask_digest(home)), ("stride", stride),
                 ("brief_sha256", blind.sha256_path(brief)), ("agent_sha256", blind.sha256_path(agent))):
        if log[k] != v:
            raise blind.BlindError(f"{render}: {k} differs from the ledger's")
    blind.check_registry(log, "prompt-frame", render)
    blind.check_can_prepare(log, render)
    if not idx or len(idx) > 999:
        raise blind.BlindError(f"{len(idx)} stills: want 1 to 999")
    files = {blind.BRIEF_NAME: Path(brief).read_bytes(), "stills.txt": ("\n".join(names) + "\n").encode(), **imgs}
    code = blind.new_code()
    folder = Path(blind.NEUTRAL_ROOT) / code
    inv = blind.write_folder(folder, files)
    dispatch = blind.dispatch_prompt(folder.resolve())
    st = {"schema": FOLDER_SCHEMA, "kind": "prompt-frame", "code": code, "render": render, "id": render,
          "folder": str(folder.resolve()), "inventory": inv, "dispatch": dispatch, "agent": str(Path(agent).resolve()),
          "stills": [{"name": n, "frame": i} for n, i in zip(names, idx)], "size": list(size),
          "ledger": {"path": str(lp.resolve()), "step": None}, "transcripts": str(blind.TRANSCRIPTS)}
    blind.write_state(blind.STATE, code, st)
    blind.register("prompt-frame", render, code)
    log["attempts"].append(blind.prepared_attempt(code, dispatch, inv))
    blind.save_json(lp, log)
    blind.commit_ledger(lp, "prompt-frame", code, "prepared")
    return st


# --- record -------------------------------------------------------------------------------------
def parse_pick(out: dict, n_stills: int) -> tuple[int | None, list[str]]:
    """(still number or None for "none", problems). Problems never echo what the agent wrote."""
    probs = blind.extra_fields(out, {"pick", "unreadable"})
    if "pick" not in out:
        return None, probs + ["no pick"]
    p, pick = out["pick"], None
    if p == "none":
        pick = None
    elif isinstance(p, int) and not isinstance(p, bool) and 1 <= p <= n_stills:
        pick = p
    else:
        probs.append(f"pick must be a still number 1-{n_stills} or \"none\"")
    unread = out.get("unreadable", [])
    if not isinstance(unread, list):
        probs.append("unreadable must be a list")
    elif unread:
        probs.append(f"{len(unread)} still(s) reported unreadable")
    return pick, probs


def record(code: str, stream, store) -> dict:
    """Check the dispatched attempt `code` against its stream and session store and close it in the ledger.
    Raises blind.Lost when the record cannot be trusted (seam/dispatch.py then closes the step as failed)."""
    st = blind.read_state(blind.STATE, code)
    if st.get("kind") != "prompt-frame":
        raise blind.BlindError(f"{code} is not a prompt-frame folder")
    log, step = blind.ledger_load(st)
    att = blind.find_attempt(step, code)
    agent = blind.agent_spec(st["agent"])
    evs, tevs, ident, probs = blind.bound_session(st, att, stream, store, agent)
    kept = {"transcript_sha256": blind.sha256_path(blind.keep_transcript(stream, code, st["transcripts"])),
            "store_sha256": blind.sha256_path(blind.keep_transcript(store, code, st["transcripts"], ".store.jsonl"))}
    folder = Path(st["folder"])
    if blind.inventory(folder) != st["inventory"]:
        probs.append("the folder changed after it was written")
    rl = blind.read_log(folder, evs, [r["name"] for r in st["inventory"]], context_evs=tevs)
    probs += blind.attempt_problems(rl)
    text = blind.final_text(evs)
    out, pick = None, None
    try:
        parsed = blind.parse_output(text)
        pick, p = parse_pick(parsed, len(st["stills"]))
        probs += p
        if not p:
            out = parsed
    except blind.BlindError as e:
        probs.append(str(e))
    if out is not None:
        need = st["stills"] if pick is None else st["stills"][:pick]
        missed = [s for s in need if f"<folder>/{s['name']}" not in set(rl["reads"])]
        if missed:
            probs.append(f"{len(missed)} still(s) up to the pick not read, first {missed[0]['name']}")
    valid = not probs
    frame = st["stills"][pick - 1]["frame"] if (valid and pick is not None) else None
    att.update(status="recorded", recorded_utc=blind.now(), read_log=rl, identity=ident,
               stills=[{"name": s["name"], "frame": s["frame"]} for s in st["stills"]], output=out,
               output_sha256=blind.sha256_bytes(text.encode()), problems=probs, valid=valid,
               pick_still=pick if valid else None, pick_frame=frame, **kept)
    if valid:
        step["result"] = {"status": "none" if pick is None else "picked", "still": pick, "frame": frame}
    blind.close_if_spent(step, {"status": "failed", "still": None, "frame": None})
    blind.ledger_save(st, log)
    return log


# --- verify -------------------------------------------------------------------------------------
def _first_frame(prompts, obj) -> int:
    d = blind.loads_strict(Path(prompts).read_text(encoding="utf-8"))
    pts = (d.get("objects") or {}).get(obj) if isinstance(d, dict) else None
    if not pts:
        raise blind.BlindError(f"{Path(prompts).name} has no points for {obj!r}")
    return min(int(p["frame"]) for p in pts)


def verify(render: str, *, prompts=None, prompt_object="creature", video=None, brief=BRIEF,
           agent=blind.PICKER) -> int | None:
    """The logged prompt frame (None when the pick was "none"), after checking the ledger against the
    registry and the frozen files."""
    log = load_log(render)
    if not log:
        raise blind.BlindError(f"{render}: no pick logged")
    blind.check_registry(log, "prompt-frame", render)
    if blind.open_attempts(log):
        raise blind.BlindError(f"{render}: the ledger has an unrecorded attempt")
    res = log["result"]
    if res is None:
        raise blind.BlindError(f"{render}: no pick logged")
    if res["status"] == "failed":
        raise blind.BlindError(f"{render}: both attempts at the pick were invalid")
    if log["brief_sha256"] != blind.sha256_path(brief):
        raise blind.BlindError(f"{render}: the logged brief hash is not the frozen brief's")
    if log["agent_sha256"] != blind.sha256_path(agent):
        raise blind.BlindError(f"{render}: the logged agent hash is not the frozen agent definition's")
    if video is not None and blind.sha256_path(video) != log["video_sha256"]:
        raise blind.BlindError(f"{render}: the video's hash is not the one the pick was made on")
    if res["status"] == "none":
        if prompts is not None:
            raise blind.BlindError(f"{render}: the pick was none (never clear of its home), yet a prompt file is given")
        return None
    if prompts is not None and _first_frame(prompts, prompt_object) != res["frame"]:
        raise blind.BlindError(f"{render}: the prompt file's prompt frame is not the logged pick ({res['frame']})")
    return res["frame"]


# --- CLI ----------------------------------------------------------------------------------------
def load_home(take_masks, render: str, n=None):
    """The acting creature's static home (majority vote of its take track, as seam/controls_inputs.py)."""
    from seam import controls_inputs, masks
    _, m = masks.load_masks(take_masks)
    name = home_name(render)
    if name not in m:
        raise blind.BlindError(f"{Path(take_masks).name} has no {name}")
    return controls_inputs.static_mask(m[name])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python seam/frame_pick.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--video", required=True, help="the render; sampled onto the 1280x720 grid as the masks are")
    p.add_argument("--render", required=True)
    p.add_argument("--take-masks", required=True, help="the take's p47-masks/1 file (its home_<material> track)")
    v = sub.add_parser("verify")
    v.add_argument("--render", required=True)
    v.add_argument("--prompts")
    v.add_argument("--prompt-object", default="creature")
    v.add_argument("--video")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "prepare":
            from seam import masks
            frames = masks.analysis_frames(a.video)
            st = build_folder(frames, render=a.render, home=load_home(a.take_masks, a.render),
                              video_sha256=blind.sha256_path(a.video))
            print(json.dumps({"code": st["code"], "stills": len(st["stills"]),
                              "next": f"python seam/dispatch.py run --code {st['code']}"}, indent=1))
        else:
            f = verify(a.render, prompts=a.prompts, prompt_object=a.prompt_object, video=a.video)
            print(json.dumps({"render": a.render, "prompt_frame": f}))
    except (blind.BlindError, OSError, ValueError) as e:
        print(f"frame_pick: refuse: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
