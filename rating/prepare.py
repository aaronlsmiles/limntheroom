#!/usr/bin/env python3
"""Build the cold-rating studies (R0.8, Phase 9.2) from rendered clips.

    python rating/prepare.py seal  [--laws sealed/laws.json]                      # Gate R, once
    python rating/prepare.py build --inputs rating/inputs.json [--raters 5]       # Phase 9.2

Everything this writes is gitignored: `rating/media/`, `rating/studies/` and `sealed/` (the Q2
options are the sealed laws' labels, so a built study is sealed material until the window closes).

`seal` (Gate R) draws, once, what must not change afterwards, and refuses to overwrite it:
  - `sealed/answer-key.json`: a salt, the blinding seed, the opaque item codes, and the answer key in the
    shape analysis/ratings.py reads;
  - `sealed/q2-options.json`: the Q2 options in a seeded order, "Nothing in particular" and "Can't tell" last.

`build` reads both and never reorders or re-codes. It refuses if the key is missing, if its codes do
not match the clips (the kit derives a code from the seed and the item id), or if the options file
disagrees with the laws. Then, in order:
  1. Rating copies of the rated renders: H.264, 1280x720, one constant frame rate, one frame
     count for all of them (a different length would name the model), no audio, no metadata
     (`-map_metadata -1 -fflags +bitexact`). Each copy is checked: one video stream, identical
     properties, only structural container tags, and no C2PA / JUMBF boxes or bytes. Named by code.
  2. Ringed baseline stills: the take's cue frame, with a thin neutral ring around the creature
     that will act: the row's `ring_bbox` in capture/takes.json (tools/ring_boxes.py derives it from
     the chosen take's home mask). A rated row without one stops the build; there is no placeholder.
     A clip's reference still is this same panel: the kit shows one image per panel, to the baseline
     question and beside the clip.
  3. One study.yaml per rater id (limn-r1 ... limn-rN): choice scales (Q1: 8 options, Q2: from
     q2-options.json), a baseline part and a clips part, `tally: false`, banned terms.
  4. `blindpanel lock`, `build` and `verify --dist` for each study, with the v0.2 CLI.
  5. A manifest (`sealed/rating-manifest.json`) with the hashes of the key, copies and locks.

Nothing is published, deployed or pushed. Inputs file (`p47-rating-inputs/1`), paths relative to it:

    {"schema": "p47-rating-inputs/1",
     "entries": [{"take": "t01", "material": "ink", "render": "...mp4", "take_video": "...mp4",
                  "cues": "cues/t01.json"  |  "cue_s": 2.4}, ...]}

One entry per rated line of capture/takes.json. The cue frame is taken at `cue_s`, else at the start
(`t`) of the cue sheet's event for the take's own cue.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rating.container import (BOX_CONTAINERS, C2PA_UUID, FORBIDDEN_BOXES, LONG_MARKERS, scan_container)  # noqa: E402,F401
from seam.compile import MODELS  # noqa: E402
from seam.cues.sheet import validate_sheet  # noqa: E402
from seam.laws import UnknownLaw, get_law, load_laws  # noqa: E402

INPUTS_SCHEMA = "p47-rating-inputs/1"
KEY_SCHEMA = "p47-answer-key/1"
Q2_SCHEMA = "p47-q2-options/1"
MANIFEST_SCHEMA = "p47-rating-manifest/1"

SIZE = (1280, 720)
FPS = 24
CRF = 16

# --- the registered wording (R0.8). Public: none of it comes from the sealed laws. ---------------
NOTHING = "Nothing in particular"
CANT_TELL = "Can't tell"
Q1_OPTIONS = ["The glass of water", "The torch's light", "The pen", "A breath", "The handwritten note",
              "The hand", NOTHING, CANT_TELL]
# takes.json `cue` -> (law cue, index into Q1_OPTIONS)
CUES = {"glass": ("water", 0), "torch": ("light", 1), "pen": ("pen", 2), "breath": ("breath", 3),
        "note": ("note", 4), "hand": ("hand", 5)}
# Deviation D3 (call 143): §19's failure path rates the glass take x3 (its ink, gold and paper rows) and nothing else.
FAILURE_PATH_CUE = "glass"
FAILURE_PATH_MATERIALS = ("gold", "ink", "paper")
QUESTIONS = {"clip_target": "q1", "clip_behaviour": "q2", "base_target": "q1b", "base_behaviour": "q2b"}
TEXT = {
    "title": "A short rating study",
    "q1b": "If the ringed drawing came alive here, what would it react to?",
    "q2b": "What would it do?",
    "q1": "What did the creature react to?",
    "q2": "What did it do?",
    "baseline_intro": ["First, some **still drawings**, one at a time. Each has one drawing inside a ring.",
                       "Two questions about each. Pick the one option that fits best."],
    "clips_intro": ["Each screen now shows a **still** (left) and a **clip** made from it (right, on a loop).",
                    "Two questions about each clip. Pick the one option that fits best."],
    "watch_note": "Watch the whole clip before answering.",
}

# Words that must not reach a rater before the reveal. Regex lines carry their own flags; the
# lookarounds keep a standalone word from matching inside a hyphenated token (the kit's own CSS has
# `--bp-ink`). Law words are added at run time from the sealed laws file.
MODEL_TERMS = ["runway", "seedance", "bytedance", "aleph", "kling", "kuaishou", "gemini", "veo", "luma",
               "sora", "pika", "hailuo", "minimax", "wan"]
MATERIAL_TERMS = ["ink", "gold", "paper"]
SLUG_TERMS = ["limntheroom", "limn the room", "limn-the-room", "limn_the_room"]

# --- the ring ------------------------------------------------------------------------------------
# Each rated row's `ring_bbox` is its creature's static home box (the majority vote over the chosen take's
# mask frames) padded by RING_PAD_PX on the 1280x720 mask grid. 4 px absorbs a pixel or two of mask edge
# error on a thin ink line; the ellipse (ring_geometry) adds its own room on top. On the registered takes
# that leaves at least 13 px between the stroke and the creature and at least 49 px to the next creature
# (they stand about 85 px apart); a larger pad crowds the pen on t03 without enclosing anything more.
RING_PAD_PX = 4
RING_COLOUR = (138, 138, 138)
RING_WIDTH = 4             # px at 1280 wide
RING_MARGIN = 1.08

ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"


class PrepareError(Exception):
    pass


# =============================================================================================
# opaque codes (the kit's scheme, src/core/codes.ts)
# =============================================================================================
def opaque_code(seed: str, kind: str, item_id: str) -> str:
    d = hashlib.sha256(f"{seed}:code:{kind}:{item_id}".encode()).digest()
    bits = int.from_bytes(d[:4], "big")
    out = ""
    for _ in range(5):
        out += ALPHABET[(bits >> 27) & 31]
        bits = (bits << 5) & 0xFFFFFFFF
    return ("c" if kind == "clip" else "p") + out


def assign_codes(seed: str, kind: str, ids, keyed=None) -> dict:
    """{key: code}; the key is the id itself, or `keyed[i]` (the ref) when given."""
    out, seen = {}, {}
    for n, i in enumerate(ids):
        k = keyed[n] if keyed else i
        if k in out:
            raise PrepareError(f"duplicate {kind} id {k}")
        c = opaque_code(seed, kind, i)
        if c in seen:
            raise PrepareError(f"code collision between {seen[c]} and {k}; change the salt")
        seen[c] = k
        out[k] = c
    return out


# =============================================================================================
# ffmpeg / ffprobe
# =============================================================================================
def _run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, **kw)
    if r.returncode:
        err = r.stderr.decode("utf-8", "replace")[-800:]
        raise PrepareError(f"{cmd[0]} failed ({r.returncode}): {err}")
    return r


def ffmpeg_version() -> str:
    return _run(["ffmpeg", "-version"]).stdout.decode().splitlines()[0]


def probe(path) -> dict:
    """ffprobe's streams and format, plus the decoded frame count of the first video stream."""
    r = _run(["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(path)])
    d = json.loads(r.stdout)
    return d


def video_facts(path) -> dict:
    d = probe(path)
    v = [s for s in d["streams"] if s.get("codec_type") == "video"]
    if not v:
        raise PrepareError(f"{Path(path).name}: no video stream")
    s = v[0]
    num, _, den = s.get("avg_frame_rate", "0/1").partition("/")
    fps = Fraction(int(num), int(den or 1)) if int(den or 1) else Fraction(0)
    nb = int(s.get("nb_read_frames") or s.get("nb_frames") or 0)
    dur = float(s.get("duration") or d["format"].get("duration") or 0)     # the video's own length, not the audio's
    return {"width": s["width"], "height": s["height"], "fps": fps, "frames": nb, "duration": dur,
            "streams": len(d["streams"])}


def available_frames(source, fps: int) -> int:
    """Frames a source can give at `fps` (its video's own length, rounded down)."""
    return int(math.floor(video_facts(source)["duration"] * fps + 1e-6))


REGISTERED_SECONDS = 12.0   # call 135: the rating copies' length is fixed before any render is seen


def common_frames(sources, fps: int, seconds: float | None = None, frames: int | None = None) -> int:
    """How many frames every rating copy gets. The registered rule (call 135), used when no length is given:
    REGISTERED_SECONDS, or the shortest source's full length if any is shorter, so no length is chosen after the
    renders are seen (an explicit length is for fixtures, and shows in the A2 addendum). A source shorter than an
    explicit length is refused (it would be padded, and an unequal length names the model)."""
    if not frames and not seconds:
        return max(1, min([int(round(REGISTERED_SECONDS * fps))] + [available_frames(src, fps) for src in sources]))
    n = int(frames) if frames else int(round(seconds * fps))
    if n < 1:
        raise PrepareError("the chosen length is under one frame")
    short = [Path(src).name for src in sources if available_frames(src, fps) < n]
    if short:
        raise PrepareError(f"{len(short)} source(s) are shorter than the chosen length of {n} frames: {short}")
    return n


def describe_lengths(sources, fps: int, n: int) -> list[str]:
    """One line per source with its own length, then the chosen length."""
    lines = []
    for src in sources:
        f = video_facts(src)
        lines.append(f"  {Path(src).name}: {f['duration']:.2f} s, {available_frames(src, fps)} frames at {fps} fps")
    lines.append(f"  chosen: {n} frames at {fps} fps = {n / fps:.2f} s")
    return lines


def make_rating_copy(src, dst, *, fps=FPS, frames: int, size=SIZE):
    w, h = size
    vf = (f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos:"
          f"out_color_matrix=bt709:out_range=tv,crop={w}:{h},setsar=1,format=yuv420p")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-map", "0:v:0", "-an", "-sn", "-dn",
          "-map_metadata", "-1", "-map_chapters", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact",
          "-metadata:s:v:0", "encoder=", "-vf", vf, "-frames:v", str(frames),
          "-c:v", "libx264", "-preset", "slow", "-crf", str(CRF), "-pix_fmt", "yuv420p",
          "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
          "-threads", "1", "-x264-params", "threads=1:colorprim=bt709:transfer=bt709:colormatrix=bt709:range=tv",
          "-fps_mode", "cfr", "-r", str(fps),
          "-movflags", "+faststart", str(dst)])
    return Path(dst)


