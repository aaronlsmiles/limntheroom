#!/usr/bin/env python3
"""Phase 1.5 ingest: an iPhone original -> the render input, the analysis copy and the WAV.

    python seam/ingest.py raw/IMG_0001.MOV --take t01 --attempt a

From one original (HEVC or H.264, possibly HDR, possibly variable frame rate, with audio):

  SHA-256        of the original, as it sits in raw/ (which ingest never writes to);
  render input   takes/<id>.render.mp4: SDR Rec.709 H.264 1080p30 CFR (never above 30 fps), CRF 12,
                 no audio, metadata stripped, colour tags bt709/bt709/bt709/tv;
  analysis copy  takes/<id>.analysis.mp4: the same at 1280x720 (the registered grid), 30 fps CFR
                 (the analysis clock reads it by timestamp at 15 fps, seam/video.py);
  WAV            takes/<id>.wav: mono, 48 kHz, 16-bit, aligned to the video's first frame, for the
                 breath detector (none if the original has no audio);
  record         one row per take in capture/ingest.json (schema p47-ingest/1): hashes, sizes, rates,
                 HDR and VFR flags, the ffmpeg version. No timestamps, no absolute paths, no device
                 or location metadata, so a re-run gives the same row.

A take longer than 30 s is refused (Runway's input limit). A source that is not 16:9, or is smaller
than 1280x720, is refused: the analysis grid is 1280x720 and a stretch would move every line.
HDR video (PQ or HLG; the protocol says HDR Video off, so this is the safety net) is tone-mapped to
SDR and flagged. This ffmpeg has no zscale, so the conversion is built from stock filters: the
YUV -> float RGB conversion by swscale, the transfer function as a 1-D LUT (PQ, or HLG with a
per-channel system gamma of 1.2) into units of 100 nits, BT.2020 -> BT.709 primaries by a 3x3
matrix in linear light, ffmpeg's `tonemap=hable:desat=0:peak=10` (1,000 nits -> 1.0), the BT.709
OETF as a LUT, then RGB -> limited-range BT.709 YUV. A Dolby Vision file is read through its base
layer (iPhone HDR is HLG underneath). Encodes are single-threaded and bit-exact, so the hashes are
stable run to run on one ffmpeg build.

Run order after ingest: take masks and cue sheets; codec nulls and the paste / shift controls
(seam/controls_inputs.py); the no-op null, whose request is compiled with `--trim-to 10` (a 10 s clip,
like the probe); renders; then seam/assemble.py once per render.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from seam.util import ffmpeg_version, sha256_file  # noqa: E402

SCHEMA = "p47-ingest/1"
MAX_SECONDS = 30.0
RENDER_SIZE = (1920, 1080)
ANALYSIS_SIZE = (1280, 720)
FPS = 30
CRF = 12
PRESET = "medium"
WAV_RATE = 48000
LUT_SIZE = 16384
TONEMAP = "hable"
TONEMAP_PEAK = 10            # in units of 100 nits: a 1,000 nit display
HLG_GAMMA = 1.2              # system gamma of a 1,000 nit display, applied per channel
VFR_TOLERANCE = 0.2          # frame intervals differing by more than 20 % of the median are variable
# BT.2020 -> BT.709 primaries in linear light (ITU-R BT.2087)
M2020_TO_709 = ((1.6605, -0.5876, -0.0728), (-0.1246, 1.1329, -0.0083), (-0.0182, -0.1006, 1.1187))
HDR_TRC = {"smpte2084": "pq", "arib-std-b67": "hlg"}
MATRIX = {"bt709": "bt709", "bt2020nc": "bt2020", "bt2020c": "bt2020", "smpte170m": "smpte170m",
          "bt470bg": "smpte170m", "smpte240m": "smpte240m"}
_NAME = re.compile(r"^[a-z][a-z0-9]{0,15}$")
_ATTEMPT = re.compile(r"^[a-z]$")


class IngestError(ValueError):
    pass


# ---- small helpers --------------------------------------------------------------------------------------
def _rel(path, root):
    p = Path(path).resolve()
    try:
        return p.relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return p.name


def _num(x, nd=3):
    x = round(float(x), nd)
    return int(x) if x == int(x) else x


def check_duration(seconds):
    if not seconds or seconds <= 0:
        raise IngestError("the video has no duration")
    if seconds > MAX_SECONDS + 1e-6:
        raise IngestError(f"a take is at most {MAX_SECONDS:g} s (Runway's input limit); this one is "
                          f"{seconds:.2f} s. Trim it first.")


# ---- probing ---------------------------------------------------------------------------------------------
def ffprobe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise IngestError(f"{Path(path).name}: not a readable media file: {r.stderr.strip()[:200]}")
    return json.loads(r.stdout)


def video_stream(info):
    for s in info.get("streams", []):
        if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic"):
            return s
    raise IngestError("no video stream")


def audio_stream(info):
    for s in info.get("streams", []):
        if s.get("codec_type") == "audio":
            return s
    return None


def packet_times(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return np.array(sorted(float(x) for x in r.stdout.split() if x.strip() and x.strip() != "N/A"))


def is_vfr(times):
    """True if the frame intervals are not constant (a dropped or held frame doubles one)."""
    d = np.diff(np.asarray(times, float))
    if len(d) < 2:
        return False
    return bool(np.ptp(d) > VFR_TOLERANCE * np.median(d))


def detect_hdr(stream):
    """(is_hdr, evidence) from the stream's transfer function and side data."""
    trc = stream.get("color_transfer")
    if trc in HDR_TRC:
        return True, f"color_transfer={trc}"
    for sd in stream.get("side_data_list", []) or []:
        t = str(sd.get("side_data_type", ""))
        if "DOVI" in t or "Dolby Vision" in t:
            return True, "Dolby Vision configuration record"
    return False, ""


