#!/usr/bin/env python3
"""The paste- and shift-control inputs (R0.3, §10), built from a real take and the flat scan crop.

    python seam/controls_inputs.py paste --take t01 --material ink --take-id t01a \
        --masks masks/t01.npz --cues cues/t01.json --crops creature/scan/crops.json --out runs/registration/t01-ink.paste.npz
    python seam/controls_inputs.py shift-pair --take t01 --material ink --take-id t01a --masks masks/t01.npz \
        --paste-result runs/registration/t01-ink.paste.json --shift-result runs/registration/t01-ink.shift.json --out ...
    python seam/controls_inputs.py shift --take t01 --material ink --take-id t01a \
        --masks masks/t01.npz --paste-result runs/registration/t01-ink.paste.json --out runs/registration/t01-ink.shift.npz
    python seam/controls_inputs.py null --take t01 --take-id t01a --masks masks/t01.npz --out cache/controls/t01.null.npz

These run in the repo venv. The files they write are what `seam/lines_job.py` reads in the ComfyUI venv
(`paste-control --input`, `shift-control --input`; `measure --pair` for the pair).

Paste. `capture/takes.json` gains a per-row `paste` entry (one row per take and acting material):

    "paste": {"crop": "ink",              key of creature/scan/crops.json (an RGBA PNG per material; alpha > 127
                                          is the paste mask, the alpha channel is the creature's cut-out)
              "touched_mask": "glass",    object name in the take's p47-masks/1 file; null for the breath take
              "home_mask": "home_ink",    the acting creature's resting drawing
              "page_mask": "page",        required only when touched_mask is null
              "scale": null,              crop px -> analysis px; null = fit the crop's area to the home mask's
              "event": "e02" | "t": 0.4}  optional override of the cue window (default: the first event that fires a law)

* Cue window: from the firing event's t to the end of the take, in analysis frames (first frame at or after t).
* Placement (§10): the crop is held still, with its nearest mask pixel 4 px (the first 0.25 px step at which it is
  at least 4 px, rounded to whole pixels) from the touched object's take mask at the cue frame, on the line from the
  touched object's centroid to the home's centroid. SAM tracks forward from the blind placer's prompt frame only, so
  where that mask is empty at the cue frame the first frame at or after it with the object tracked places the crop;
  the window still starts at the cue (call 133). Both frames are recorded (`cue_frame`, `placement_frame`).
* The cue sheet defaults to the render's own, cues/<take>-<material>.json (the glass take's gold and paper renders,
  call 133), else cues/<take>.json. The breath take, which touches nothing, has the crop just below
  the page (its bottom edge plus 4 px), centred on the home's x.
* The home is the majority vote of the home track over the take (a resting drawing does not move).
* The codec nulls are the render input (the 1080p copy the model is sent) re-encoded at 720p and at 1080p with the
  null settings of seam/video.py, decoded onto the grid; the take is the analysis copy. A real render goes through
  the same resize, so the floor carries the same resampling difference.

Shift. `shift_region` gives R0(t) = ~dilate(home, m) on every frame, m from the paste result; the lines job picks
the patch, moves it and judges the cells. `write_shift_pair` also writes the take against its shifted copy in
`seam/pairs.py` format, for `lines_job.py measure`.

Null. The codec-null input for the registered D0 floors and κ_codec (§9): the take, its render input re-encoded at
720p and 1080p (as for the paste control) and every home's static mask; `lines_job.py codec-null` scores it.
"""
import argparse
import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from seam import controls, pairs, regions, video  # noqa: E402
from seam.util import sha256_file  # noqa: E402

SCHEMA = "p47-control-input/1"
GAP_PX = 4
STEP_PX = 0.25
FPS = video.FPS
REQUIRED = ("crop", "touched_mask", "home_mask")
OPTIONAL = ("page_mask", "scale", "event", "t")


class ControlInputError(ValueError):
    pass


