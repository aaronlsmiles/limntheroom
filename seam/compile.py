"""Compile a cue sheet x laws into a ``p47-render/1`` request for the hub Runway client, plus a
clause trace (``p47-trace/1``: each event -> law id -> clause -> time).

The prompt is a fixed template, line by line:

1. The preamble: keep the camera, framing, timing, desk, page and every object and hand as filmed.
2. The target, named by its position on the page: "The drawing on the left of the page, the ink one,
   comes to life and steps up out of its place on the page." (call 110)
3. One style lock per material on the page, in page order: "The <material> drawing stays <look>."
4. Each resting drawing: "The <material> drawing <position> stays still on the page."
5. Each targeted event, in time order, fires exactly one law: "At <t> s, when <what>, it <clause>."
   Context events (target null) fire nothing and appear in the trace with law null.
6. Models that take a reference image add one sentence pointing at it.

The no-op null's prompt is the fixed ``NOOP_PROMPT``. Output is deterministic (sorted keys, no
timestamps), so compiling twice gives identical bytes.

**Sealing.** A compiled prompt contains law clauses. A request compiled from a laws file inside a
``sealed/`` folder may only be written inside a ``sealed/`` folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from .cues.sheet import dumps, load_sheet, validate_sheet
from .laws import canonical_sha256, get_law, load_laws

ROOT = Path(__file__).resolve().parent.parent
SEALED_DIR = ROOT / "sealed"
COMPILER = "p47-compile/1"
REQUEST_SCHEMA = "p47-render/1"
TRACE_SCHEMA = "p47-trace/1"

PREAMBLE = "Keep the camera, framing, timing, desk, page and every object and hand exactly as filmed."
NOOP_PROMPT = "Change nothing. Keep every object, hand and line exactly as filmed."
REFERENCE_SENTENCE = "It keeps the exact look of the drawing in the reference image."

# capture/takes.json names a take by its prop; the cue sheet names the cue.
TAKE_CUE = {"glass": "water", "torch": "light", "pen": "pen", "breath": "breath", "note": "note", "hand": "hand"}
POSITION = {"left": "on the left of the page", "centre": "in the centre of the page", "right": "on the right of the page"}
POSITION_ORDER = ("left", "centre", "right")

# Per-model request shape (master plan R0.5). Limits are the API's promptText caps in UTF-16 units.
MODELS = {
    "aleph2": {"seed": 1, "options": {}, "references": False, "limit": 1000},
    "kling_4": {"seed": None, "options": {"ratio": "auto_720p"}, "references": True, "limit": 26000},
    # seedance edit renders at the input's tier, so the compiler sends it a 720p copy (the budget's tier).
    "seedance2_5": {"seed": 1, "options": {"mode": "edit", "audio": False}, "references": True, "limit": 15000,
                    "max_height": 720},
    # gemini edit takes at most 10 s of input: the compiler trims longer takes to their first 10 s (R0.5).
    "gemini_omni_flash_1.1": {"seed": None, "options": {"mode": "edit", "ratio": "640:360"}, "references": True,
                              "limit": 4000, "max_input_s": 10},
}


class CompileError(ValueError):
    pass


DRAFT_BEFORE_S = 1.0   # a draft's window starts this long before the firing event (§14; Gate R review note 8, call 136)
DRAFT_SECONDS = 4.0


def draft_window(sheet: dict, material: str, before: float = DRAFT_BEFORE_S, seconds: float = DRAFT_SECONDS):
    """(start s, seconds) of a draft's input, from the cue sheet: it starts `before` s ahead of the first event that
    fires a law for `material` (not before 0 s), so no window is chosen by hand."""
    firing = sorted((e for e in sheet["events"] if e.get("target") == material), key=lambda e: e["t"])
    if not firing:
        raise CompileError(f"the cue sheet has no event that fires a law for {material}")
    return round(max(0.0, float(firing[0]["t"]) - before), 3), float(seconds)


def u16len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def _adapter(model: str) -> dict:
    if model not in MODELS:
        raise CompileError(f"unknown model {model!r}; one of {sorted(MODELS)}")
    return MODELS[model]


def _page_order(page: dict) -> list[str]:
    for m, pos in page.items():
        if pos not in POSITION:
            raise CompileError(f"page: {m} has unknown position {pos!r}; one of {POSITION_ORDER}")
    return sorted(page, key=lambda m: POSITION_ORDER.index(page[m]))


def _fmt_t(t: float) -> str:
    return f"{t:.2f}"


def build_prompt(sheet: dict, laws: dict, take: dict, page: dict, with_reference: bool, clip=None):
    """(prompt, trace clauses, fired law ids). ``clip`` = (start, end) s of a trimmed input: prompt times
    are clip times (take time - start), and a targeted event outside the clip is an error."""
    target = take["target_material"]
    if page.get(target) != take["target_position"]:
        raise CompileError(f"take {take['id']}: {target} is at {take['target_position']!r} in the take list "
                           f"but at {page.get(target)!r} on the page")
    order = _page_order(page)
    for m in order:
        if m not in laws["materials"]:
            raise CompileError(f"laws: no look for material {m!r}")
    lines = [PREAMBLE,
             f"The drawing {POSITION[page[target]]}, the {target} one, comes to life and steps up out of its place on the page."]
    lines += [f"The {m} drawing stays {laws['materials'][m]['look']}." for m in order]
    lines += [f"The {m} drawing {POSITION[page[m]]} stays still on the page." for m in order if m != target]
    clauses, fired = [], []
    c0, c1 = clip if clip is not None else (0.0, None)
    for e in sheet["events"]:      # the sheet is validated, so events are already in time order
        inside = e["t"] >= c0 - 1e-9 and (c1 is None or e["t"] <= c1 + 1e-9)
        t_clip = round(e["t"] - c0, 3) if inside else None
        if e["target"] is None:
            clauses.append({"event": e["id"], "t": e["t"], "t_clip": t_clip, "cue": e["cue"], "law": None,
                            "clause": None})
            continue
        if e["target"] != target:
            raise CompileError(f"event {e['id']} targets {e['target']}, but the take's acting creature is {target}")
        if not inside:
            raise CompileError(f"event {e['id']} at {e['t']} s falls outside the trimmed window {c0:g}-{c1:g} s")
        law = get_law(laws, f"{e['target']}.{e['cue']}")
        text = f"At {_fmt_t(t_clip)} s, when {e['what']}, it {law['clause']}."
        lines.append(text)
        clauses.append({"event": e["id"], "t": e["t"], "t_clip": t_clip, "cue": e["cue"], "law": law["id"],
                        "clause": text})
        fired.append(law["id"])
    if not fired:
        raise CompileError(f"take {take['id']}: no event fires a law (no event has the take's cue and a target)")
    if with_reference:
        lines.append(REFERENCE_SENTENCE)
    return " ".join(lines), clauses, fired


def _request(model, prompt, video, references, video_info, seed, meta):
    ad = _adapter(model)
    n = u16len(prompt)
    if n > ad["limit"]:
        raise CompileError(f"{model}: prompt is {n} characters; the limit is {ad['limit']} (hard failure, no truncation)")
    inputs = {"video": video, "keyframes": [], "references": [{"path": r} for r in references]}
    if video_info is not None:
        inputs["video_info"] = video_info
    meta = dict(meta)
    req = {"schema": REQUEST_SCHEMA, "model": model, "prompt": prompt, "inputs": inputs,
           "options": dict(ad["options"]), "meta": meta}
    s = ad["seed"] if seed is None else seed
    if s is not None and ad["seed"] is not None:
        req["seed"] = s
    meta["seed_policy"] = "fixed" if "seed" in req else "first output"
    return req


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tool(args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, capture_output=True, text=True)
    except FileNotFoundError:
        raise CompileError(f"{args[0]} not found on PATH; install ffmpeg (it ships ffprobe): brew install ffmpeg") from None


def video_seconds(path) -> float:
    r = _tool(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    if r.returncode != 0 or not r.stdout.strip():
        raise CompileError(f"ffprobe could not read {path}: {r.stderr.strip()}")
    return float(r.stdout.strip())


def video_size(path) -> tuple[int, int]:
    r = _tool(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
               "-of", "csv=p=0", str(path)])
    try:
        w, h = r.stdout.strip().split(",")[:2]
        return int(w), int(h)
    except ValueError:
        raise CompileError(f"ffprobe could not read the size of {path}: {r.stderr.strip()}") from None


def prepare_input_for_model(video, model: str, out_dir, window: tuple[float, float] | None = None):
    """(video to send, record or None). Per the model's adapter:

    - ``max_input_s`` (gemini edit: 10 s): a longer take is cut to its first ``max_input_s`` seconds,
      as R0.5 trims the probe. Recorded as ``trim``.
    - ``max_height`` (seedance2_5: 720): a taller take is scaled to that height (width keeps the aspect,
      even), because seedance's edit mode renders and bills at the input's tier (1080p costs 68 + 34
      credits per second; 720p, 30 + 15). Recorded as ``scale``.

    Both happen in one frame-accurate re-encode (libx264 CRF 12, audio kept, metadata stripped) named by
    the source's SHA-256, so an identical preparation is reused rather than re-encoded. aleph2 (flat
    price) and kling_4 (``auto_720p`` sets its tier) are sent as they are.

    ``window`` = (start s, duration s) trims any model's input to that span: the probe's shared 10 s clip
    (``--trim-to``) or a draft's 4 s around the cue (``--window``). It must lie inside the take and within
    the model's ``max_input_s``."""
    video = Path(video)
    ad = _adapter(model)
    limit, max_h = ad.get("max_input_s"), ad.get("max_height")
    src_s = video_seconds(video)
    if window is not None:
        start, dur = window
        if start < 0 or dur <= 0 or start + dur > src_s + 0.05:
            raise CompileError(f"window {start:g}+{dur:g} s does not fit the {src_s:.2f} s take {video.name}")
        if limit is not None and dur > limit + 0.05:
            raise CompileError(f"{model} takes at most {limit} s of input; the window is {dur:g} s")
        trim = True
    else:
        trim = limit is not None and src_s > limit + 0.05
        start, dur = 0, limit
    w, h = video_size(video) if max_h is not None else (None, None)
    scale = max_h is not None and h > max_h
    if not (trim or scale):
        return video, None
    sha = file_sha256(video)
    rec = {}
    tags, args = [], []
    if trim:
        tags.append(f"first{dur:g}s" if start == 0 else f"from{start:g}s.{dur:g}s")
        args += (["-ss", f"{start:g}"] if start else []) + ["-t", f"{dur:g}"]   # -ss after -i: frame-accurate
        rec["trim"] = {"start_s": start, "seconds": dur, "source": video.name, "source_sha256": sha}
    if scale:
        tags.append(f"{max_h}p")
        args += ["-vf", f"scale=-2:{max_h}:flags=lanczos"]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{video.stem}.{sha[:12]}.{'.'.join(tags)}.mp4"
    if not out.exists():
        tmp = out.with_name(out.name + ".part.mp4")
        r = _tool(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(video), *args,
                   "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "12",
                   "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-map_metadata", "-1",
                   "-movflags", "+faststart", str(tmp)])
        if r.returncode != 0:
            tmp.unlink(missing_ok=True)
            raise CompileError(f"ffmpeg preparation of {video.name} failed: {r.stderr.strip()}")
        tmp.replace(out)
    if trim and video_seconds(out) > dur + 0.05:
        raise CompileError(f"{out.name}: trimmed copy is longer than {dur:g} s")
    if scale:
        ow, oh = video_size(out)
        if oh != max_h:
            raise CompileError(f"{out.name}: scaled copy is {ow}x{oh}, not {max_h} px tall")
        rec["scale"] = {"width": ow, "height": oh, "source": video.name, "source_sha256": sha}
    return out, rec