def hdr_kind(stream):
    trc = stream.get("color_transfer")
    if trc in HDR_TRC:
        return HDR_TRC[trc]
    raise IngestError("a Dolby Vision file without a PQ or HLG base layer cannot be tone-mapped; "
                      "film with HDR Video off")


def rotation(stream):
    for sd in stream.get("side_data_list", []) or []:
        if "rotation" in sd:
            return int(round(float(sd["rotation"]))) % 360
    r = (stream.get("tags") or {}).get("rotate")
    return int(r) % 360 if r else 0


def display_size(stream):
    w, h = int(stream["width"]), int(stream["height"])
    return (h, w) if rotation(stream) in (90, 270) else (w, h)


def stream_duration(info, stream):
    for d in (stream.get("duration"), info.get("format", {}).get("duration")):
        try:
            if d not in (None, "N/A") and float(d) > 0:
                return float(d)
        except ValueError:
            pass
    return 0.0


def _start(stream):
    try:
        return float(stream.get("start_time") or 0.0)
    except ValueError:
        return 0.0


# ---- the HDR -> SDR chain ----------------------------------------------------------------------------
def eotf_lut(kind, n=LUT_SIZE):
    """Display light in units of 100 nits for coded values linspace(0, 1, n).

    PQ is SMPTE ST 2084 (10,000 nits at 1.0 -> 100). HLG is BT.2100: the inverse OETF to scene light
    E, then a per-channel system gamma of 1.2 and a 1,000 nit peak (1.0 -> 10)."""
    x = np.linspace(0.0, 1.0, n)
    if kind == "pq":
        m1, m2 = 2610 / 16384, 2523 / 4096 * 128
        c1, c2, c3 = 3424 / 4096, 2413 / 4096 * 32, 2392 / 4096 * 32
        p = np.power(x, 1 / m2)
        return 10000.0 * np.power(np.maximum(p - c1, 0.0) / (c2 - c3 * p), 1 / m1) / 100.0
    if kind == "hlg":
        a = 0.17883277
        b = 1 - 4 * a
        c = 0.5 - a * np.log(4 * a)
        E = np.where(x <= 0.5, x * x / 3.0, (np.exp((x - c) / a) + b) / 12.0)
        return 10.0 * np.power(E, HLG_GAMMA)
    raise ValueError(f"unknown HDR transfer {kind!r}")