# ---- the entry in capture/takes.json -------------------------------------------------------------------------
def validate_paste_entry(e):
    if not isinstance(e, dict):
        raise ControlInputError("paste entry must be an object")
    unknown = sorted(set(e) - set(REQUIRED) - set(OPTIONAL))
    if unknown:
        raise ControlInputError(f"paste entry: unknown keys {unknown}")
    missing = [k for k in REQUIRED if k not in e]
    if missing:
        raise ControlInputError(f"paste entry: missing {', '.join(missing)}")
    for k in ("crop", "home_mask"):
        if not isinstance(e[k], str) or not e[k]:
            raise ControlInputError(f"paste entry: {k} must be a name")
    if e["touched_mask"] is not None and not (isinstance(e["touched_mask"], str) and e["touched_mask"]):
        raise ControlInputError("paste entry: touched_mask must be a name or null")
    if e["touched_mask"] is None and not e.get("page_mask"):
        raise ControlInputError("paste entry: a take with no touched object needs a page_mask")
    s = e.get("scale")
    if s is not None and not (isinstance(s, (int, float)) and not isinstance(s, bool) and s > 0 and math.isfinite(s)):
        raise ControlInputError(f"paste entry: scale must be null or a positive number, got {s!r}")
    if e.get("event") is not None and e.get("t") is not None:
        raise ControlInputError("paste entry: give event or t, not both")
    return e


def find_row(rows, take, material):
    hit = [r for r in rows if r.get("id") == take and r.get("target_material") == material]
    if len(hit) != 1:
        raise ControlInputError(f"capture/takes.json: {len(hit)} rows for take {take!r} and material {material!r}")
    return hit[0]


# ---- the crop ------------------------------------------------------------------------------------------------------
def load_crop(crops_json, name):
    """The RGBA crop for a material (uint8 (h, w, 4)); its file is named in crops.json, relative to it."""
    from PIL import Image
    path = Path(crops_json)
    try:
        crops = json.loads(path.read_text())["crops"]
    except (OSError, KeyError, ValueError) as e:
        raise ControlInputError(f"{path}: cannot read crops: {e}") from e
    if name not in crops:
        raise ControlInputError(f"{path}: no crop named {name!r}; it has {sorted(crops)}")
    f = path.parent / crops[name]["file"]
    if not f.is_file():
        raise ControlInputError(f"{path}: the crop file {f.name} for {name!r} does not exist")
    img = Image.open(f)
    # alpha is an A band, or a tRNS chunk (palette, grey or RGB PNGs), which PIL keeps in info["transparency"]
    if "A" not in img.getbands() and "transparency" not in img.info:
        raise ControlInputError(f"{f.name}: no alpha channel; the crop needs its cut-out as alpha")
    rgba = np.asarray(img.convert("RGBA"), np.uint8)
    if not alpha_mask(rgba).any():
        raise ControlInputError(f"{f.name}: no opaque pixel (alpha > 127)")
    return rgba


def alpha_mask(rgba):
    return np.asarray(rgba)[..., 3] > 127


def fit_scale(rgba, home):
    home = np.asarray(home, bool)
    if not home.any():
        raise ControlInputError("home mask is empty")
    return float(math.sqrt(home.sum() / alpha_mask(rgba).sum()))