# =============================================================================================
# the container check: no C2PA, JUMBF, XMP or metadata in a rating copy
# =============================================================================================
OK_STREAM_TAGS = {"language": {"und"}, "handler_name": {"VideoHandler"}}
OK_FORMAT_TAGS = {"major_brand", "minor_version", "compatible_brands"}


def check_rating_copy(path, *, size=SIZE, fps=FPS, frames: int, banned=()) -> dict:
    """Raise PrepareError unless `path` is a clean rating copy; return its comparable facts."""
    name = Path(path).name
    d = probe(path)
    probs = []
    streams = d["streams"]
    if len(streams) != 1 or streams[0].get("codec_type") != "video":
        probs.append(f"{len(streams)} streams (want one video stream)")
    s = streams[0] if streams else {}
    want = {"codec_name": "h264", "width": size[0], "height": size[1], "pix_fmt": "yuv420p",
            "r_frame_rate": f"{fps}/1", "avg_frame_rate": f"{fps}/1", "color_space": "bt709",
            "color_primaries": "bt709", "color_transfer": "bt709", "color_range": "tv"}
    for k, v in want.items():
        if s.get(k) != v:
            probs.append(f"{k} is {s.get(k)!r}, want {v!r}")
    nb = int(s.get("nb_read_frames") or 0)
    if nb != frames:
        probs.append(f"{nb} frames, want {frames}")
    for k, v in (s.get("tags") or {}).items():
        if k not in OK_STREAM_TAGS or v not in OK_STREAM_TAGS[k]:
            probs.append(f"stream tag {k}")
    for k in (d["format"].get("tags") or {}):
        if k not in OK_FORMAT_TAGS:
            probs.append(f"format tag {k}")
    if d.get("chapters"):
        probs.append("chapters")
    probs += scan_container(path, banned)
    if probs:
        raise PrepareError(f"{name}: " + "; ".join(probs))
    return {k: s.get(k) for k in list(want) + ["profile", "level"]} | {"frames": nb, "duration": s.get("duration")}