def oetf_lut(n=LUT_SIZE):
    """The BT.709 OETF on linear values linspace(0, 1, n)."""
    x = np.linspace(0.0, 1.0, n)
    return np.where(x < 0.018, 4.5 * x, 1.099 * np.power(x, 0.45) - 0.099)


def write_cube(path, values):
    lines = [f"LUT_1D_SIZE {len(values)}"] + [f"{v:.9g} {v:.9g} {v:.9g}" for v in values]
    Path(path).write_text("\n".join(lines) + "\n")


def _scale_in(stream):
    """The swscale input options: the stream's own matrix and range."""
    matrix = MATRIX.get(stream.get("color_space"), "bt2020" if stream.get("color_primaries") == "bt2020" else "bt709")
    rng = "full" if stream.get("color_range") == "pc" else "limited"
    return matrix, rng


TAGS = "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv"


def video_filter(size, stream, kind=None):
    """The -vf chain for one output size. kind is None (SDR) or 'pq' / 'hlg' (tone-mapped; the LUT
    files eotf.cube and oetf.cube must sit in the working directory)."""
    w, h = size
    matrix, rng = _scale_in(stream)
    head = f"setpts=PTS-STARTPTS,fps={FPS}"
    if kind is None:
        return (f"{head},scale=w={w}:h={h}:flags=lanczos+accurate_rnd+full_chroma_int:in_range={rng}:"
                f"in_color_matrix={matrix}:out_range=limited:out_color_matrix=bt709,format=yuv420p,{TAGS}")
    mix = ":".join(f"{ch}{c}={M2020_TO_709[i][j]}" for i, ch in enumerate("rgb") for j, c in enumerate("rgb"))
    return (f"{head},scale=w={w}:h={h}:flags=lanczos+accurate_rnd+full_chroma_int:in_range={rng}:"
            f"in_color_matrix={matrix}:out_range=full,format=gbrpf32le,"
            f"lut1d=file=eotf.cube:interp=linear,colorchannelmixer={mix},"
            f"tonemap=tonemap={TONEMAP}:desat=0:peak={TONEMAP_PEAK},"
            f"lut1d=file=oetf.cube:interp=linear,"
            f"scale=in_range=full:out_range=limited:out_color_matrix=bt709,format=yuv420p,{TAGS}")


COMMON = ["-hide_banner", "-nostdin", "-y", "-v", "error", "-threads", "1"]
BITEXACT = ["-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact"]
X264 = ["-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF), "-pix_fmt", "yuv420p", "-threads", "1",
        "-x264-params", "threads=1:rc-lookahead=40", "-colorspace", "bt709", "-color_primaries", "bt709",
        "-color_trc", "bt709", "-color_range", "tv", "-fps_mode", "cfr", "-r", str(FPS)]


def encode_video(src, dst, size, stream, kind, workdir):
    if kind is not None:
        write_cube(Path(workdir) / "eotf.cube", eotf_lut(kind))
        write_cube(Path(workdir) / "oetf.cube", oetf_lut())
    cmd = ["ffmpeg", *COMMON, "-filter_threads", "1", "-i", str(src), "-map", "0:v:0", "-an", "-sn", "-dn",
           "-vf", video_filter(size, stream, kind), *X264, "-map_metadata", "-1", "-map_chapters", "-1",
           "-metadata:s:v:0", "handler_name=", *BITEXACT, "-movflags", "+faststart", "-f", "mp4", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=workdir)
    if r.returncode != 0:
        raise IngestError(f"ffmpeg failed on {Path(src).name}: {r.stderr.strip()[-400:]}")


def audio_filter(offset):
    """Align the audio's t=0 to the video's first frame. offset = audio start - video start (s).

    The stream's own start time is removed first (asetpts), so `-t` and the WAV length count from
    the first sample; then the audio is delayed by the offset, or its head trimmed if it started early."""
    f = ["asetpts=PTS-STARTPTS"]
    if offset > 0.0005:
        f.append(f"adelay=delays={offset * 1000:.3f}:all=1")
    elif offset < -0.0005:
        f.append(f"atrim=start={-offset:.6f}")
        f.append("asetpts=PTS-STARTPTS")
    f.append(f"aresample={WAV_RATE}")
    return ",".join(f)