def scale_rgba(rgba, scale):
    """Resample with premultiplied alpha (no dark fringe); scale 1 returns a copy."""
    import cv2
    rgba = np.asarray(rgba, np.uint8)
    if not (scale > 0 and math.isfinite(scale)):
        raise ControlInputError(f"scale must be positive, got {scale!r}")
    if scale == 1.0:
        return rgba.copy()
    h, w = rgba.shape[:2]
    size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
    a = rgba[..., 3:].astype(np.float32) / 255.0
    pre = np.concatenate([rgba[..., :3].astype(np.float32) * a, a], axis=2)
    out = cv2.resize(pre, size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    oa = np.clip(out[..., 3:], 0.0, 1.0)
    rgb = np.where(oa > 1e-6, out[..., :3] / np.maximum(oa, 1e-6), 0.0)
    return np.concatenate([np.clip(np.rint(rgb), 0, 255), np.rint(oa * 255)], axis=2).astype(np.uint8)


# ---- the cue window ---------------------------------------------------------------------------------------------------
def cue_window(sheet, material, fps=FPS, event=None, t=None):
    """(t, first analysis frame): the window runs from there to the end of the take."""
    if event is not None and t is not None:
        raise ControlInputError("give event or t, not both")
    if t is None:
        events = sheet["events"]
        if event is not None:
            hit = [e for e in events if e["id"] == event]
            if not hit:
                raise ControlInputError(f"cue sheet has no event {event!r}")
            if hit[0]["target"] != material:
                raise ControlInputError(f"event {event} fires no law for {material} (target {hit[0]['target']!r})")
            t = hit[0]["t"]
        else:
            firing = sorted((e for e in events if e["target"] == material), key=lambda e: e["t"])
            if not firing:
                raise ControlInputError(f"cue sheet has no event that fires a law for {material}")
            t = firing[0]["t"]
    return float(t), int(math.ceil(float(t) * fps - 1e-9))


# ---- placement ----------------------------------------------------------------------------------------------------------
def _centroid(mask):
    ys, xs = np.nonzero(mask)
    return np.array([xs.mean(), ys.mean()])


def place_at_object(rgba, touched, home, gap=GAP_PX):
    """Top-left (x, y) putting the crop's nearest mask pixel `gap` px from the touched object, on the line from
    its centroid to the home's. Returns (xy, info)."""
    from scipy.ndimage import distance_transform_edt
    touched, home = np.asarray(touched, bool), np.asarray(home, bool)
    if not touched.any():
        raise ControlInputError("the touched object's mask is empty at the cue frame")
    if not home.any():
        raise ControlInputError("the home mask is empty")
    c_t, c_h = _centroid(touched), _centroid(home)
    if np.allclose(c_t, c_h):
        raise ControlInputError("the touched object and the home have the same centroid; no line to place on")
    u = (c_h - c_t) / np.linalg.norm(c_h - c_t)
    ys, xs = np.nonzero(alpha_mask(rgba))
    cm = np.array([xs.mean(), ys.mean()])
    dist = distance_transform_edt(~touched)
    h, w = touched.shape
    s_max = math.hypot(h, w)
    for k in range(int(s_max / STEP_PX) + 1):
        s = k * STEP_PX
        x, y = (int(v) for v in np.rint(c_t + s * u - cm))
        px, py = xs + x, ys + y
        if px.min() < 0 or py.min() < 0 or px.max() >= w or py.max() >= h:
            continue
        near = float(dist[py, px].min())
        if near >= gap:
            return (x, y), {"placement": "at_object", "distance": near, "s": s, "direction": [float(u[0]), float(u[1])]}
    raise ControlInputError(f"no room: the crop does not clear the touched object by {gap} px inside the frame "
                            "on the line to the home")


def place_below(rgba, home, page=None, gap=GAP_PX):
    """The breath take: the crop's top edge `gap` px below the page (else below the home), centred on the home's x."""
    home = np.asarray(home, bool)
    if not home.any():
        raise ControlInputError("the home mask is empty")
    ref = home if page is None else np.asarray(page, bool)
    if not ref.any():
        raise ControlInputError("the page mask is empty")
    bottom = int(np.nonzero(ref)[0].max()) + 1
    ys, xs = np.nonzero(alpha_mask(rgba))
    x = int(round(_centroid(home)[0] - xs.mean()))
    y = bottom + gap - int(ys.min())
    h, w = home.shape
    if xs.min() + x < 0 or xs.max() + x >= w or ys.max() + y >= h:
        raise ControlInputError("no room below the page inside the frame")
    return (x, y)


def placement_frame(track, i0):
    """The frame whose touched-object mask places the crop (call 133): the cue frame, or, since SAM tracks forward
    from the blind placer's prompt frame only, the first frame at or after it on which the object is tracked."""
    tracked = np.nonzero(np.asarray(track, bool).reshape(len(track), -1).any(axis=1))[0]
    after = tracked[tracked >= i0]
    if not len(after):
        raise ControlInputError(f"the touched object is not tracked at or after the cue frame {i0}")
    return int(after[0])


def static_mask(stack):
    """Majority vote over frames: a resting drawing does not move."""
    return np.asarray(stack, bool).mean(axis=0) > 0.5


def _mask(masks, name, n):
    if name not in masks:
        raise ControlInputError(f"the take masks have no object {name!r}; they have {sorted(masks)}")
    m = np.asarray(masks[name], bool)
    if len(m) != n:
        raise ControlInputError(f"mask {name!r}: length {len(m)} != {n} frames")
    return m


# ---- the paste composite ------------------------------------------------------------------------------------------------------
def build_paste(take_frames, masks, entry, material, sheet, rgba_raw, fps=FPS):
    """The cue-window frames, the crop composited through them, the paste masks and the placement.
    ``masks`` maps object names to (n, H, W) bool tracks on the same frames as ``take_frames``."""
    validate_paste_entry(entry)
    n = len(take_frames)
    t, i0 = cue_window(sheet, material, fps, entry.get("event"), entry.get("t"))
    if not 0 <= i0 < n:
        raise ControlInputError(f"the cue window starts at frame {i0}, outside the {n} frames")
    home = static_mask(_mask(masks, entry["home_mask"], n))
    scale = entry.get("scale") or fit_scale(rgba_raw, home)
    rgba = scale_rgba(rgba_raw, scale)
    if entry["touched_mask"] is not None:
        f = placement_frame(_mask(masks, entry["touched_mask"], n), i0)
        xy, info = place_at_object(rgba, _mask(masks, entry["touched_mask"], n)[f], home)
    else:
        page = static_mask(_mask(masks, entry["page_mask"], n))
        xy = place_below(rgba, home, page)
        f, info = None, {"placement": "below_page", "distance": None}
    info = {**info, "cue_frame": i0, "placement_frame": f}
    window = np.asarray(take_frames)[i0:]
    composite, pmasks = controls.paste(window, rgba, xy, range(len(window)))
    return {"take": window, "composite": composite, "masks": pmasks, "rgba": rgba, "xy": tuple(int(v) for v in xy),
            "home": home, "i0": i0, "window": (i0, n), "t": t, "info": {**info, "scale": float(scale)}}


# ---- the codec nulls -------------------------------------------------------------------------------------------------------------
def null_frames(render_input, heights=(720, 1080), *, n_frames=None, size=video.SIZE):
    """{height: (n, H, W, 3)}: the render input re-encoded at each height (the null settings), decoded onto the
    grid at the analysis times, the first n_frames of them."""
    out = {}
    with tempfile.TemporaryDirectory(prefix="null-") as td:
        for h in heights:
            dst = video.reencode(render_input, Path(td) / f"null{h}.mp4", h)
            fr, pts = video.read_video(dst, size=size)
            sel = video.resample(fr, pts, video.analysis_times(pts[-1]))
            if n_frames is not None:
                if len(sel) < n_frames:
                    raise ControlInputError(f"the {h}p null has {len(sel)} analysis frames, the take {n_frames}")
                sel = sel[:n_frames]
            out[int(h)] = sel
    return out


# ---- writers ------------------------------------------------------------------------------------------------------------------------
def _save(path, arrays, meta):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, **arrays, meta=np.array(json.dumps({"schema": SCHEMA, **meta}, sort_keys=True)))
    return path