def trim_for_model(video, model: str, out_dir):
    """(video to send, trim record or None): ``prepare_input_for_model`` for the trim alone."""
    out, rec = prepare_input_for_model(video, model, out_dir)
    return out, (rec or {}).get("trim")


def compile_request(sheet: dict, laws: dict, take: dict, *, model: str, video: str, page: dict,
                    reference: str | None = None, video_info: dict | None = None, seed: int | None = None,
                    purpose: str = "final", trim: dict | None = None, scale: dict | None = None):
    """(request, trace) for one take on one model."""
    validate_sheet(sheet)
    ad = _adapter(model)
    if sheet["take"] != take["id"]:
        raise CompileError(f"the sheet is for take {sheet['take']}, the take spec is {take['id']}")
    if take["cue"] not in TAKE_CUE:
        raise CompileError(f"take {take['id']}: cue {take['cue']!r} is not one of {sorted(TAKE_CUE)}")
    if isinstance(take["target_material"], list):
        raise CompileError(f"take {take['id']}: several acting creatures; the compiler handles one")
    use_ref = bool(ad["references"] and reference)
    clip = (trim["start_s"], trim["start_s"] + trim["seconds"]) if trim is not None else None
    prompt, clauses, fired = build_prompt(sheet, laws, take, page, use_ref, clip)
    meta = {"take": take["id"], "material": take["target_material"], "purpose": purpose, "compiler": COMPILER,
            "cue": TAKE_CUE[take["cue"]], "fires": fired, "laws_sha256": canonical_sha256(laws),
            "cues_sha256": canonical_sha256(sheet)}
    if trim is not None:
        meta["trim"] = trim
    if scale is not None:
        meta["scale"] = scale
    req = _request(model, prompt, video, [reference] if use_ref else [], video_info, seed, meta)
    trace = {"schema": TRACE_SCHEMA, "take": take["id"], "material": take["target_material"], "model": model,
             "prompt_chars": u16len(prompt), "clauses": clauses}
    return req, trace