# =============================================================================================
# stills and the ring
# =============================================================================================
def extract_frame(video, t: float, size=SIZE):
    from PIL import Image
    w, h = size
    r = _run(["ffmpeg", "-v", "error", "-i", str(video), "-ss", f"{t:.3f}", "-frames:v", "1",
              "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h}",
              "-f", "image2pipe", "-vcodec", "png", "-"])
    if not r.stdout:
        raise PrepareError(f"{Path(video).name}: no frame at {t:.3f} s")
    return Image.open(io.BytesIO(r.stdout)).convert("RGB")


def ring_geometry(bbox, size=SIZE, margin=RING_MARGIN):
    """The ring's ellipse as (cx, cy, a, b) in pixels: the smallest ellipse of the box's shape that
    encloses the box, with a margin. `bbox` is (x0, y0, x1, y1) as fractions of the frame."""
    x0, y0, x1, y1 = bbox
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise PrepareError(f"ring_bbox {bbox} is not x0<x1, y0<y1 within 0..1")
    w, h = size
    return ((x0 + x1) / 2 * w, (y0 + y1) / 2 * h, (x1 - x0) / 2 * w * math.sqrt(2) * margin,
            (y1 - y0) / 2 * h * math.sqrt(2) * margin)


def draw_ring(img, bbox, *, colour=RING_COLOUR, width=RING_WIDTH):
    """A copy of `img` with a thin anti-aliased ring around `bbox`; every pixel away from the ring is untouched."""
    from PIL import Image, ImageDraw
    cx, cy, a, b = ring_geometry(bbox, img.size)
    pad = width + 2
    x0, y0 = max(0, int(cx - a - pad)), max(0, int(cy - b - pad))
    x1, y1 = min(img.width, int(cx + a + pad) + 1), min(img.height, int(cy + b + pad) + 1)
    k = 4
    mask = Image.new("L", ((x1 - x0) * k, (y1 - y0) * k), 0)
    ImageDraw.Draw(mask).ellipse([(cx - a - x0) * k, (cy - b - y0) * k, (cx + a - x0) * k, (cy + b - y0) * k],
                                 outline=255, width=width * k)
    mask = mask.resize((x1 - x0, y1 - y0), Image.LANCZOS)
    out = img.copy()
    out.paste(Image.new("RGB", mask.size, colour), (x0, y0), mask)
    return out


