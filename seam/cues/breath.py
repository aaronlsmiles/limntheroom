"""Breath cue: a breath out across the page, heard in the take's WAV and, if it moves, seen on the page.

**Audio burst** (Aaron's ruling, 8 Nov 2026; hub call 126). Frames of 2048 samples, hop 512. Per frame:
RMS in dBFS. The take's room floor is the 10th percentile of its frame RMS. A frame is loud if its RMS
is at least ``rise_db`` (30 dB) above the room floor (and never below ``abs_floor_db``). Frames whose
window reaches into the first or last ``edge_s`` (0.5 s) of the take are ignored: the record button
clicks there. Runs of loud frames are merged across gaps under ``merge_gap`` s and kept if they last at
least ``min_dur`` (0.5 s). There is no spectral test: the iPhone 15 Pro records almost nothing above
3 kHz, so a real blow through the straw arrives as low-frequency wind, not hiss (call 124).

**Page flow.** A breath may barely move a taped page, so flow is evidence, not a requirement:
Farnebäck optical flow inside ``page_box`` between consecutive analysis frames; ``flow_peak`` is the
largest mean magnitude (px per frame) within the burst (± 0.2 s); ``flow_confirmed`` is whether it
exceeds ``flow_px``. Both are null when no frames are given.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from scipy.io import wavfile

from .sheet import make_event

N_FFT, HOP = 2048, 512

RISE_DB = 30.0          # a breath is at least this far above the take's room floor (10th percentile RMS)
MERGE_GAP_S = 0.1       # a breath broken by a gap this short is still one breath
MIN_DUR_S = 0.5         # shorter bursts are clicks and knocks; the protocol's breath is about 2 s (t04)
EDGE_S = 0.5            # s at each end of the take that never count: the record button's clicks
ABS_FLOOR_DB = -55.0    # dBFS: never call anything quieter a breath, even in a silent take
FLOW_MARGIN_S = 0.2     # s: page flow is searched this far either side of the burst (the page lags the air)
FLOW_PX = 0.5           # px per frame of mean page flow that counts as the page moving


def read_wav(path) -> tuple[np.ndarray, int]:
    """Mono float32 in [-1, 1] and the sample rate."""
    sr, data = wavfile.read(str(path))
    x = data.astype(np.float64)
    if np.issubdtype(data.dtype, np.integer):
        x /= float(np.iinfo(data.dtype).max)
    if x.ndim == 2:
        x = x.mean(axis=1)
    return x.astype(np.float32), int(sr)


def audio_features(x: np.ndarray, sr: int):
    """(frame centre times s, RMS dBFS), one value per hop."""
    if x.size < N_FFT:
        x = np.pad(x, (0, N_FFT - x.size))
    n = 1 + (x.size - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    rms = np.sqrt(np.mean(x[idx] ** 2, axis=1))
    rms_db = 20 * np.log10(np.maximum(rms, 1e-10))
    t = (HOP * np.arange(n) + N_FFT / 2) / sr
    return t, rms_db


def bursts(t, rms_db, duration, rise_db=RISE_DB, merge_gap=MERGE_GAP_S, min_dur=MIN_DUR_S, edge_s=EDGE_S,
           abs_floor_db=ABS_FLOOR_DB, sr=48000):
    """([(start s, end s, frame slice)] of breath-like runs, room floor dBFS). ``duration`` is the take's
    length in s; a frame whose window reaches into its first or last ``edge_s`` is never loud."""
    floor = float(np.percentile(rms_db, 10))
    half = N_FFT / 2 / sr
    inside = (t - half >= edge_s) & (t + half <= duration - edge_s)
    on = (rms_db >= max(floor + rise_db, abs_floor_db)) & inside
    runs, i, n = [], 0, len(on)
    hop_s = (t[1] - t[0]) if n > 1 else HOP / sr
    while i < n:
        if on[i]:
            j = i
            while j < n and on[j]:
                j += 1
            runs.append([i, j])
            i = j
        else:
            i += 1
    merged: list[list[int]] = []
    for r in runs:
        if merged and (r[0] - merged[-1][1]) * hop_s < merge_gap:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    out = []
    for a, b in merged:
        start, end = t[a] - hop_s / 2, t[b - 1] + hop_s / 2
        if end - start >= min_dur:
            out.append((float(start), float(end), slice(a, b)))
    return out, floor


def page_flow(frames, page_box=None) -> np.ndarray:
    """Mean Farnebäck flow magnitude per frame (index i holds the flow from frame i-1 to i; [0] = 0)."""
    g = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) for f in frames]
    if page_box is not None:
        x, y, w, h = page_box
        g = [im[y:y + h, x:x + w] for im in g]
    out = [0.0]
    for a, b in zip(g, g[1:]):
        fl = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        out.append(float(np.hypot(fl[..., 0], fl[..., 1]).mean()))
    return np.array(out)


def detect(wav, *, frames=None, fps: float = 15, page_box=None, flow_px: float = FLOW_PX, **burst_kw) -> list[dict]:
    x, sr = read_wav(wav)
    t, rms_db = audio_features(x, sr)
    found, floor = bursts(t, rms_db, x.size / sr, sr=sr, **burst_kw)
    flow = page_flow(frames, page_box) if frames is not None else None
    out = []
    for start, end, sl in found:
        peak = confirmed = None
        if flow is not None:
            a = max(0, int(np.floor((start - FLOW_MARGIN_S) * fps)))
            b = min(len(flow), int(np.ceil((end + FLOW_MARGIN_S) * fps)) + 1)
            peak = round(float(flow[a:b].max()), 3) if b > a else 0.0
            confirmed = bool(peak > flow_px)
        out.append(make_event(
            t=max(0.0, start), t_end=end, cue="breath", what="someone breathes out across the page",
            source="detector:breath",
            evidence={"rms_db_peak": round(float(rms_db[sl].max()), 1), "noise_floor_db": round(floor, 1),
                      "rise_db_peak": round(float(rms_db[sl].max()) - floor, 1), "flow_peak": peak,
                      "flow_confirmed": confirmed, "wav": Path(wav).name}))
    return out
