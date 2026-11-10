"""Take and render masks: point prompts -> SAM 2.1 tracks on CPU, stored bit-packed per frame.

Analysis runs at 15 fps on the 1280x720 grid (R0.3). The pieces:

- ``sample_frames``: decode a video and keep one frame per 1/fps second.
- ``load_prompts``: ``masks/prompts/<take>.json`` -> ``{object: [(frame, x, y, positive)]}``.
- ``track``: SAM 2.1 small video propagation on CPU, forward from each object's first prompt.
- ``save_masks`` / ``load_masks``: ``p47-masks/1`` npz, one ``np.packbits`` row per frame.
- ``mask_digest``: SHA-256 over the packed bits, for the manifest addendum.
- ``quality_ok``: the R0.3 mask quality rule (a frame scores None if the mask is empty or its
  area changes by more than 50 % from the previous frame).
- ``grid_overlay`` / ``write_grid_frames``: labelled pixel grids for the point-placing agent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

SCHEMA = "p47-masks/1"
ANALYSIS_FPS = 15
ROOT = Path(__file__).resolve().parent.parent
CKPT = ROOT / "models" / "sam2.1_hiera_small.pt"
SAM_CONFIG = "configs/sam2.1/sam2.1_hiera_s.yaml"
MAX_AREA_CHANGE = 0.5


# --- frames -------------------------------------------------------------------
def sample_frames(path, fps: float = ANALYSIS_FPS, size: tuple[int, int] | None = None) -> np.ndarray:
    """RGB uint8 frames (n, h, w, 3), one per 1/fps s: frame k is the first decoded frame whose
    presentation time is at or after k/fps (less half a source frame, to absorb pts jitter).
    ``size`` is (height, width) for an optional INTER_AREA resize."""
    import av

    out = []
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        src_rate = float(s.average_rate or s.guessed_rate or 30)
        slack = 0.5 / src_rate
        k = 0
        for fr in c.decode(s):
            t = float(fr.pts * fr.time_base) if fr.pts is not None else len(out) / fps
            if t + slack < k / fps:
                continue
            img = fr.to_ndarray(format="rgb24")
            if size is not None:
                img = cv2.resize(img, (size[1], size[0]), interpolation=cv2.INTER_AREA)
            # one source frame may stand for several analysis ticks if the source is slower than fps
            while t + slack >= k / fps:
                out.append(img)
                k += 1
    if not out:
        raise ValueError(f"{path}: no video frames decoded")
    return np.stack(out)


ANALYSIS_SIZE = (720, 1280)


def video_size(path) -> tuple[int, int]:
    """(height, width) of a video's first stream."""
    import av
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        return int(s.height), int(s.width)


def analysis_frames(path, fps: float = ANALYSIS_FPS) -> np.ndarray:
    """A video's frames on the registered 1280x720 grid at 15 fps: the frames every mask, pick and point
    prompt is made on. A source that is not 16:9 is refused (it cannot map onto the grid)."""
    h, w = video_size(path)
    if abs(w * 9 - h * 16) > max(w, h) * 0.01 * 9:
        raise ValueError(f"{Path(path).name}: {w}x{h} is not 16:9, so it cannot map onto the 1280x720 grid")
    return sample_frames(path, fps=fps, size=ANALYSIS_SIZE)


# --- prompts --------------------------------------------------------------------
def load_prompts(path, size: tuple[int, int], n_frames: int | None = None) -> dict[str, list[tuple[int, float, float, bool]]]:
    """Validate a point-prompt file. ``size`` is (height, width) of the analysis frames; ``n_frames``,
    if given, bounds the frame indices. Every object needs at least one positive point; coordinates
    must lie inside the frame."""
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    h, w = size
    if not isinstance(data, dict) or not isinstance(data.get("objects"), dict) or not data["objects"]:
        raise ValueError(f"{p.name}: needs a non-empty 'objects' map")
    out = {}
    for obj, pts in sorted(data["objects"].items()):
        if not isinstance(pts, list) or not pts:
            raise ValueError(f"{p.name}: object {obj!r} has no points")
        rows = []
        for pt in pts:
            if not isinstance(pt, dict) or set(pt) != {"frame", "x", "y", "positive"}:
                raise ValueError(f"{p.name}: {obj!r} point needs exactly frame, x, y, positive")
            f, x, y, pos = pt["frame"], pt["x"], pt["y"], pt["positive"]
            if isinstance(f, bool) or not isinstance(f, int) or f < 0:
                raise ValueError(f"{p.name}: {obj!r} frame must be a non-negative integer")
            if n_frames is not None and f >= n_frames:
                raise ValueError(f"{p.name}: {obj!r} frame {f} is past the take's last frame ({n_frames - 1})")
            if not isinstance(pos, bool):
                raise ValueError(f"{p.name}: {obj!r} positive must be true or false")
            if not (0 <= x < w and 0 <= y < h):
                raise ValueError(f"{p.name}: {obj!r} point ({x}, {y}) is outside the {w}x{h} frame")
            rows.append((f, float(x), float(y), pos))
        if not any(r[3] for r in rows):
            raise ValueError(f"{p.name}: object {obj!r} needs at least one positive point")
        out[obj] = rows
    return out


