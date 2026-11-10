"""Time SAM 2.1 small propagation on CPU over a synthetic 1280x720, 150-frame clip
(10 s at 15 fps) with a moving shape and one click prompt. Prints seconds per frame."""
import shutil
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
CKPT = ROOT / "models" / "sam2.1_hiera_small.pt"
W, H, N = 1280, 720, 150


def make_clip(d: Path):
    for i in range(N):
        img = np.full((H, W, 3), 235, np.uint8)
        cv2.rectangle(img, (0, 560), (W, H), (200, 210, 220), -1)  # backdrop
        cx = int(250 + 780 * i / (N - 1))
        cy = int(360 + 80 * np.sin(i / 12))
        cv2.circle(img, (cx, cy), 70, (30, 40, 200), -1)
        cv2.circle(img, (cx + 25, cy - 20), 12, (255, 255, 255), -1)
        cv2.imwrite(str(d / f"{i:05d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])


def main():
    from sam2.build_sam import build_sam2_video_predictor

    torch.set_grad_enabled(False)
    tmp = Path(tempfile.mkdtemp(prefix="sam2clip_"))
    try:
        make_clip(tmp)
        pred = build_sam2_video_predictor(
            "configs/sam2.1/sam2.1_hiera_s.yaml", str(CKPT), device="cpu"
        )
        t0 = time.perf_counter()
        state = pred.init_state(video_path=str(tmp))  # includes frame loading/resize
        t_init = time.perf_counter() - t0
        pred.add_new_points_or_box(
            state, frame_idx=0, obj_id=1,
            points=np.array([[250, 360]], np.float32), labels=np.array([1], np.int32),
        )
        t0 = time.perf_counter()
        n = 0
        for _ in pred.propagate_in_video(state):
            n += 1
        t_prop = time.perf_counter() - t0
        print(f"frames={n} init={t_init:.1f}s propagate={t_prop:.1f}s "
              f"seconds_per_frame={t_prop / n:.3f} threads={torch.get_num_threads()}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