def write_paste_input(path, built, nulls, meta=None):
    """The npz `lines_job.py paste-control` reads: take (the cue window), null_<height>, rgba, xy, home."""
    shape = built["take"].shape
    arrays = {"take": built["take"], "rgba": built["rgba"], "xy": np.array(built["xy"], np.int64), "home": built["home"]}
    for h, fr in sorted(nulls.items()):
        if np.asarray(fr).shape != shape:
            raise ControlInputError(f"null_{h}: shape {np.asarray(fr).shape} != the window {shape}")
        arrays[f"null_{h}"] = np.asarray(fr, np.uint8)
    i0, n = built["window"]
    info = {k: v for k, v in built["info"].items()}
    return _save(path, arrays, {**(meta or {}), "window": {"t": built["t"], "i0": i0, "n": n - i0},
                                "scale": info["scale"], "xy": list(built["xy"]), "placement": info})


def shift_region(home, m, n):
    """R0(t) = ~dilate(home, m) on every one of n frames (the region before any render exists)."""
    if m not in controls.M_CHOICES:
        raise ControlInputError(f"m must be one of {controls.M_CHOICES}, got {m!r}")
    return np.repeat((~regions.dilate(home, m))[None], n, axis=0)


def write_shift_input(path, take, R, meta=None):
    """The npz `lines_job.py shift-control` reads: take (n, H, W, 3) and R (n, H, W)."""
    take, R = np.asarray(take, np.uint8), np.asarray(R, bool)
    if R.shape != take.shape[:3]:
        raise ControlInputError(f"R shape {R.shape} != take frames {take.shape[:3]}")
    return _save(path, {"take": take, "R": R}, meta or {})


def write_shift_pair(path, take, R, xy, fps=FPS, meta=None):
    """The take against its copy with the 64x64 patch at xy moved by (3, 3), in pairs.py format."""
    take = np.asarray(take, np.uint8)
    shifted = controls.shift_patch(take, xy)                 # ValueError if the move leaves the frame
    n = len(take)
    shift = {"xy": [int(xy[0]), int(xy[1])], "dx": controls.SHIFT[0], "dy": controls.SHIFT[1], "size": controls.PATCH}
    return pairs.write_pair(path, take=take, render=shifted, valid=np.ones(n, bool), R=R, t=np.arange(n) / fps,
                            meta={**(meta or {}), "shift": shift})