# --- SAM 2.1 tracking -----------------------------------------------------------
def _float_memory(_module, args, kwargs):
    """SAM 2 (2b90b9f) stores mask memories as bfloat16, assuming CUDA autocast. On CPU, when a
    frame's memory holds only those (no float object pointers to promote the concat), the memory
    attention's float32 Linear fails with a dtype mismatch. Cast the memory inputs back to float32."""
    import torch

    for k in ("memory", "memory_pos"):
        v = kwargs.get(k)
        if v is not None and v.dtype != torch.float32:
            kwargs[k] = v.float()
    return args, kwargs


def track(frames: np.ndarray, prompts: dict, ckpt=CKPT, config: str = SAM_CONFIG) -> dict[str, np.ndarray]:
    """Propagate point prompts through ``frames`` (n, h, w, 3 RGB) with SAM 2.1 on CPU.

    One SAM object per prompt object (sorted by name). Propagation runs forward from the earliest
    prompted frame; frames before an object's first prompt stay empty. Returns {object: bool (n, h, w)}.
    """
    if not Path(ckpt).is_file():
        raise FileNotFoundError(f"SAM 2.1 checkpoint not found at {ckpt}; download it as in models/MODELS.md")
    try:
        import torch
        from sam2.build_sam import build_sam2_video_predictor
    except ImportError as e:
        raise ImportError("SAM 2 is not installed in this venv: run `SAM2_BUILD_CUDA=0 uv sync` "
                          "(pinned commit and checkpoint in models/MODELS.md)") from e

    frames = np.asarray(frames)
    n, h, w = frames.shape[:3]
    names = sorted(prompts)
    out = {k: np.zeros((n, h, w), bool) for k in names}
    tmp = Path(tempfile.mkdtemp(prefix="limn_sam2_"))
    try:
        for i, f in enumerate(frames):   # SAM 2's video loader reads a folder of numbered JPEGs
            cv2.imwrite(str(tmp / f"{i:05d}.jpg"), cv2.cvtColor(f, cv2.COLOR_RGB2BGR),
                        [cv2.IMWRITE_JPEG_QUALITY, 95])
        with torch.inference_mode():
            pred = build_sam2_video_predictor(config, str(ckpt), device="cpu")
            pred.memory_attention.register_forward_pre_hook(_float_memory, with_kwargs=True)
            state = pred.init_state(video_path=str(tmp))
            for oid, k in enumerate(names, start=1):
                by_frame: dict[int, list] = {}
                for fi, x, y, pos in prompts[k]:
                    by_frame.setdefault(fi, []).append((x, y, pos))
                for fi in sorted(by_frame):
                    pts = by_frame[fi]
                    pred.add_new_points_or_box(
                        state, frame_idx=fi, obj_id=oid,
                        points=np.array([[x, y] for x, y, _ in pts], np.float32),
                        labels=np.array([1 if p else 0 for _, _, p in pts], np.int32))
            for fi, obj_ids, logits in pred.propagate_in_video(state):
                for j, oid in enumerate(obj_ids):
                    k = names[int(oid) - 1]
                    first = min(p[0] for p in prompts[k])
                    if fi >= first:
                        out[k][fi] = (logits[j, 0] > 0).cpu().numpy()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


# --- store ----------------------------------------------------------------------
def _common_shape(m: dict[str, np.ndarray]) -> tuple[int, int, int]:
    shapes = {np.asarray(v).shape for v in m.values()}
    if len(shapes) != 1 or len(next(iter(shapes))) != 3:
        raise ValueError(f"all masks must share one (n, h, w) shape, got {sorted(shapes)}")
    return next(iter(shapes))


def save_masks(path, m: dict[str, np.ndarray], *, take: str, fps: float = ANALYSIS_FPS, extra=None) -> None:
    """Write ``p47-masks/1``: key ``meta`` (JSON) and ``obj:<name>`` = packbits per frame. ``extra`` (a
    JSON map) is merged into the meta: the source size and the prompt and video hashes, from the CLI."""
    if not m:
        raise ValueError("no masks to save")
    n, h, w = _common_shape(m)
    meta = {"schema": SCHEMA, "take": take, "fps": fps, "n_frames": n, "height": h, "width": w,
            "objects": sorted(m), **(extra or {})}
    arrays = {"meta": np.array(json.dumps(meta, sort_keys=True))}
    for k in sorted(m):
        arrays[f"obj:{k}"] = np.packbits(np.asarray(m[k], bool).reshape(n, -1), axis=1)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        np.savez_compressed(f, **arrays)


def load_masks(path) -> tuple[dict, dict[str, np.ndarray]]:
    with np.load(path) as z:
        meta = json.loads(str(z["meta"]))
        if meta.get("schema") != SCHEMA:
            raise ValueError(f"{path}: not a {SCHEMA} file")
        n, h, w = meta["n_frames"], meta["height"], meta["width"]
        out = {k: np.unpackbits(z[f"obj:{k}"], axis=1, count=h * w).reshape(n, h, w).astype(bool)
               for k in meta["objects"]}
    return meta, out