def encode_wav(src, dst, offset, seconds, workdir):
    cmd = ["ffmpeg", *COMMON, "-i", str(src), "-map", "0:a:0", "-vn", "-sn", "-dn", "-af", audio_filter(offset),
           "-ac", "1", "-ar", str(WAV_RATE), "-c:a", "pcm_s16le", "-t", f"{seconds:.6f}", "-map_metadata", "-1",
           *BITEXACT, "-f", "wav", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=workdir)
    if r.returncode != 0:
        raise IngestError(f"ffmpeg failed on the audio of {Path(src).name}: {r.stderr.strip()[-400:]}")


# ---- ingest ------------------------------------------------------------------------------------------------
def _entry(path, root):
    return {"path": _rel(path, root), "sha256": sha256_file(path), "bytes": Path(path).stat().st_size}


def _write_json_atomic(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    os.replace(tmp, path)


def read_ingest_json(path):
    """The rows of capture/ingest.json (empty if it does not exist yet); IngestError if it is unreadable
    or not p47-ingest/1, so a bad record is found before anything is encoded."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise IngestError(f"{path.name}: the ingest record is not readable JSON: {e}") from e
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA or not isinstance(doc.get("rows"), list):
        raise IngestError(f"{path.name}: the ingest record is not {SCHEMA} (schema "
                          f"{doc.get('schema') if isinstance(doc, dict) else None!r}, rows missing or not a list)")
    return doc["rows"]


def update_ingest_json(path, row, rows=None):
    """Insert or replace the row with this take_id; rows stay sorted by take_id."""
    rows = read_ingest_json(path) if rows is None else rows
    rows = [r for r in rows if r["take_id"] != row["take_id"]] + [row]
    rows.sort(key=lambda r: r["take_id"])
    _write_json_atomic(path, {"schema": SCHEMA, "rows": rows})


def ingest(original, take, attempt=None, *, root=REPO, raw_dir=None, out_dir=None, ingest_path=None):
    """Ingest one original; returns its capture/ingest.json row. Nothing is written on a refusal, and a
    missing or failing ffmpeg / ffprobe, or output that is not JSON, is an IngestError."""
    try:
        return _ingest(original, take, attempt, root=root, raw_dir=raw_dir, out_dir=out_dir, ingest_path=ingest_path)
    except FileNotFoundError as e:
        raise IngestError(f"a required tool or file is missing ({e.filename or e}): is ffmpeg / ffprobe installed?") from e
    except subprocess.CalledProcessError as e:
        tool = e.cmd if isinstance(e.cmd, str) else e.cmd[0]
        raise IngestError(f"{Path(str(tool)).name} failed (exit {e.returncode})") from e
    except json.JSONDecodeError as e:
        raise IngestError(f"ffprobe output is not JSON: {e}") from e


def _ingest(original, take, attempt, *, root, raw_dir, out_dir, ingest_path):
    root = Path(root)
    raw_dir = Path(raw_dir) if raw_dir else root / "raw"
    out_dir = Path(out_dir) if out_dir else root / "takes"
    ingest_path = Path(ingest_path) if ingest_path else root / "capture/ingest.json"
    if not _NAME.match(take or ""):
        raise IngestError(f"take name {take!r}: lowercase letters and digits, starting with a letter (e.g. t01)")
    if attempt is not None and not _ATTEMPT.match(attempt):
        raise IngestError(f"attempt {attempt!r}: one lowercase letter")
    take_id = take + (attempt or "")
    original = Path(original)
    if not original.is_file():
        raise IngestError(f"{original}: no such file")
    if not original.resolve().is_relative_to(raw_dir.resolve()):
        raise IngestError(f"{original.name} is not in {raw_dir}: put originals in raw/ (gitignored) first; "
                          "ingest never writes there")
    for what, p in (("the output directory", out_dir), ("the ingest record", ingest_path)):
        if Path(p).resolve().is_relative_to(raw_dir.resolve()):
            raise IngestError(f"{what} {p} is inside {raw_dir}: originals stay untouched in raw/")
    rows = read_ingest_json(ingest_path)             # a bad record is found before anything is encoded

    info = ffprobe(original)
    v = video_stream(info)
    a = audio_stream(info)
    seconds = stream_duration(info, v)
    check_duration(seconds)
    w, h = display_size(v)
    if abs(w / h - 16 / 9) > 0.01:
        raise IngestError(f"{original.name} is {w}x{h}, not 16:9; the analysis grid is 1280x720")
    if h < ANALYSIS_SIZE[1]:
        raise IngestError(f"{original.name} is {w}x{h}, below the 1280x720 analysis grid")
    hdr, evidence = detect_hdr(v)
    kind = hdr_kind(v) if hdr else None
    times = packet_times(original)
    vfr = is_vfr(times)
    fps_src = Fraction(v.get("avg_frame_rate") or "0/1")
    warnings = []
    if not hdr and (v.get("color_primaries") not in (None, "bt709", "unknown", "unspecified")
                    or v.get("color_transfer") not in (None, "bt709", "unknown", "unspecified")):
        warnings.append(f"source tagged {v.get('color_primaries')}/{v.get('color_transfer')}; "
                        "only the matrix was converted")

    out_dir.mkdir(parents=True, exist_ok=True)
    final = {"render": out_dir / f"{take_id}.render.mp4", "analysis": out_dir / f"{take_id}.analysis.mp4",
             "wav": out_dir / f"{take_id}.wav"}
    # the work directory sits beside the outputs, so the final os.replace never crosses a filesystem
    with tempfile.TemporaryDirectory(prefix=".ingest-", dir=out_dir) as td:
        parts = {k: Path(td) / p.name for k, p in final.items()}
        encode_video(original, parts["render"], RENDER_SIZE, v, kind, td)
        encode_video(original, parts["analysis"], ANALYSIS_SIZE, v, kind, td)
        if a is not None:
            encode_wav(original, parts["wav"], _start(a) - _start(v), seconds, td)
        for k, p in parts.items():
            if p.exists():
                os.replace(p, final[k])
    if a is None:
        final["wav"].unlink(missing_ok=True)

    r_info = ffprobe(final["render"])
    rv = video_stream(r_info)
    row = {
        "schema": SCHEMA, "take_id": take_id, "take": take, "attempt": attempt,
        "original": _entry(original, root),
        "outputs": {"render": _entry(final["render"], root), "analysis": _entry(final["analysis"], root),
                    "wav": _entry(final["wav"], root) if a is not None else None},
        "duration_s": _num(seconds), "frames_render": int(rv.get("nb_frames") or 0),
        "fps_source": _num(float(fps_src)), "fps_render": FPS, "vfr_detected": vfr,
        "size_source": [w, h], "size_render": list(RENDER_SIZE), "size_analysis": list(ANALYSIS_SIZE),
        "rotation": rotation(v), "codec_source": v.get("codec_name"), "pix_fmt_source": v.get("pix_fmt"),
        "hdr_detected": hdr, "hdr_evidence": evidence, "hdr_kind": kind,
        "has_audio": a is not None, "ffmpeg": ffmpeg_version(),
        "recipe": {"crf": CRF, "preset": PRESET, "tonemap": TONEMAP if hdr else None,
                   "tonemap_peak": TONEMAP_PEAK if hdr else None},
        "warnings": warnings,
    }
    update_ingest_json(ingest_path, row, rows)
    return row


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("original")
    ap.add_argument("--take", required=True, help="take name, e.g. t01")
    ap.add_argument("--attempt", help="attempt letter, e.g. a")
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--raw")
    ap.add_argument("--out")
    ap.add_argument("--ingest")
    a = ap.parse_args(argv)
    try:
        row = ingest(a.original, a.take, a.attempt, root=a.root, raw_dir=a.raw, out_dir=a.out, ingest_path=a.ingest)
    except IngestError as e:
        print(f"ingest: refuse: {e}", file=sys.stderr)
        return 1
    print(row["take_id"], "hdr" if row["hdr_detected"] else "sdr", "vfr" if row["vfr_detected"] else "cfr")
    for k, o in row["outputs"].items():
        if o:
            print(f"  {k:9s} {o['sha256']}  {o['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