# ---- files in, files out ------------------------------------------------------------------------------------------------------------
def _analysis_frames(path, size):
    fr, pts = video.read_video(path, size=size)
    return video.resample(fr, pts, video.analysis_times(pts[-1]))


def _common(a):
    root = Path(a.root)
    rows = json.loads(Path(a.takes or root / "capture/takes.json").read_text())
    row = find_row(rows, a.take, a.material)
    if "paste" not in row:
        raise ControlInputError(f"capture/takes.json: row {a.take}/{a.material} has no paste entry")
    entry = validate_paste_entry(row["paste"])
    take_id = a.take_id or a.take
    return root, entry, take_id, root / "takes" / f"{take_id}.analysis.mp4", root / "takes" / f"{take_id}.render.mp4"


def sheet_path(root, take, material):
    """The render's cue sheet: cues/<take>-<material>.json if it exists (the glass take's gold and paper renders,
    call 133), else cues/<take>.json."""
    own = Path(root) / "cues" / f"{take}-{material}.json"
    return own if own.is_file() else Path(root) / "cues" / f"{take}.json"


def _load_masks(path, n):
    from seam import masks as mk
    if not path:
        raise ControlInputError("give --masks (the take's p47-masks/1 file)")
    meta, m = mk.load_masks(path)
    return meta, m


def paste_from_files(a):
    root, entry, take_id, analysis, render_in = _common(a)
    size = tuple(a.size)
    heights = tuple(int(h) for h in a.heights.split(","))
    take = _analysis_frames(analysis, size)
    _, m = _load_masks(a.masks, len(take))
    sheet = json.loads(Path(a.cues or sheet_path(root, a.take, a.material)).read_text())
    crops = Path(a.crops or root / "creature/scan/crops.json")
    raw = load_crop(crops, entry["crop"])
    built = build_paste(take, m, entry, a.material, sheet, raw)
    nulls = null_frames(render_in, heights, n_frames=len(take), size=size)
    nulls = {h: v[built["i0"]:] for h, v in nulls.items()}
    meta = {"take": a.take, "take_id": take_id, "material": a.material, "fps": FPS, "heights": list(heights),
            "size": list(size), "entry": entry,
            "sources": {"analysis": sha256_file(analysis), "render_input": sha256_file(render_in),
                        "masks": sha256_file(a.masks), "crop_rgba": hashlib.sha256(raw.tobytes()).hexdigest()}}
    return write_paste_input(a.out, built, nulls, meta)


def check_result(res, what, take, material):
    """A lines-job result must say (input_meta, copied from the input npz) which take and material it is for."""
    im = res.get("input_meta")
    if not isinstance(im, dict) or "take" not in im or "material" not in im:
        raise ControlInputError(f"the {what} has no input_meta naming its take and material (an older lines job?); "
                                "rerun it on the current input file")
    if im["take"] != take:
        raise ControlInputError(f"the {what} is for take {im['take']!r}, not {take!r}")
    if im["material"] != material:
        raise ControlInputError(f"the {what} is for material {im['material']!r}, not {material!r}")
    return im


def _region_m(a):
    m = a.m
    if a.paste_result:
        res = json.loads(Path(a.paste_result).read_text())
        check_result(res, "paste result", a.take, a.material)
        if res.get("m") is None:
            raise ControlInputError(f"the paste control gave no m ({res.get('reason')}): H is not testable, "
                                    "so there is no region to shift in")
        if m is not None and m != res["m"]:
            raise ControlInputError(f"--m {m} disagrees with the paste result's m {res['m']}")
        m = res["m"]
    if m is None:
        raise ControlInputError("give --m or --paste-result")
    return int(m)


