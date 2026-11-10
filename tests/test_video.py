import json
import subprocess

import numpy as np
import pytest

import hashlib

from seam import video
from seam.video import SIZE, analysis_times, nearest_indices, read_video, reencode, resample, write_video


def _frames(n, w=320, h=180):
    out = np.zeros((n, h, w, 3), np.uint8) + 200
    for i in range(n):
        out[i, 40:80, 10 + 5 * i:50 + 5 * i] = 20
    return out


def test_analysis_times():
    t = analysis_times(2.0)
    assert len(t) == 31 and t[0] == 0 and t[-1] == pytest.approx(2.0)
    assert len(analysis_times(1.99)) == 30


def test_nearest_indices_30_and_24_fps():
    pts30 = np.arange(60) / 30
    assert list(nearest_indices(pts30, np.array([0, 1 / 15, 2 / 15]))) == [0, 2, 4]
    pts24 = np.arange(48) / 24
    # t = 1/15 = 0.0667: nearest 24 fps frame is 2/24 = 0.0833 (vs 1/24 = 0.0417)
    assert nearest_indices(pts24, np.array([1 / 15]))[0] == 2
    # an exact tie goes to the earlier frame
    assert nearest_indices(np.array([0.0, 1.0]), np.array([0.5]))[0] == 0


def test_resample_picks_frames():
    frames = np.arange(5)[:, None, None, None] * np.ones((1, 2, 2, 3), np.uint8)
    out = resample(frames, np.arange(5) / 10, np.array([0.0, 0.21, 0.4]))
    assert [int(f[0, 0, 0]) for f in out] == [0, 2, 4]


def test_write_read_round_trip(tmp_path):
    p = tmp_path / "a.mp4"
    write_video(p, _frames(15), fps=30)
    frames, pts = read_video(p, size=(320, 180))
    assert frames.shape == (15, 180, 320, 3)
    assert np.allclose(pts, np.arange(15) / 30, atol=1e-6)
    full, _ = read_video(p)
    assert full.shape[1:3] == (SIZE[1], SIZE[0])


@pytest.mark.parametrize("height", [720, 1080])
def test_reencode_heights(tmp_path, height):
    src = tmp_path / "src.mp4"
    write_video(src, _frames(10), fps=30)
    dst = reencode(src, tmp_path / f"null{height}.mp4", height)
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "json", str(dst)], capture_output=True, text=True, check=True).stdout)
    assert probe["streams"][0]["height"] == height
    frames, pts = read_video(dst)
    assert frames.shape == (10, 720, 1280, 3) and len(pts) == 10


def test_codec_null_is_deterministic_and_recorded(tmp_path):
    src = tmp_path / "src.mp4"
    write_video(src, _frames(12), fps=30)
    a = reencode(src, tmp_path / "a.mp4", 720)
    b = reencode(src, tmp_path / "b.mp4", 720)
    assert hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()
    info = video.codec_null_params()
    assert info["ffmpeg"].startswith("ffmpeg version")
    assert "-threads" in info["args"] and "threads=1" in info["args"]


def test_read_video_errors_on_empty_input(tmp_path):
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    with pytest.raises(ValueError):
        read_video(empty)
    audio = tmp_path / "a.m4a"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono", "-t", "0.2",
                    str(audio)], check=True)
    with pytest.raises(ValueError, match="no video stream"):
        read_video(audio)


def test_resample_refuses_a_short_render():
    frames = np.zeros((24, 2, 2, 3), np.uint8)
    pts = np.arange(24) / 24                                   # 0 .. 0.958 s
    resample(frames, pts, analysis_times(pts[-1]))             # fine
    with pytest.raises(ValueError, match="shorter"):
        resample(frames, pts, analysis_times(1.5))