def save_png(img, path):
    """A PNG with no text chunks, so nothing but pixels."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG", optimize=True)
    return Path(path)


def ring_box(take: dict) -> tuple:
    """The row's own `ring_bbox` (x0, y0, x1, y1, fractions of the frame). No placeholder: a rated row
    without a valid box is refused, since a guessed ring can circle the wrong drawing."""
    who = f"{take.get('id')}/{take.get('target_material')}"
    box = take.get("ring_bbox")
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        raise PrepareError(f"{who}: no ring_bbox [x0, y0, x1, y1] in takes.json; derive it from the home mask "
                           "with tools/ring_boxes.py --write")
    try:
        box = tuple(float(v) for v in box)
        ring_geometry(box)
    except (TypeError, ValueError, PrepareError) as e:
        raise PrepareError(f"{who}: bad ring_bbox {take['ring_bbox']}: {e}") from None
    return box


def ring_bbox_from_mask(home, pad_px: int = RING_PAD_PX) -> tuple:
    """The ring's box for one static home mask (H, W) on the registered 1280x720 grid: the mask's bounding
    box padded by `pad_px` and clamped to the frame, as fractions (x0, y0, x1, y1) rounded to 4 places."""
    import numpy as np
    m = np.asarray(home, bool)
    if m.shape != (SIZE[1], SIZE[0]):
        raise PrepareError(f"a home mask of shape {m.shape} is not on the {SIZE[0]}x{SIZE[1]} grid")
    ys, xs = np.nonzero(m)
    if not len(xs):
        raise PrepareError("the home mask is empty; it has no box")
    w, h = SIZE
    x0, y0 = max(0, int(xs.min()) - pad_px), max(0, int(ys.min()) - pad_px)
    x1, y1 = min(w, int(xs.max()) + 1 + pad_px), min(h, int(ys.max()) + 1 + pad_px)
    return (round(x0 / w, 4), round(y0 / h, 4), round(x1 / w, 4), round(y1 / h, 4))


# =============================================================================================
# banned terms
# =============================================================================================
def parse_banned(text: str):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.fullmatch(r"/(.+)/([a-z]*)", line)
        if m:
            flags = re.I if "i" in m.group(2) else 0
            # the kit's JS regex syntax is close enough to Python's for these lines (lookarounds, \b, classes)
            out.append(re.compile(m.group(1), flags))
        else:
            out.append(line)
    return out


def find_banned(text: str, banned) -> list[int]:
    """Indices of the banned entries found in `text` (indices, so a message never prints sealed words)."""
    low = text.lower()
    return [i for i, b in enumerate(banned) if (b.lower() in low if isinstance(b, str) else b.search(text))]


def _term_line(term: str) -> str:
    term = " ".join(term.split())
    if term.startswith("#") or (term.startswith("/") and term.rstrip("abcdefghijklmnopqrstuvwxyz").endswith("/")):
        raise PrepareError("a law string looks like a comment or a regex in banned-terms.txt; reword it")
    return term


def banned_lines(laws: dict, extra=(), strict_materials=False) -> list[str]:
    """The banned-terms file, line by line: model names and ids, material names, the slug, and the law words.

    The dist scan (banned-terms.txt) keeps a standalone-word match for the materials, so the kit's own CSS
    (`--bp-ink`) passes. The check on the wording a rater reads (`strict_materials`) matches the material at
    the start of any word, hyphenated or not: `t01-ink`, `inky` and `ink-stained` all hit."""
    lines = ["# Never shipped. Generated by rating/prepare.py; the law words come from the sealed laws file.",
             "# models"]
    lines += [f"/(?<![\\w-]){re.escape(m)}(?![\\w-])/i" for m in MODEL_TERMS]
    lines += ["# exact model ids, as plain substrings", *MODELS]
    material = ("/\\b(" + "|".join(MATERIAL_TERMS) + ")/i") if strict_materials else \
        ("/(?<![\\w-])(" + "|".join(MATERIAL_TERMS) + ")(?![\\w-])/i")
    lines += ["# materials", material, "# the project", *SLUG_TERMS,
              "# law words (clause, behaviour, look, id)"]
    law_words = []
    for law in laws["laws"]:
        law_words += [law["id"], law["clause"]]
        law_words += [s.strip() for s in re.split(r"(?<=[.!?])\s+", law["behaviour"]) if len(s.strip()) >= 6]
    law_words += [m["look"] for m in laws["materials"].values()]
    seen = set()
    for w in law_words:
        w = _term_line(w)
        if len(w) >= 6 and w.lower() not in seen:
            seen.add(w.lower())
            lines.append(w)
    lines += list(extra)
    return lines


# =============================================================================================
# the studies
# =============================================================================================
def q2_labels(laws: dict) -> list[str]:
    """The 8 rated laws' labels and the two decoys (unordered), checked for markup and repeats."""
    labels = [law["label"].strip() for law in laws["laws"] if law["rated"]] + [d.strip() for d in laws["decoys"]]
    for lab in labels + Q1_OPTIONS:
        if "**" in lab or "<" in lab or ">" in lab:
            raise PrepareError("an option label holds markup (** < >); the export would not match the key")
    if len({x.lower() for x in labels + [NOTHING, CANT_TELL]}) != len(labels) + 2:
        raise PrepareError("two Q2 options are the same label")
    if not 2 <= len(labels) + 2 <= 12:
        raise PrepareError(f"Q2 has {len(labels) + 2} options; the kit allows 2 to 12")
    return labels


def follows_q1_order(order, laws: dict) -> bool:
    """True if the rated laws' labels appear in the Q1 order of their cues (decoys ignored): a rater could then
    match a Q2 option to a cue by position (§17)."""
    q1 = {law_cue: i for law_cue, i in CUES.values()}
    cue = {law["label"].strip(): q1[law["cue"]] for law in laws["laws"] if law["rated"]}
    idx = [cue[o] for o in order if o in cue]
    return all(a <= b for a, b in zip(idx, idx[1:]))


def draw_q2_options(laws: dict, seed: str) -> list[str]:
    """Gate R: the seeded shuffle, drawn once; the two fixed options stay last. If the shuffle lists the rated
    labels in the Q1 order, it is redrawn from "<seed>:1", then ":2" and so on: still a function of the seed alone
    (call 135)."""
    base = q2_labels(laws)
    for k in range(1000):
        key = seed if k == 0 else f"{seed}:{k}"
        labels = sorted(base, key=lambda s: hashlib.sha256(f"{key}:q2order:{s}".encode()).hexdigest())
        if not follows_q1_order(labels, laws):
            return labels + [NOTHING, CANT_TELL]
    raise PrepareError("no Q2 order that does not follow the Q1 order")


def read_q2_options(path, laws: dict) -> list[str]:
    """The options exactly as sealed. They must be the laws' labels and decoys plus the two fixed ones."""
    p = Path(path)
    if not p.exists():
        raise PrepareError(f"{p.name} is missing: run `prepare.py seal` at Gate R first")
    d = json.loads(p.read_text())
    opts = d.get("options") if isinstance(d, dict) and d.get("schema") == Q2_SCHEMA else None
    if not isinstance(opts, list) or not all(isinstance(o, str) for o in opts):
        raise PrepareError(f"{p.name}: want schema {Q2_SCHEMA} with an options list")
    if opts[-2:] != [NOTHING, CANT_TELL] or sorted(opts[:-2]) != sorted(q2_labels(laws)):
        raise PrepareError(f"{p.name} disagrees with the laws file or does not end with the two fixed options")
    return opts


