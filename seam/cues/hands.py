"""Hands cue: when a hand comes into view and when it leaves (MediaPipe Hand Landmarker).

The heavy front end (``HandDetector``, VIDEO running mode) gives one presence flag per analysis
frame; ``presence_intervals`` debounces the flags into [enter, leave) frame intervals. One event per
interval: ``t`` = enter, ``t_end`` = leave, or null if the hand is still in view at the end.

Sub-plan C's ``seam/hands.py`` (keypoint drift) is a different module.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .sheet import make_event

ROOT = Path(__file__).resolve().parent.parent.parent
MODEL = ROOT / "models" / "hand_landmarker.task"

# Debounce, in 15 fps analysis frames (0.2 s each): a hand must be seen for 3 frames to count, and a
# dropout shorter than 3 frames (a missed detection while the hand moves) does not split its interval.
MIN_ON = 3
MIN_OFF = 3


def presence_intervals(presence, min_on: int = MIN_ON, min_off: int = MIN_OFF) -> list[tuple[int, int]]:
    """[enter, leave) frame intervals. Gaps shorter than ``min_off`` frames are bridged first;
    runs shorter than ``min_on`` frames are then dropped."""
    p = [bool(x) for x in presence]
    runs, i, n = [], 0, len(p)
    while i < n:
        if p[i]:
            j = i
            while j < n and p[j]:
                j += 1
            runs.append([i, j])
            i = j
        else:
            i += 1
    merged: list[list[int]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < min_off:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [(a, b) for a, b in merged if b - a >= min_on]


def detect_from_presence(presence, fps: float, min_on: int = MIN_ON, min_off: int = MIN_OFF) -> list[dict]:
    n = len(presence)
    out = []
    for a, b in presence_intervals(presence, min_on, min_off):
        open_end = b >= n
        out.append(make_event(
            t=a / fps, t_end=None if open_end else b / fps, cue="hand", what="a hand comes into view",
            source="detector:hands",
            evidence={"enter_frame": a, "leave_frame": None if open_end else b,
                      "frames_present": int(sum(bool(x) for x in presence[a:b])), "open_at_end": open_end}))
    return out


class HandDetector:
    """MediaPipe Hand Landmarker in VIDEO mode (timestamps must increase). Use as a context manager."""

    def __init__(self, model=MODEL, num_hands: int = 2, min_conf: float = 0.5):
        if not Path(model).is_file():
            raise FileNotFoundError(f"hand landmarker model not found at {model}; download it as in models/MODELS.md")
        from mediapipe.tasks.python.core.base_options import BaseOptions
        from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode

        opts = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model)), running_mode=RunningMode.VIDEO,
            num_hands=num_hands, min_hand_detection_confidence=min_conf,
            min_hand_presence_confidence=min_conf, min_tracking_confidence=min_conf)
        self._lm = HandLandmarker.create_from_options(opts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self._lm.close()

    def landmarks(self, frame_rgb: np.ndarray, index: int, fps: float):
        import mediapipe as mp

        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(frame_rgb))
        return self._lm.detect_for_video(img, int(round(index * 1000 / fps))).hand_landmarks

    def present(self, frame_rgb: np.ndarray, index: int, fps: float) -> bool:
        return len(self.landmarks(frame_rgb, index, fps)) > 0


def presence(frames, fps: float, model=MODEL) -> list[bool]:
    with HandDetector(model) as det:
        return [det.present(f, i, fps) for i, f in enumerate(frames)]


def detect(frames, fps: float, model=MODEL, min_on: int = MIN_ON, min_off: int = MIN_OFF) -> list[dict]:
    return detect_from_presence(presence(frames, fps, model), fps, min_on, min_off)