def compile_noop(take: dict, *, model: str, video: str, video_info: dict | None = None, seed: int | None = None,
                 trim: dict | None = None, scale: dict | None = None):
    """The no-op null: the fixed prompt, no references, no clauses."""
    meta = {"take": take["id"], "material": None, "purpose": "noop", "compiler": COMPILER, "fires": []}
    if trim is not None:
        meta["trim"] = trim
    if scale is not None:
        meta["scale"] = scale
    req = _request(model, NOOP_PROMPT, video, [], video_info, seed, meta)
    trace = {"schema": TRACE_SCHEMA, "take": take["id"], "material": None, "model": model,
             "prompt_chars": u16len(NOOP_PROMPT), "clauses": []}
    return req, trace


def trace_path(request_path) -> Path:
    p = Path(request_path)
    return p.with_name(p.stem + ".trace.json")


def in_sealed(path) -> bool:
    """True if ``path`` (resolved) lies inside this repo's own ``sealed/`` folder."""
    return Path(path).resolve().is_relative_to(Path(SEALED_DIR).resolve())


def write_outputs(path, request: dict, trace: dict, laws_path=None) -> tuple[Path, Path]:
    """Write the request and its trace (``<stem>.trace.json``). A request compiled from a laws file
    inside ``sealed/`` carries sealed clauses, so it may only be written inside ``sealed/``."""
    p = Path(path)
    if laws_path is not None and in_sealed(laws_path) and not in_sealed(p):
        raise CompileError(f"{p}: compiled from sealed laws ({laws_path}), so it must be written inside {SEALED_DIR} "
                           "until the rating window closes")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dumps(request), encoding="utf-8")
    t = trace_path(p)
    t.write_text(dumps(trace), encoding="utf-8")
    return p, t


