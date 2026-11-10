"""Environment check: every dependency imports, and SAM 2.1 small builds on CPU."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CKPT = ROOT / "models" / "sam2.1_hiera_small.pt"


def test_imports():
    import numpy, cv2, skimage, scipy, av, imageio, mediapipe, PIL, torch, torchvision  # noqa: F401
    import Vision  # noqa: F401  (pyobjc-framework-Vision, macOS only)
    import sam2  # noqa: F401


def test_sam2_video_predictor_builds_on_cpu():
    import torch
    from sam2.build_sam import build_sam2_video_predictor

    assert CKPT.exists(), "run the download in models/MODELS.md first"
    pred = build_sam2_video_predictor(
        "configs/sam2.1/sam2.1_hiera_s.yaml", str(CKPT), device="cpu"
    )
    assert next(pred.parameters()).device.type == "cpu"
    assert isinstance(pred, torch.nn.Module)
