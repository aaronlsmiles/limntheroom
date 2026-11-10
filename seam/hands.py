"""The hand's invariant (R0.3, the hand take): MediaPipe keypoint drift.

One hand (the first MediaPipe returns), 21 landmarks in pixels on the take grid. Drift per frame
= mean distance between take and render landmarks / the diagonal of the take hand's landmark
bounding box. None when either side has no hand or the frame failed the gate.
The model file is models/hand_landmarker.task (see models/MODELS.md), IMAGE mode, so each frame
is read on its own: no tracking state carries a guess across frames.
"""
from pathlib import Path

import numpy as np

MODEL = Path(__file__).resolve().parents[1] / "models/hand_landmarker.task"
N_POINTS = 21


def keypoint_drift(take_kp, render_kp):
    if take_kp is None or render_kp is None:
        return None
    a = np.asarray(take_kp, float)
    b = np.asarray(render_kp, float)
    if a.shape != (N_POINTS, 2) or b.shape != (N_POINTS, 2):
        raise ValueError("keypoints must be (21, 2)")
    diag = float(np.hypot(*(a.max(0) - a.min(0))))
    if diag == 0:
        return None
    return float(np.linalg.norm(a - b, axis=1).mean() / diag)


class HandTracker:
    def __init__(self, model_path=MODEL):
        from mediapipe.tasks.python.core.base_options import BaseOptions
        from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode
        opts = HandLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(model_path)),
                                     running_mode=RunningMode.IMAGE, num_hands=1)
        self._lm = HandLandmarker.create_from_options(opts)

    def detect(self, frame_rgb):
        """(21, 2) pixel coordinates of the first hand, or None."""
        import mediapipe as mp
        f = np.ascontiguousarray(frame_rgb)
        res = self._lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=f))
        if not res.hand_landmarks:
            return None
        h, w = f.shape[:2]
        return np.array([[p.x * w, p.y * h] for p in res.hand_landmarks[0]], float)


def drift_series(take_tracker, render_tracker, take, render, valid):
    out = []
    for tf, rf, ok in zip(take, render, valid):
        out.append(keypoint_drift(take_tracker.detect(tf), render_tracker.detect(rf)) if ok else None)
    return out