def build_study(study_id, *, seed, instrument, q2, items, fps, frames, media_base="../../media/") -> dict:
    """The study.yaml content as a dict. `items`: [{id, ref, clip_file, clip_sha, panel_file, panel_sha}]."""
    n = len(items)
    return {
        "blindpanel": 1, "id": study_id, "title": TEXT["title"], "instrument": instrument,
        "media": {"base": media_base, "origins": []},
        "blinding": {"seed": seed, "banned_terms_file": "banned-terms.txt"},
        "scales": {"reacts": {"kind": "choice", "labels": Q1_OPTIONS}, "acts": {"kind": "choice", "labels": q2}},
        "questions": [
            {"id": QUESTIONS["base_target"], "short": "Would react to", "part": "baseline", "text": TEXT["q1b"], "scale": "reacts"},
            {"id": QUESTIONS["base_behaviour"], "short": "Would do", "part": "baseline", "text": TEXT["q2b"], "scale": "acts"},
            {"id": QUESTIONS["clip_target"], "short": "Reacted to", "part": "clips", "text": TEXT["q1"], "scale": "reacts"},
            {"id": QUESTIONS["clip_behaviour"], "short": "Did", "part": "clips", "text": TEXT["q2"], "scale": "acts"},
        ],
        "parts": {
            "baseline": {"intro": TEXT["baseline_intro"]},
            "clips": {"intro": TEXT["clips_intro"], "watch_note": TEXT["watch_note"],
                      "clip_seconds": frames / fps, "session_size": n, "extend": False,
                      "video": {"loop": True, "autoplay": "unless_reduced_motion"}},
        },
        "items": {
            "panels": [{"id": it["kit_id"], "ref": it["ref"], "file": it["panel_file"], "sha256": it["panel_sha"]} for it in items],
            "clips": [{"id": it["kit_id"], "ref": it["ref"], "reference": it["kit_id"], "file": it["clip_file"],
                       "sha256": it["clip_sha"], "label": it["clip_code"], "meta": {}} for it in items],
        },
        "modes": {"public": {"submit": True, "tally": False, "min_crowd_n": 1}},
    }


def public_wording(study: dict) -> str:
    """Everything of a study a rater can read before the reveal."""
    keep = {k: study[k] for k in ("title", "scales", "questions")} | {"parts": study["parts"]}
    return json.dumps(keep, ensure_ascii=False)