def mask_digest(m: dict[str, np.ndarray]) -> str:
    """SHA-256 over every object's name, shape and packed bits, in name order."""
    hsh = hashlib.sha256()
    for k in sorted(m):
        a = np.asarray(m[k], bool)
        hsh.update(f"{k}:{a.shape}\n".encode())
        hsh.update(np.packbits(a.reshape(a.shape[0], -1), axis=1).tobytes())
    return hsh.hexdigest()


# --- the R0.3 mask quality rule -------------------------------------------------
def quality_ok(series, start: int | None = None) -> list[bool]:
    """Per frame: False means the frame scores None. ``series`` is a list of areas or an (n, h, w)
    mask stack. A frame fails if its mask is empty, or if its area changes by more than 50 % from
    the previous frame (a non-empty frame after an empty one is an unbounded change, so it fails).

    ``start`` is a render mask's prompt frame (the creature's first frame fully clear of its home). SAM
    propagates forward only, so earlier frames are empty while the creature is still its drawing at
    home: they are valid (A(t) is the dilated home; ``regions.measured_region(..., at_home=True)``).
    The prompt frame is valid by definition, and the rule runs from the frame after it."""
    arr = np.asarray(series)
    areas = arr.reshape(arr.shape[0], -1).sum(axis=1) if arr.ndim == 3 else arr.astype(float)
    if start is not None and len(areas) and not 0 <= start < len(areas):
        raise ValueError(f"start frame {start} is outside the {len(areas)} frames")
    out = []
    for t, a in enumerate(areas):
        if start is not None and t <= start:
            out.append(True)
        elif a <= 0:
            out.append(False)
        elif t == 0:
            out.append(True)
        else:
            prev = areas[t - 1]
            out.append(bool(prev > 0 and abs(a - prev) / prev <= MAX_AREA_CHANGE))
    return out


def prompt_frame(prompts: dict, obj: str) -> int:
    """The earliest prompted frame for ``obj`` (for a render mask: its first frame clear of its home)."""
    return min(p[0] for p in prompts[obj])


# --- grid frames for the point-placing agent ------------------------------------
def grid_overlay(frame: np.ndarray, step: int = 64) -> np.ndarray:
    """A copy of ``frame`` (RGB) with a labelled pixel grid: a line every ``step`` px (every 4th
    heavier), x labels along the top and y labels down the left edge."""
    g = frame.copy()
    h, w = g.shape[:2]
    colour = (255, 0, 255)
    for x in range(step, w, step):
        cv2.line(g, (x, 0), (x, h - 1), colour, 2 if (x // step) % 4 == 0 else 1)
        cv2.putText(g, str(x), (x + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, colour, 1, cv2.LINE_AA)
    for y in range(step, h, step):
        cv2.line(g, (0, y), (w - 1, y), colour, 2 if (y // step) % 4 == 0 else 1)
        cv2.putText(g, str(y), (2, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, colour, 1, cv2.LINE_AA)
    return g


def write_grid_frames(frames: np.ndarray, indices, out_dir, step: int = 64) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in indices:
        p = out / f"grid_{i:04d}.png"
        cv2.imwrite(str(p), cv2.cvtColor(grid_overlay(frames[i], step), cv2.COLOR_RGB2BGR))
        paths.append(p)
    return paths


# --- CLI ------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m seam.masks", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    pt = sub.add_parser("track", help="SAM 2.1 tracks from a point-prompt file")
    pt.add_argument("--video", required=True, help="the 1280x720 analysis copy")
    pt.add_argument("--prompts", required=True)
    pt.add_argument("--out", required=True)
    pt.add_argument("--take", help="defaults to the prompt file's take")
    pg = sub.add_parser("grid", help="labelled grid frames for placing points")
    pg.add_argument("--video", required=True)
    pg.add_argument("--frames", required=True, help="comma-separated analysis frame indices")
    pg.add_argument("--out", required=True)
    pg.add_argument("--step", type=int, default=64)
    a = ap.parse_args(argv)

    if a.cmd == "grid":
        frames = sample_frames(a.video)
        for p in write_grid_frames(frames, [int(x) for x in a.frames.split(",")], a.out, a.step):
            print(p)
        return 0
    # the same frames the blind picker and placer saw: any 16:9 source, sampled onto the 1280x720 grid
    try:
        frames = analysis_frames(a.video)
    except ValueError as e:
        raise SystemExit(f"masks: refuse: {e}")
    prompts = load_prompts(a.prompts, size=frames.shape[1:3], n_frames=frames.shape[0])
    take = a.take or json.loads(Path(a.prompts).read_text(encoding="utf-8")).get("take") or Path(a.prompts).stem
    m = track(frames, prompts)
    from seam.util import sha256_file
    save_masks(a.out, m, take=take, extra={"source_size": list(video_size(a.video)),
                                           "prompts_sha256": sha256_file(a.prompts), "video_sha256": sha256_file(a.video)})
    q = {k: sum(quality_ok(v)) for k, v in m.items()}
    print(json.dumps({"out": a.out, "digest": mask_digest(m), "frames": int(frames.shape[0]),
                      "valid_frames": q}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