def shift_pair_from_files(a):
    """The take against its shifted copy (pairs.py format) for the patch the shift control chose."""
    root, entry, take_id, analysis, _ = _common(a)
    m = _region_m(a)
    res = json.loads(Path(a.shift_result).read_text())
    im = check_result(res, "shift result", a.take, a.material)
    if im.get("m") is not None and im["m"] != m:
        raise ControlInputError(f"the shift result was run with m = {im['m']}, not {m}")
    if res.get("xy") is None:
        raise ControlInputError(f"the shift result chose no patch ({res.get('reason')}); there is no pair to build")
    size = tuple(a.size)
    take = _analysis_frames(analysis, size)
    _, masks_ = _load_masks(a.masks, len(take))
    if entry["home_mask"] not in masks_:
        raise ControlInputError(f"the take masks have no object {entry['home_mask']!r}; they have {sorted(masks_)}")
    R = shift_region(static_mask(masks_[entry["home_mask"]]), m, len(take))
    meta = {"render": f"{a.take}-{a.material}", "take": a.take, "take_id": take_id, "material": a.material, "m": m,
            "sources": {"analysis": sha256_file(analysis), "masks": sha256_file(a.masks)}}
    return write_shift_pair(a.out, take, R, tuple(res["xy"]), meta=meta)


def shift_from_files(a):
    root, entry, take_id, analysis, _ = _common(a)
    m = _region_m(a)
    size = tuple(a.size)
    take = _analysis_frames(analysis, size)
    _, masks_ = _load_masks(a.masks, len(take))
    if entry["home_mask"] not in masks_:
        raise ControlInputError(f"the take masks have no object {entry['home_mask']!r}; they have {sorted(masks_)}")
    home = static_mask(masks_[entry["home_mask"]])
    meta = {"take": a.take, "take_id": take_id, "material": a.material, "m": int(m), "fps": FPS, "size": list(size),
            "home_mask": entry["home_mask"],
            "sources": {"analysis": sha256_file(analysis), "masks": sha256_file(a.masks)}}
    return write_shift_input(a.out, take, shift_region(home, int(m), len(take)), meta)


def null_from_files(a):
    """The codec-null input (§9): the take's analysis frames, its render input re-encoded at each height and
    decoded onto the grid, and every resting drawing's static home (the majority vote of its track)."""
    root = Path(a.root)
    take_id = a.take_id or a.take
    analysis, render_in = root / "takes" / f"{take_id}.analysis.mp4", root / "takes" / f"{take_id}.render.mp4"
    size = tuple(a.size)
    heights = tuple(int(h) for h in a.heights.split(","))
    take = _analysis_frames(analysis, size)
    _, m = _load_masks(a.masks, len(take))
    names = sorted(k for k in m if k.startswith("home_"))
    if not names:
        raise ControlInputError(f"the take masks have no home; they have {sorted(m)}")
    homes = np.stack([static_mask(_mask(m, k, len(take))) for k in names])
    nulls = null_frames(render_in, heights, n_frames=len(take), size=size)
    arrays = {"take": take, "homes": homes, **{f"null_{h}": v for h, v in sorted(nulls.items())}}
    meta = {"take": a.take, "take_id": take_id, "fps": FPS, "heights": list(heights), "size": list(size),
            "homes": names, "sources": {"analysis": sha256_file(analysis), "render_input": sha256_file(render_in),
                                        "masks": sha256_file(a.masks)}}
    return _save(a.out, arrays, meta)


def _size(s):
    w, _, h = s.partition("x")
    return (int(w), int(h))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("paste", "shift", "shift-pair", "null"):
        p = sub.add_parser(name)
        p.add_argument("--take", required=True)
        if name != "null":
            p.add_argument("--material", required=True)
        p.add_argument("--take-id", help="take plus attempt letter, e.g. t01a (default: --take)")
        p.add_argument("--root", default=str(REPO))
        p.add_argument("--takes")
        p.add_argument("--masks")
        p.add_argument("--size", type=_size, default=video.SIZE, help="WxH of the analysis grid")
        p.add_argument("--out", required=True)
        if name == "paste":
            p.add_argument("--cues")
            p.add_argument("--crops")
            p.add_argument("--heights", default="720,1080")
        elif name == "null":
            p.add_argument("--heights", default="720,1080")
        else:
            p.add_argument("--m", type=int)
            p.add_argument("--paste-result", help="lines_job paste-control output; gives m and names its take and material")
            if name == "shift-pair":
                p.add_argument("--shift-result", required=True, help="lines_job shift-control output (the patch xy)")
    a = ap.parse_args(argv)
    try:
        out = {"paste": paste_from_files, "shift": shift_from_files, "shift-pair": shift_pair_from_files,
               "null": null_from_files}[a.cmd](a)
    except (ControlInputError, ValueError, OSError, KeyError) as e:
        print(f"controls_inputs: refuse: {e}", file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