def write_study(path, study: dict):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # JSON is valid YAML, and it needs no quoting rules for labels like "Can't tell"
    Path(path).write_text("# Generated by rating/prepare.py. Sealed until the rating window closes.\n"
                          + json.dumps(study, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def seed_from_salt(salt: str) -> str:
    return "s" + hashlib.sha256(f"seed:{salt}".encode()).hexdigest()[:24]


def kit_id(salt: str, ref: str) -> str:
    """The id the kit sees for an item. The kit ships the seed and hashes (seed, kind, id) into the code,
    so a human-readable id like t01-ink could be recovered by anyone; this one needs the sealed salt."""
    return "i" + hashlib.sha256(f"{salt}:{ref}".encode()).hexdigest()[:10]


def answer_key(salt, seed, items) -> dict:
    """The sealed key. `clips` and `baseline` are what analysis/ratings.py reads; `ids` and `codes` are the assignment."""
    clips = {e["ref"]: {"law": e["law"], "target": e["target"], "behaviour": e["behaviour"]} for e in items}
    ids = {e["ref"]: kit_id(salt, e["ref"]) for e in items}
    return {"schema": KEY_SCHEMA, "salt": salt, "seed": seed, "questions": dict(QUESTIONS), "ids": ids,
            "codes": {"clips": assign_codes(seed, "clip", [ids[e["ref"]] for e in items], keyed=[e["ref"] for e in items]),
                      "panels": assign_codes(seed, "panel", [ids[e["ref"]] for e in items], keyed=[e["ref"] for e in items])},
            "clips": clips, "baseline": json.loads(json.dumps(clips))}


def read_key(path, items) -> dict:
    """The sealed key, checked against the clips about to be built. Never makes or changes codes."""
    p = Path(path)
    if not p.exists():
        raise PrepareError(f"{p.name} is missing: run `prepare.py seal` at Gate R first")
    key = json.loads(p.read_text())
    if key.get("schema") != KEY_SCHEMA or not all(k in key for k in ("salt", "seed", "ids", "codes", "clips", "baseline", "questions")):
        raise PrepareError(f"{p.name}: not a {KEY_SCHEMA} key")
    refs = sorted(e["ref"] for e in items)
    if sorted(key["clips"]) != refs or sorted(key["baseline"]) != refs:
        raise PrepareError(f"{p.name}: its clips are not the rated takes {refs}")
    ids = key["ids"]
    if not isinstance(ids, dict) or sorted(ids) != refs:
        raise PrepareError(f"{p.name}: ids do not cover the clips")
    for e in items:
        if ids[e["ref"]] != kit_id(key["salt"], e["ref"]):
            raise PrepareError(f"{p.name}: the kit id for {e['ref']} is not derived from the salt")
    for part, kind in (("clips", "clip"), ("panels", "panel")):
        have = key["codes"].get(part)
        if not isinstance(have, dict) or sorted(have) != refs:
            raise PrepareError(f"{p.name}: codes.{part} do not cover the clips")
        for e in items:
            if have[e["ref"]] != opaque_code(key["seed"], kind, ids[e["ref"]]):
                raise PrepareError(f"{p.name}: the code for {e['ref']} ({part}) is not the kit's code for that seed and id")
        if len(set(have.values())) != len(have):
            raise PrepareError(f"{p.name}: two {part} share a code")
    for e in items:
        want = {"law": e["law"], "target": e["target"], "behaviour": e["behaviour"]}
        if key["clips"][e["ref"]] != want or key["baseline"][e["ref"]] != want:
            raise PrepareError(f"{p.name}: the answer for {e['ref']} disagrees with the takes and laws")
    return key


# =============================================================================================
# inputs
# =============================================================================================
def sha256_file(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def rated_items(takes, laws) -> list[dict]:
    """The rated lines of capture/takes.json joined with their laws: refs and the answers. No files."""
    try:
        return _rated_items(takes, laws)
    except KeyError as e:
        if isinstance(e, UnknownLaw):
            raise
        raise PrepareError(f"takes.json: a rated entry lacks {e}") from None


def _rated_items(takes, laws) -> list[dict]:
    rated = [t for t in takes if t.get("rated")]
    for t in rated:
        if not isinstance(t.get("target_material"), str):
            raise PrepareError(f"{t['id']}: a rated take needs one target_material")
    keys = [(t["id"], t["target_material"]) for t in rated]
    if len(set(keys)) != len(keys):
        raise PrepareError("takes.json: a rated take and material appear twice")
    out, law_ids = [], {}
    for t in rated:
        if t["cue"] not in CUES:
            raise PrepareError(f"{t['id']}: cue {t['cue']!r} is not one of {sorted(CUES)}")
        lawcue, qi = CUES[t["cue"]]
        law_id = f"{t['target_material']}.{lawcue}"
        try:
            law = get_law(laws, law_id)
        except KeyError:
            raise PrepareError(f"take {t['id']}/{t['target_material']} needs law {law_id}, which the laws file lacks") from None
        if not law["rated"]:
            raise PrepareError(f"{law_id} is not a rated law")
        law_ids[law_id] = t["id"]
        out.append({"take": t, "ref": f"{t['id']}-{t['target_material']}",
                    "lawcue": lawcue, "law": law_id, "target": Q1_OPTIONS[qi], "behaviour": law["label"].strip()})
    rated_laws = {law["id"] for law in laws["laws"] if law["rated"]}
    if rated_laws != set(law_ids):
        raise PrepareError(f"rated laws and rated takes disagree: laws without a take {sorted(rated_laws - set(law_ids))}, "
                           f"takes without a rated law {sorted(set(law_ids) - rated_laws)}")
    return out


def failure_path_items(items) -> list[dict]:
    """D3 (call 143): the glass take x3 out of the rated items: one take on the glass cue, with exactly its ink, gold
    and paper rows."""
    glass = [i for i in items if i["take"]["cue"] == FAILURE_PATH_CUE]
    if (len({i["take"]["id"] for i in glass}) != 1
            or sorted(i["take"]["target_material"] for i in glass) != sorted(FAILURE_PATH_MATERIALS)):
        raise PrepareError(f"the failure path needs one glass take with exactly its {', '.join(FAILURE_PATH_MATERIALS)} "
                           f"rows; the rated takes give {sorted(i['ref'] for i in glass)}")
    return glass


def load_inputs(path, takes, laws, failure_path=False) -> list[dict]:
    """Join the rated items with the inputs file's files and cue times; check they agree. With `failure_path` (D3), the
    items are the glass take x3 only."""
    try:
        return _load_inputs(path, takes, laws, failure_path)
    except KeyError as e:
        if isinstance(e, UnknownLaw):
            raise
        raise PrepareError(f"{Path(path).name}: an entry lacks {e}") from None


def _load_inputs(path, takes, laws, failure_path=False) -> list[dict]:
    path = Path(path)
    doc = json.loads(path.read_text())
    if doc.get("schema") != INPUTS_SCHEMA or not isinstance(doc.get("entries"), list):
        raise PrepareError(f"{path.name}: schema must be {INPUTS_SCHEMA} with an entries list")
    base = path.parent
    got = {}
    for e in doc["entries"]:
        k = (e.get("take"), e.get("material"))
        if k in got:
            raise PrepareError(f"inputs: {k[0]}/{k[1]} appears twice")
        got[k] = e
    items = rated_items(takes, laws)
    if failure_path:
        items = failure_path_items(items)
    keys = [(i["take"]["id"], i["take"]["target_material"]) for i in items]
    extra, missing = sorted(set(got) - set(keys)), sorted(set(keys) - set(got))
    if failure_path and (extra or missing):
        raise PrepareError(f"the failure path rates the glass take x3 only: missing {missing}, not on it {extra}")
    if extra or missing:
        raise PrepareError(f"inputs and takes.json disagree: missing {missing}, not rated {extra}")
    out = []
    for it in items:
        t = it["take"]
        e = got[(t["id"], t["target_material"])]
        render, tv = (base / e["render"]), (base / e["take_video"])
        for p in (render, tv):
            if not p.exists():
                raise PrepareError(f"{e['take']}/{e['material']}: missing {p.name}")
        cue_s = e.get("cue_s")
        if cue_s is None:
            if not e.get("cues"):
                raise PrepareError(f"{t['id']}/{t['target_material']}: give cue_s or a cues sheet")
            cue_s = cue_time(base / e["cues"], it["lawcue"], t["target_material"])
        out.append({**it, "render": render, "take_video": tv, "cue_s": float(cue_s), "ring_bbox": ring_box(t)})
    return out


def cue_time(sheet_path, lawcue: str, material: str) -> float:
    """The start of the take's own cue event aimed at `material`. No fallback to another material's event."""
    s = validate_sheet(json.loads(Path(sheet_path).read_text()))
    evs = [e for e in s["events"] if e["cue"] == lawcue]
    if not evs:
        raise PrepareError(f"{Path(sheet_path).name}: no {lawcue} event")
    own = [e for e in evs if e["target"] == material]
    if not own:
        raise PrepareError(f"{Path(sheet_path).name}: no {lawcue} event aimed at {material} (its events aim at "
                           f"{sorted({str(e['target']) for e in evs})}); give cue_s for this entry")
    return min(e["t"] for e in own)


# =============================================================================================
# blindpanel
# =============================================================================================
def blindpanel(cli, *args):
    r = subprocess.run(["node", str(cli), *map(str, args)], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def lock_build_verify(cli, study_dir: Path, *, force_lock=False) -> dict:
    y = study_dir / "study.yaml"
    out = {}
    for step, args in (("validate", ["validate", y]), ("lock", ["lock", y] + (["--force"] if force_lock else [])),
                       ("build", ["build", y, "--out", study_dir / "dist"]),
                       ("verify", ["verify", y, "--dist", study_dir / "dist"])):
        code, text = blindpanel(cli, *args)
        out[step] = text
        if code:
            raise PrepareError(f"blindpanel {step} failed for {study_dir.name} (exit {code}):\n{text}")
    return out


def check_built(study_dir: Path, codes_clip, codes_panel, n_items, q2):
    """Our own checks on the built site, beyond verify: tally off, labels are codes, media are code-named."""
    dist = study_dir / "dist"
    study = json.loads((dist / "study.json").read_text())
    if study["modes"]["public"]["tally"] is not False:
        raise PrepareError("built study has tally on")
    reveal = json.loads((dist / "reveal.json").read_text())
    if set(reveal["items"]) != set(codes_clip) or any(v["label"] != k or v["meta"] for k, v in reveal["items"].items()):
        raise PrepareError("reveal.json is not codes only")
    if reveal.get("reference") is not None:
        raise PrepareError("reveal.json carries a reference panel")
    files = sorted(p.name for p in (dist / "media").iterdir())
    want = sorted([c + ".mp4" for c in codes_clip] + [c + ".png" for c in codes_panel])
    if files != want:
        raise PrepareError("dist/media is not exactly the code-named files")
    if study["scales"]["acts"]["labels"] != q2 or len(study["parts"]["clips"]["items"]) != n_items:
        raise PrepareError("built study differs from the plan")


# =============================================================================================
# the run
# =============================================================================================
def write_pair_atomically(files: dict):
    """Write every file or none: temp files first, then os.replace each; on any failure the old files are put back
    and the temp files removed."""
    tmps, old = {}, {}
    try:
        for path, text in files.items():
            tmp = path.with_name(f".{path.name}.tmp")
            tmp.write_text(text)
            tmps[path] = tmp
            old[path] = path.read_bytes() if path.exists() else None
        for path, tmp in tmps.items():
            os.replace(tmp, path)
    except BaseException:
        for path, was in old.items():
            if was is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(was)
        raise
    finally:
        for tmp in tmps.values():
            tmp.unlink(missing_ok=True)


def seal(a) -> dict:
    """Gate R: draw the salt, seed, codes and Q2 order once, and write them under sealed/."""
    sealed = Path(a.sealed).resolve()
    keyfile, qfile = sealed / "answer-key.json", sealed / "q2-options.json"
    if (keyfile.exists() or qfile.exists()) and not a.force:
        raise PrepareError("sealed/answer-key.json or q2-options.json exists; they are drawn once (--force to redraw, "
                           "which changes every code)")
    laws = load_laws(a.laws)
    items = rated_items(json.loads(Path(a.takes).read_text()), laws)
    salt = secrets.token_hex(16)
    seed = seed_from_salt(salt)
    sealed.mkdir(parents=True, exist_ok=True)
    write_pair_atomically({keyfile: json.dumps(answer_key(salt, seed, items), indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                           qfile: json.dumps({"schema": Q2_SCHEMA, "options": draw_q2_options(laws, seed)}, indent=1,
                                             ensure_ascii=False) + "\n"})
    return {"key_sha256": sha256_file(keyfile), "q2_sha256": sha256_file(qfile), "items": len(items)}


def prepare(a) -> dict:
    out = Path(a.out).resolve()
    sealed = Path(a.sealed).resolve()
    media = out / "media"
    studies = out / "studies"
    laws = load_laws(a.laws)
    takes = json.loads(Path(a.takes).read_text())
    entries = load_inputs(a.inputs, takes, laws, failure_path=a.failure_path)
    if not a.no_blindpanel and not a.blindpanel:
        raise PrepareError("no blindpanel CLI: set BLINDPANEL_CLI or pass --blindpanel (bin/blindpanel.mjs in the blindpanel "
                           "repository checked out at tag v0.2.0, §3)")
    cli = Path(a.blindpanel) if a.blindpanel else None
    if not a.no_blindpanel and not cli.exists():
        raise PrepareError(f"blindpanel CLI not found at {cli}; pass --blindpanel")

    # the sealed assignment: read, checked, never changed
    keyfile = sealed / "answer-key.json"
    key = read_key(keyfile, rated_items(takes, laws))     # the whole sealed key, also on the failure path (D3)
    salt, seed = key["salt"], key["seed"]
    clip_codes = {e["ref"]: key["codes"]["clips"][e["ref"]] for e in entries}
    panel_codes = {e["ref"]: key["codes"]["panels"][e["ref"]] for e in entries}
    q2 = read_q2_options(sealed / "q2-options.json", laws)

    # banned terms, and a look at the wording before anything is built
    lines = banned_lines(laws, extra=_extra_banned(a.banned_extra))
    banned = parse_banned("\n".join(lines))
    wording_banned = parse_banned("\n".join(banned_lines(laws, extra=_extra_banned(a.banned_extra), strict_materials=True)))
    hits = find_banned(public_wording(build_study("x", seed=seed, instrument="1", q2=q2, items=[], fps=a.fps, frames=a.fps,
                                                   media_base="")), wording_banned)
    if hits:
        raise PrepareError(f"the wording a rater reads matches banned entries #{hits} of banned-terms.txt "
                           "(a Q2 label that uses a material name or a law's own phrasing?); reword it")

    # rating copies
    sources = [e["render"] for e in entries]
    n_frames = common_frames(sources, a.fps, a.seconds, a.frames)
    print("rating copy length:\n" + "\n".join(describe_lengths(sources, a.fps, n_frames)))
    if media.exists():
        for p in media.iterdir():
            p.unlink()
    items, facts = [], {}
    for e in entries:
        cdst = make_rating_copy(e["render"], media / f"{clip_codes[e['ref']]}.mp4", fps=a.fps, frames=n_frames)
        facts[e["ref"]] = check_rating_copy(cdst, fps=a.fps, frames=n_frames, banned=banned)
        bbox = e["ring_bbox"]                    # checked by load_inputs, before anything was encoded
        still = draw_ring(extract_frame(e["take_video"], e["cue_s"]), bbox)
        pdst = save_png(still, media / f"{panel_codes[e['ref']]}.png")
        items.append({**e, "kit_id": key["ids"][e["ref"]], "clip_code": clip_codes[e["ref"]], "panel_code": panel_codes[e["ref"]],
                      "clip_file": cdst.name, "panel_file": pdst.name,
                      "clip_sha": sha256_file(cdst), "panel_sha": sha256_file(pdst), "ring_bbox": list(bbox)})
    keys = {tuple(sorted((k, str(v)) for k, v in f.items() if k not in ("duration",))) for f in facts.values()}
    if len(keys) != 1:
        raise PrepareError("rating copies differ in size, rate, frames or encoding")

    # studies
    banned_text = "\n".join(lines) + "\n"
    ids = [f"{a.prefix}-r{i}" for i in range(1, a.raters + 1)]
    for sid in ids:
        d = studies / sid
        d.mkdir(parents=True, exist_ok=True)
        (d / "banned-terms.txt").write_text(banned_text)
        write_study(d / "study.yaml", build_study(sid, seed=seed, instrument=a.instrument, q2=q2, items=items,
                                                   fps=a.fps, frames=n_frames))
        if not a.no_blindpanel:
            lock_build_verify(cli, d, force_lock=a.force_lock)
            check_built(d, list(clip_codes.values()), list(panel_codes.values()), len(items), q2)

    locks = {}
    for sid in ids:
        lp = studies / sid / "study.lock.json"
        if lp.exists():
            locks[sid] = json.loads(lp.read_text())
    manifest = {
        "schema": MANIFEST_SCHEMA, "salt": salt, "seed": seed, "fps": a.fps, "frames": n_frames, "size": list(SIZE),
        "crf": CRF, "ffmpeg": ffmpeg_version(), "studies": ids, "instrument": a.instrument, "locks": locks,
        "key_sha256": sha256_file(keyfile), "q2_options_sha256": sha256_file(sealed / "q2-options.json"),
        "banned_terms_sha256": hashlib.sha256(banned_text.encode()).hexdigest(),
        "items": [{"ref": i["ref"], "law": i["law"], "clip_code": i["clip_code"], "panel_code": i["panel_code"],
                   "clip_sha256": i["clip_sha"], "panel_sha256": i["panel_sha"], "cue_s": i["cue_s"],
                   "ring_bbox": i["ring_bbox"]} for i in items],
        "q2_options": len(q2), "failure_path": bool(a.failure_path),
    }
    (sealed / "rating-manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return manifest


def _extra_banned(path):
    return [ln for ln in Path(path).read_text().splitlines()] if path else []


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--laws", default=str(ROOT / "sealed" / "laws.json"), help="p47-laws/1 file: the Q2 labels and law words")
        p.add_argument("--takes", default=str(ROOT / "capture" / "takes.json"))
        p.add_argument("--sealed", default=str(ROOT / "sealed"), help="answer-key.json, q2-options.json, rating-manifest.json")

    s = sub.add_parser("seal", help="Gate R: draw the salt, seed, codes and Q2 order once")
    common(s)
    s.add_argument("--force", action="store_true", help="redraw (changes every code)")
    b = sub.add_parser("build", help="Phase 9.2: copies, stills, studies, lock and verify")
    common(b)
    b.add_argument("--inputs", required=True, help="p47-rating-inputs/1 JSON")
    b.add_argument("--out", default=str(ROOT / "rating"), help="holds media/ and studies/ (gitignored)")
    b.add_argument("--raters", type=int, default=5)
    b.add_argument("--prefix", default="limn", help="study ids are <prefix>-r1 ...")
    b.add_argument("--instrument", default="1")
    b.add_argument("--fps", type=int, default=FPS)
    b.add_argument("--seconds", type=float, help="rating copy length, fixtures only: omitted, the registered rule (12 s or the shortest render) applies")
    b.add_argument("--frames", type=int, help="rating copy length in frames (overrides --seconds)")
    b.add_argument("--blindpanel", default=os.environ.get("BLINDPANEL_CLI"),
                   help="bin/blindpanel.mjs of the blindpanel repository at tag v0.2.0 (default: $BLINDPANEL_CLI; no other default)")
    b.add_argument("--no-blindpanel", action="store_true", help="write files only; skip lock, build and verify")
    b.add_argument("--force-lock", action="store_true", help="re-lock after a wording fix before any rating")
    b.add_argument("--banned-extra", help="a file of extra banned-terms lines")
    b.add_argument("--failure-path", action="store_true",
                   help="deviation D3 (call 143): the glass take x3 only, with their sealed codes (§19's failure path)")
    a = ap.parse_args(argv)
    if a.cmd == "build" and not (a.seconds or a.frames):
        ap.error("build needs --seconds or --frames: the copies' length is chosen, never defaulted to the shortest source")
    return a


def main(argv=None) -> int:
    a = parse_args(argv)
    try:
        if a.cmd == "seal":
            r = seal(a)
            print(f"sealed {r['items']} items; key sha256 {r['key_sha256'][:12]}, q2-options sha256 {r['q2_sha256'][:12]}")
        else:
            m = prepare(a)
            print(f"prepared {len(m['studies'])} studies, {len(m['items'])} items, {m['frames']} frames at {m['fps']} fps; "
                  f"key sha256 {m['key_sha256'][:12]}")
    except (PrepareError, OSError, ValueError, KeyError) as e:      # ValueError covers bad JSON and an invalid laws file
        print(f"prepare: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