def page_from_takes(takes: list[dict]) -> dict:
    """{material: position} from the take list's several-creature entry (the curtain call)."""
    for t in takes:
        if isinstance(t.get("target_material"), list):
            return dict(zip(t["target_material"], t["target_position"]))
    raise CompileError("the take list has no entry naming all the creatures' positions")


def find_take(takes: list[dict], take_id: str, material: str | None, *, any_material: bool = False) -> dict:
    """The take-list entry for ``take_id`` (and ``material``). With ``any_material``, the first entry
    for the take (the no-op null needs the take, not a creature). Raises CompileError otherwise."""
    if not isinstance(takes, list) or not all(isinstance(t, dict) for t in takes):
        raise CompileError("the take list must be a JSON list of objects")
    hits = [t for t in takes if t.get("id") == take_id and (material is None or t.get("target_material") == material)]
    if hits and any_material:
        return hits[0]
    if len(hits) != 1:
        raise CompileError(f"take {take_id} material {material}: {len(hits)} matching entries in the take list")
    return hits[0]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m seam.compile", description="Compile a cue sheet x laws into a p47-render/1 request.")
    ap.add_argument("--sheet", help="the render's cue sheet: cues/<take>.json, or cues/<take>-<material>.json for the glass take's gold and paper renders (not with --noop)")
    ap.add_argument("--laws", help="laws.json in p47-laws/1 (not with --noop)")
    ap.add_argument("--takes", default=str(ROOT / "capture" / "takes.json"))
    ap.add_argument("--take", required=True)
    ap.add_argument("--material", help="the acting creature (picks the take-list entry)")
    ap.add_argument("--model", required=True, choices=sorted(MODELS))
    ap.add_argument("--video", required=True, help="the render input video; stored relative to --out")
    ap.add_argument("--reference", help="the acting creature's scan crop (models that take references)")
    ap.add_argument("--purpose", default="final")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--noop", action="store_true", help="the no-op null's fixed prompt")
    trims = ap.add_mutually_exclusive_group()
    trims.add_argument("--trim-to", type=float, metavar="SECONDS",
                       help="trim any model's input to SECONDS from --start (the probe's shared 10 s clip, R0.5)")
    trims.add_argument("--window", type=float, nargs=2, metavar=("START", "DUR"),
                       help="trim to DUR seconds from START (fixtures; a registered draft uses --draft-window)")
    trims.add_argument("--draft-window", action="store_true",
                       help="a draft's registered window: 4 s from 1.0 s before the firing event in --sheet (§14)")
    ap.add_argument("--start", type=float, default=0.0, help="start of --trim-to, in take seconds")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.start and a.trim_to is None:
        ap.error("--start goes with --trim-to")
    window = tuple(a.window) if a.window else ((a.start, a.trim_to) if a.trim_to is not None else None)
    if a.draft_window:
        if not (a.sheet and a.material):
            ap.error("--draft-window needs --sheet and --material")
        try:
            window = draft_window(load_sheet(a.sheet), a.material)
        except (CompileError, ValueError, OSError) as e:
            print(f"compile: {e}", file=sys.stderr)
            return 2

    out = Path(a.out)
    rel = lambda p: os.path.relpath(Path(p).resolve(), out.resolve().parent)
    try:
        takes = json.loads(Path(a.takes).read_text(encoding="utf-8"))
        if not Path(a.video).is_file():
            raise CompileError(f"input video not found: {a.video}")
        if a.noop:
            take = find_take(takes, a.take, a.material, any_material=a.material is None)
            vid, prep = prepare_input_for_model(a.video, a.model, out.parent, window=window)
            req, trace = compile_noop(take, model=a.model, video=rel(vid), seed=a.seed, **(prep or {}))
            laws_path = None
        else:
            if not (a.sheet and a.laws):
                ap.error("--sheet and --laws are required unless --noop")
            take = find_take(takes, a.take, a.material)
            vid, prep = prepare_input_for_model(a.video, a.model, out.parent, window=window)
            req, trace = compile_request(load_sheet(a.sheet), load_laws(a.laws), take, model=a.model,
                                         video=rel(vid), page=page_from_takes(takes), **(prep or {}),
                                         reference=rel(a.reference) if a.reference else None, seed=a.seed,
                                         purpose=a.purpose)
            laws_path = a.laws
        p, t = write_outputs(out, req, trace, laws_path=laws_path)
    except (CompileError, ValueError, OSError) as e:      # UnknownLaw and JSON errors are ValueErrors
        print(f"compile: {e}", file=sys.stderr)
        return 2
    print(json.dumps({"request": str(p), "trace": str(t), "prompt_chars": trace["prompt_chars"],
                      "fires": req["meta"]["fires"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
