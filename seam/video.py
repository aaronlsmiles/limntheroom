"""Decode by timestamp onto the 1280×720 analysis grid; codec-null re-encodes.

Each stream keeps its own presentation timestamps. Analysis time t_i = i / 15 takes the
source frame whose pts is nearest (a tie goes to the earlier frame), so a 24 fps render and a
30 fps take land on the same 15 fps grid without assuming either rate.
"""
import subprocess
from pathlib import Path

import numpy as np

from seam.util import ffmpeg_version  # noqa: F401  (re-exported: the null records name the build)

SIZE = (1280, 720)          # (width, height)
FPS = 15
# One thread everywhere, so a re-encode is byte-identical run to run (x264's frame threads
# can reorder lookahead decisions).
CODEC_NULL = ("-threads", "1", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
              "-x264-params", "threads=1", "-pix_fmt", "yuv420p", "-an")


def read_video(path, size=SIZE):
    """(frames (N,H,W,3) uint8 RGB resized to size with INTER_AREA, pts in seconds from the first).

    Each frame is resized as it is decoded, into a buffer preallocated from the stream's frame
    count (grown if the count was short). A frame without pts takes its decoder time, else
    index / average rate. Raises ValueError on unreadable or frameless input."""
    import av
    import cv2
    w, h = size
    try:
        c = av.open(str(path))
    except (av.error.FFmpegError, OSError) as e:
        raise ValueError(f"{path}: cannot open: {e}") from e
    with c:
        if not c.streams.video:
            raise ValueError(f"{path}: no video stream")
        s = c.streams.video[0]
        rate = float(s.average_rate) if s.average_rate else None
        buf = np.empty((max(int(s.frames or 0), 1) + 2, h, w, 3), np.uint8)
        pts = []
        for i, f in enumerate(c.decode(s)):
            img = f.to_ndarray(format="rgb24")
            if (img.shape[1], img.shape[0]) != (w, h):
                img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
            if i >= len(buf):
                buf = np.concatenate([buf, np.empty_like(buf)])
            buf[i] = img
            if f.pts is not None:
                pts.append(float(f.pts * s.time_base))
            elif f.time is not None:
                pts.append(float(f.time))
            elif rate:
                pts.append(i / rate)
            else:
                raise ValueError(f"{path}: frame {i} has no timestamp and the stream no rate")
    if not pts:
        raise ValueError(f"{path}: no video frames")
    frames = buf[:len(pts)]
    pts = np.asarray(pts, float)
    order = np.argsort(pts, kind="stable")
    if not np.array_equal(order, np.arange(len(order))):
        frames = frames[order]
    return frames, pts[order] - pts[order][0]


def analysis_times(last_pts, fps=FPS):
    return np.arange(int(np.floor(fps * last_pts + 1e-9)) + 1) / fps


def nearest_indices(pts, times):
    """Index of the nearest pts for each time; an exact tie goes to the earlier frame."""
    pts = np.asarray(pts, float)
    times = np.asarray(times, float)
    hi = np.clip(np.searchsorted(pts, times, side="left"), 0, len(pts) - 1)
    lo = np.clip(hi - 1, 0, len(pts) - 1)
    take_lo = np.abs(times - pts[lo]) <= np.abs(pts[hi] - times)
    return np.where(take_lo, lo, hi)


def covers(pts, times):
    """True if the stream's pts cover the analysis times to within half a source frame."""
    pts = np.asarray(pts, float)
    times = np.asarray(times, float)
    if not len(times):
        return True
    if not len(pts):
        return False
    step = float(np.median(np.diff(pts))) if len(pts) > 1 else 0.0
    return not (times.max() > pts.max() + step / 2 + 1e-9 or times.min() < pts.min() - step / 2 - 1e-9)


def resample(frames, pts, times):
    """Frames at the analysis times; raises if the stream does not cover them (more than half
    a source frame short at either end)."""
    pts = np.asarray(pts, float)
    times = np.asarray(times, float)
    if not covers(pts, times):
        raise ValueError(f"stream shorter than the analysis span: pts {pts.min():.3f}-{pts.max():.3f} s, "
                         f"times {times.min():.3f}-{times.max():.3f} s")
    return np.asarray(frames)[nearest_indices(pts, times)]


def reencode(src, dst, height):
    """The codec null: H.264 CRF 18 at the given height (width even, aspect kept)."""
    dst = Path(dst)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-threads", "1", "-i", str(src),
                    "-vf", f"scale=-2:{int(height)}:flags=lanczos", *CODEC_NULL, str(dst)], check=True)
    return dst


def codec_null_params():
    """What the codec null was encoded with, for the output records."""
    return {"ffmpeg": ffmpeg_version(), "args": list(CODEC_NULL), "scale": "scale=-2:<height>:flags=lanczos",
            "heights": [720, 1080]}


def write_video(path, frames, fps):
    """Lossless-ish H.264 (CRF 0, yuv444p) for fixtures."""
    import av
    frames = np.asarray(frames)
    with av.open(str(path), "w") as c:
        s = c.add_stream("libx264", rate=int(fps))
        s.width, s.height = frames.shape[2], frames.shape[1]
        s.pix_fmt = "yuv444p"
        s.options = {"crf": "0"}
        for f in frames:
            for pkt in s.encode(av.VideoFrame.from_ndarray(f, format="rgb24")):
                c.mux(pkt)
        for pkt in s.encode():
            c.mux(pkt)
