"""seam/ingest.py (Phase 1.5): originals -> render input, analysis copy, WAV, capture/ingest.json.

Every clip is synthetic (ffmpeg lavfi). No real take is read.
"""
import hashlib
import json
import subprocess
import wave
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pytest

from seam import ingest

REPO = Path(__file__).resolve().parent.parent


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def probe(path, entries="stream=codec_name,pix_fmt,width,height,r_frame_rate,avg_frame_rate,color_space,"
                        "color_primaries,color_transfer,color_range,nb_frames,duration"):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", entries,
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)["streams"][0]


def format_tags(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out).get("format", {}).get("tags", {})


def pts_deltas(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True).stdout
    t = np.array(sorted(float(x) for x in out.split() if x.strip()))
    return np.diff(t)


def y_planes(path):
    """Mean luma (limited-range code values) of each vertical third of the first frame."""
    with av.open(str(path)) as c:
        f = next(c.decode(video=0))
        y = f.to_ndarray(format="gray")      # for a limited-range yuv420p source this is the Y plane
    w = y.shape[1]
    return [float(y[:, i * w // 3:(i + 1) * w // 3].mean()) for i in range(3)]


# ---- synthetic sources -----------------------------------------------------------------------------
GEQ = "geq=lum='if(lt(X,W/3),200,if(lt(X,2*W/3),400,700))':cb=512:cr=512"


@pytest.fixture(scope="module")
def src(tmp_path_factory):
    d = tmp_path_factory.mktemp("src")
    s = {}
    tags = ["-metadata", "creation_time=2026-10-30T12:00:00Z", "-metadata", "location=+51.5000-000.1000/",
            "-metadata", "com.apple.quicktime.model=iPhone 99"]
    # SDR H.264, 1080p30, with stereo audio and identifying metadata
    s["sdr"] = d / "sdr.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=1", "-f", "lavfi", "-i", "sine=f=440:r=44100:d=1",
       "-ac", "2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-colorspace", "bt709",
       "-color_primaries", "bt709", "-color_trc", "bt709", "-c:a", "aac", *tags, str(s["sdr"]))
    # no audio at all
    s["mute"] = d / "mute.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=1", "-c:v", "libx264", "-preset", "ultrafast",
       "-pix_fmt", "yuv420p", str(s["mute"]))
    # HEVC 10-bit PQ and HLG, three luma bands
    for name, trc in (("pq", "smpte2084"), ("hlg", "arib-std-b67")):
        s[name] = d / f"{name}.mov"
        ff("-f", "lavfi", "-i", "color=c=gray:s=1920x1080:r=30:d=1,format=yuv420p10le," + GEQ,
           "-f", "lavfi", "-i", "sine=f=220:r=48000:d=1", "-c:v", "libx265", "-preset", "ultrafast",
           "-pix_fmt", "yuv420p10le", "-color_primaries", "bt2020", "-color_trc", trc, "-colorspace", "bt2020nc",
           "-color_range", "tv",
           "-x265-params", f"log-level=error:colorprim=bt2020:transfer={trc}:colormatrix=bt2020nc",
           "-tag:v", "hvc1", "-c:a", "aac", "-shortest", str(s[name]))
    # variable frame rate: keep frames 0-6 of every 10 (timestamps keep the gaps)
    s["vfr"] = d / "vfr.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=2", "-vf", "select='lt(mod(n,10),7)'", "-fps_mode", "vfr",
       "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(s["vfr"]))
    # 60 fps
    s["fast"] = d / "fast.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=60:d=1", "-c:v", "libx264", "-preset", "ultrafast",
       "-pix_fmt", "yuv420p", str(s["fast"]))
    # 31 s (tiny, 2 fps)
    s["long"] = d / "long.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x180:r=2:d=31", "-c:v", "libx264", "-preset", "ultrafast",
       "-pix_fmt", "yuv420p", str(s["long"]))
    # audio that starts 0.25 s after the video
    s["late"] = d / "late.mov"
    ff("-i", str(s["sdr"]), "-itsoffset", "0.25", "-f", "lavfi", "-i", "sine=f=440:r=48000:d=1", "-map", "0:v",
       "-map", "1:a", "-c:v", "copy", "-c:a", "aac", str(s["late"]))
    # 16:9 but smaller than the analysis grid
    s["small"] = d / "small.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=1", "-c:v", "libx264", "-preset", "ultrafast",
       "-pix_fmt", "yuv420p", str(s["small"]))
    # 4:3 (not the registered 16:9 grid)
    s["square"] = d / "square.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=1440x1080:r=30:d=1", "-c:v", "libx264", "-preset", "ultrafast",
       "-pix_fmt", "yuv420p", str(s["square"]))
    return s


@pytest.fixture(scope="module")
def tree(tmp_path_factory, src):
    """A working tree with raw/ holding every source, so each can be ingested by name."""
    root = tmp_path_factory.mktemp("repo")
    (root / "raw").mkdir()
    for k, p in src.items():
        (root / "raw" / p.name).write_bytes(p.read_bytes())
    return root


def run(tree, name, take="t01", attempt="a", out="takes", ingest_json="capture/ingest.json"):
    return ingest.ingest(tree / "raw" / f"{name}.mov", take, attempt, root=tree, out_dir=tree / out,
                         ingest_path=tree / ingest_json)


@pytest.fixture(scope="module")
def sdr(tree):
    return run(tree, "sdr")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ---- the ordinary case ---------------------------------------------------------------------------------
def test_sdr_outputs_and_hashes(tree, sdr):
    original = tree / "raw/sdr.mov"
    assert sdr["take_id"] == "t01a"
    assert sdr["original"]["sha256"] == sha(original)
    for kind in ("render", "analysis", "wav"):
        o = sdr["outputs"][kind]
        assert (tree / o["path"]).is_file() and o["sha256"] == sha(tree / o["path"])
        assert not Path(o["path"]).is_absolute() and o["path"].startswith("takes/")
    assert sdr["hdr_detected"] is False and sdr["vfr_detected"] is False
    assert sdr["has_audio"] is True
    assert sdr["ffmpeg"].startswith("ffmpeg version")
    assert sdr["duration_s"] == pytest.approx(1.0, abs=0.1)
    assert sdr["size_render"] == [1920, 1080] and sdr["size_analysis"] == [1280, 720] and sdr["fps_render"] == 30


@pytest.mark.parametrize("kind,size", [("render", (1920, 1080)), ("analysis", (1280, 720))])
def test_video_outputs_are_sdr_rec709_h264_cfr30(tree, sdr, kind, size):
    p = probe(tree / sdr["outputs"][kind]["path"])
    assert (p["codec_name"], p["pix_fmt"]) == ("h264", "yuv420p")
    assert (p["width"], p["height"]) == size
    assert (p["color_space"], p["color_primaries"], p["color_transfer"], p["color_range"]) == \
        ("bt709", "bt709", "bt709", "tv")
    assert Fraction(p["r_frame_rate"]) == 30 and Fraction(p["avg_frame_rate"]) == 30
    assert int(p["nb_frames"]) == 30
    assert pts_deltas(tree / sdr["outputs"][kind]["path"]) == pytest.approx(1 / 30, abs=1e-6)


def test_outputs_carry_no_audio_and_no_metadata(tree, sdr):
    for kind in ("render", "analysis"):
        path = tree / sdr["outputs"][kind]["path"]
        streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                                  str(path)], capture_output=True, text=True, check=True).stdout.split()
        assert streams == ["video"]
        tags = {k.lower(): v for k, v in format_tags(path).items()}
        assert not {k for k in tags if k in ("creation_time", "location", "encoder", "title") or "apple" in k
                    or "location" in k}, tags
        assert "iPhone" not in path.read_bytes().decode("latin-1")
        assert b"2026-10-30" not in path.read_bytes()


def test_wav_is_mono_48k_16bit_and_as_long_as_the_video(tree, sdr):
    with wave.open(str(tree / sdr["outputs"]["wav"]["path"])) as w:
        assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (1, 48000, 2)
        assert w.getnframes() / 48000 == pytest.approx(1.0, abs=0.05)
        data = np.frombuffer(w.readframes(w.getnframes()), np.int16)
    assert np.abs(data).max() > 1000                 # the tone came through


def test_a_source_with_no_audio_has_no_wav(tree):
    row = run(tree, "mute", take="t09", attempt="a")
    assert row["has_audio"] is False and row["outputs"]["wav"] is None
    assert not (tree / "takes/t09a.wav").exists()


def test_originals_are_never_touched(tree, sdr):
    before = sha(tree / "raw/sdr.mov")
    names = sorted(p.name for p in (tree / "raw").iterdir())
    run(tree, "sdr", take="t01", attempt="a")
    assert sha(tree / "raw/sdr.mov") == before and sorted(p.name for p in (tree / "raw").iterdir()) == names


# ---- HDR -> SDR ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name,trc", [("pq", "smpte2084"), ("hlg", "arib-std-b67")])
def test_hdr_tagged_clip_becomes_sdr_tagged(tree, src, name, trc):
    sp = probe(src[name])
    assert (sp["color_transfer"], sp["pix_fmt"]) == (trc, "yuv420p10le")      # the fixture really is HDR
    row = run(tree, name, take=f"t1{name[0]}", attempt="a")
    assert row["hdr_detected"] is True and trc in row["hdr_evidence"]
    for kind in ("render", "analysis"):
        p = probe(tree / row["outputs"][kind]["path"])
        assert (p["pix_fmt"], p["color_space"], p["color_primaries"], p["color_transfer"], p["color_range"]) == \
            ("yuv420p", "bt709", "bt709", "bt709", "tv")


def test_pq_is_tone_mapped_not_just_retagged(tree):
    row = run(tree, "pq", take="t10", attempt="a")
    lo, mid, hi = y_planes(tree / row["outputs"]["render"]["path"])
    # PQ codes 200 / 400 / 700 are ~1 / 25 / 1000 nits. A retag would leave the shadows near luma 50;
    # the PQ EOTF puts them near black, and the bright band near white.
    assert lo < 30 < mid < hi and hi > 200, (lo, mid, hi)


def test_hlg_is_tone_mapped_in_order(tree):
    row = run(tree, "hlg", take="t11", attempt="a")
    lo, mid, hi = y_planes(tree / row["outputs"]["render"]["path"])
    assert lo < mid < hi


def test_eotf_luts_are_deterministic_and_monotone():
    for kind in ("pq", "hlg"):
        a, b = ingest.eotf_lut(kind, 1024), ingest.eotf_lut(kind, 1024)
        assert np.array_equal(a, b) and a.shape == (1024,)
        assert a[0] == 0 and np.all(np.diff(a) >= 0)
    assert ingest.eotf_lut("pq", 4096)[-1] == pytest.approx(100.0)       # 10,000 nits in 100-nit units
    assert ingest.eotf_lut("hlg", 4096)[-1] == pytest.approx(10.0)       # a 1,000 nit display


def test_hdr_detection_reads_transfer_primaries_and_dolby_vision():
    s = {"color_transfer": "smpte2084"}
    assert ingest.detect_hdr(s)[0] and ingest.detect_hdr({"color_transfer": "arib-std-b67"})[0]
    dv = {"color_transfer": "bt709", "side_data_list": [{"side_data_type": "DOVI configuration record"}]}
    hit, why = ingest.detect_hdr(dv)
    assert hit and "dolby" in why.lower()
    assert ingest.detect_hdr({"color_transfer": "bt709", "color_primaries": "bt709"}) == (False, "")
    assert ingest.detect_hdr({}) == (False, "")


# ---- frame rate ----------------------------------------------------------------------------------------------
def test_vfr_becomes_cfr(tree, src):
    d = pts_deltas(src["vfr"])
    assert d.max() > 2 * np.median(d)                                    # the fixture really is irregular
    row = run(tree, "vfr", take="t12", attempt="a")
    assert row["vfr_detected"] is True
    for kind in ("render", "analysis"):
        path = tree / row["outputs"][kind]["path"]
        assert pts_deltas(path) == pytest.approx(1 / 30, abs=1e-6)
        p = probe(path)
        assert Fraction(p["r_frame_rate"]) == 30 and Fraction(p["avg_frame_rate"]) == 30
    assert float(probe(tree / row["outputs"]["render"]["path"])["duration"]) == pytest.approx(row["duration_s"], abs=0.1)


def test_a_constant_rate_source_is_not_vfr(tree, sdr):
    assert sdr["vfr_detected"] is False


def test_sixty_fps_is_capped_at_thirty(tree):
    row = run(tree, "fast", take="t13", attempt="a")
    assert row["fps_source"] == 60 and row["fps_render"] == 30
    p = probe(tree / row["outputs"]["render"]["path"])
    assert Fraction(p["avg_frame_rate"]) == 30 and int(p["nb_frames"]) == 30


# ---- stability and refusals -----------------------------------------------------------------------------------
def test_hashes_are_stable_run_to_run(tree, sdr):
    again = run(tree, "sdr", take="t01", attempt="a", out="takes_again", ingest_json="capture/ingest_again.json")
    for kind in ("render", "analysis", "wav"):
        assert again["outputs"][kind]["sha256"] == sdr["outputs"][kind]["sha256"], kind
    assert again["original"] == sdr["original"]


def test_hdr_hashes_are_stable_too(tree):
    a = run(tree, "pq", take="t10", attempt="a")
    b = run(tree, "pq", take="t10", attempt="a", out="takes_again", ingest_json="capture/ingest_again.json")
    assert a["outputs"]["render"]["sha256"] == b["outputs"]["render"]["sha256"]


def test_refuses_a_take_longer_than_30_seconds(tree):
    with pytest.raises(ingest.IngestError, match="30"):
        run(tree, "long", take="t20", attempt="a")
    assert not list((tree / "takes").glob("t20a*"))                      # nothing half-written


def test_the_duration_limit_is_30_seconds_inclusive():
    ingest.check_duration(30.0)
    ingest.check_duration(1.0)
    with pytest.raises(ingest.IngestError, match="30"):
        ingest.check_duration(30.01)
    with pytest.raises(ingest.IngestError):
        ingest.check_duration(0.0)


def test_refuses_a_source_that_is_not_16_by_9(tree):
    with pytest.raises(ingest.IngestError, match="16:9"):
        run(tree, "square", take="t22", attempt="a")


def test_refuses_a_source_below_the_analysis_grid(tree):
    with pytest.raises(ingest.IngestError, match="1280x720"):
        run(tree, "small", take="t25", attempt="a")


def test_audio_that_starts_late_is_padded_so_t0_is_the_first_frame(tree):
    row = run(tree, "late", take="t26", attempt="a")
    with wave.open(str(tree / row["outputs"]["wav"]["path"])) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float)
    head, body = x[: int(0.2 * 48000)], x[int(0.35 * 48000): int(0.9 * 48000)]
    assert np.abs(head).max() < 50 and np.abs(body).max() > 1000, (np.abs(head).max(), np.abs(body).max())
    assert len(x) / 48000 == pytest.approx(1.0, abs=0.05)


def test_audio_filter_pads_trims_or_leaves_alone():
    assert ingest.audio_filter(0.0) == "asetpts=PTS-STARTPTS,aresample=48000"
    assert "adelay=delays=250.000:all=1" in ingest.audio_filter(0.25)
    assert "atrim=start=0.100000" in ingest.audio_filter(-0.1)


def test_refuses_an_original_outside_raw(tree, tmp_path, src):
    stray = tmp_path / "stray.mov"
    stray.write_bytes(src["sdr"].read_bytes())
    with pytest.raises(ingest.IngestError, match="raw"):
        ingest.ingest(stray, "t23", "a", root=tree, out_dir=tree / "takes", ingest_path=tree / "capture/x.json")


def test_refuses_a_missing_original_and_a_non_video(tree):
    with pytest.raises(ingest.IngestError):
        ingest.ingest(tree / "raw/none.mov", "t24", "a", root=tree, out_dir=tree / "takes",
                      ingest_path=tree / "capture/x.json")
    (tree / "raw/notvideo.mov").write_bytes(b"not a video")
    with pytest.raises(ingest.IngestError):
        ingest.ingest(tree / "raw/notvideo.mov", "t24", "a", root=tree, out_dir=tree / "takes",
                      ingest_path=tree / "capture/x.json")


def test_take_and_attempt_names_are_checked(tree):
    with pytest.raises(ingest.IngestError):
        run(tree, "sdr", take="../evil", attempt="a")
    with pytest.raises(ingest.IngestError):
        run(tree, "sdr", take="t01", attempt="AB")


# ---- capture/ingest.json --------------------------------------------------------------------------------------
def test_ingest_json_is_sorted_upserted_and_free_of_absolute_paths(tree, sdr):
    run(tree, "sdr", take="t01", attempt="b")                            # a second attempt of the same take
    run(tree, "sdr", take="t01", attempt="a")                            # re-ingest replaces, not duplicates
    doc = json.loads((tree / "capture/ingest.json").read_text())
    assert doc["schema"] == "p47-ingest/1"
    ids = [r["take_id"] for r in doc["rows"]]
    assert ids == sorted(ids) and len(ids) == len(set(ids)) and {"t01a", "t01b"} <= set(ids)
    text = (tree / "capture/ingest.json").read_text()
    assert str(tree) not in text and "/Users/" not in text and "creation_time" not in text
    row = next(r for r in doc["rows"] if r["take_id"] == "t01a")
    assert row["original"]["path"] == "raw/sdr.mov"
    for k in ("take_id", "take", "attempt", "original", "outputs", "duration_s", "fps_source", "fps_render",
              "size_source", "size_render", "size_analysis", "hdr_detected", "hdr_evidence", "vfr_detected",
              "has_audio", "ffmpeg"):
        assert k in row, k


def test_rows_do_not_depend_on_the_time_of_the_run(tree, sdr):
    again = run(tree, "sdr", take="t01", attempt="a", out="takes_again", ingest_json="capture/ingest_again.json")
    strip = lambda r: {k: v for k, v in r.items() if k != "outputs"}  # noqa: E731
    assert strip(again) == strip(sdr)


def test_main_runs_the_cli(tree, capsys):
    rc = ingest.main([str(tree / "raw/sdr.mov"), "--take", "t30", "--attempt", "a", "--root", str(tree),
                      "--out", str(tree / "takes"), "--ingest", str(tree / "capture/ingest.json")])
    assert rc == 0
    assert "t30a" in capsys.readouterr().out
    rc = ingest.main([str(tree / "raw/long.mov"), "--take", "t31", "--attempt", "a", "--root", str(tree),
                      "--out", str(tree / "takes"), "--ingest", str(tree / "capture/ingest.json")])
    assert rc == 1


def test_takes_is_gitignored():
    lines = (REPO / ".gitignore").read_text().split()
    assert "takes/" in lines and "raw/" in lines


# ---- review fixes: validate first, temp dir beside the outputs, raw/ is read-only, errors wrapped -----------------
def test_a_bad_ingest_json_is_refused_before_anything_is_encoded(tree):
    bad = tree / "capture/bad.json"
    bad.parent.mkdir(exist_ok=True)
    for text in ("{not json", json.dumps({"schema": "p47-ingest/9", "rows": []}), json.dumps({"schema": ingest.SCHEMA})):
        bad.write_text(text)
        with pytest.raises(ingest.IngestError, match="ingest"):
            ingest.ingest(tree / "raw/sdr.mov", "t40", "a", root=tree, out_dir=tree / "takes_bad", ingest_path=bad)
        assert not (tree / "takes_bad").exists() or not list((tree / "takes_bad").iterdir())
        assert bad.read_text() == text


def test_outputs_and_the_record_may_not_live_in_raw(tree):
    with pytest.raises(ingest.IngestError, match="raw"):
        ingest.ingest(tree / "raw/sdr.mov", "t41", "a", root=tree, out_dir=tree / "raw/out", ingest_path=tree / "capture/x.json")
    with pytest.raises(ingest.IngestError, match="raw"):
        ingest.ingest(tree / "raw/sdr.mov", "t41", "a", root=tree, out_dir=tree / "takes", ingest_path=tree / "raw/ingest.json")
    assert not (tree / "raw/out").exists() and not (tree / "raw/ingest.json").exists()


def test_the_work_directory_is_inside_out_dir_and_is_gone_afterwards(tree, monkeypatch):
    seen = []
    real = ingest.encode_video

    def spy(src, dst, *a, **k):
        seen.append(Path(dst).parent)
        return real(src, dst, *a, **k)
    monkeypatch.setattr(ingest, "encode_video", spy)
    out = tree / "takes_spy"
    ingest.ingest(tree / "raw/sdr.mov", "t42", "a", root=tree, out_dir=out, ingest_path=tree / "capture/spy.json")
    assert seen and all(p.parent == out and p.name.startswith(".ingest-") for p in seen)
    assert sorted(p.name for p in out.iterdir()) == ["t42a.analysis.mp4", "t42a.render.mp4", "t42a.wav"]


def test_a_failed_encode_leaves_no_work_directory_and_no_row(tree, monkeypatch):
    def boom(*a, **k):
        raise ingest.IngestError("ffmpeg failed")
    monkeypatch.setattr(ingest, "encode_video", boom)
    out = tree / "takes_fail"
    with pytest.raises(ingest.IngestError):
        ingest.ingest(tree / "raw/sdr.mov", "t43", "a", root=tree, out_dir=out, ingest_path=tree / "capture/fail.json")
    assert not list(out.iterdir()) and not (tree / "capture/fail.json").exists()


def test_tool_failures_become_ingest_errors(tree, monkeypatch):
    import subprocess as sp
    args = (tree / "raw/sdr.mov", "t44", "a")
    kw = dict(root=tree, out_dir=tree / "takes_err", ingest_path=tree / "capture/err.json")
    with monkeypatch.context() as m:                                    # ffprobe / ffmpeg not installed
        m.setenv("PATH", "")
        with pytest.raises(ingest.IngestError, match="ffprobe|ffmpeg"):
            ingest.ingest(*args, **kw)
    with monkeypatch.context() as m:                                    # a tool exits non-zero under check=True
        m.setattr(ingest, "packet_times", lambda p: (_ for _ in ()).throw(sp.CalledProcessError(1, "ffprobe")))
        with pytest.raises(ingest.IngestError, match="ffprobe"):
            ingest.ingest(*args, **kw)
    with monkeypatch.context() as m:                                    # ffprobe prints something that is not JSON
        m.setattr(ingest, "ffprobe", lambda p: json.loads("not json"))
        with pytest.raises(ingest.IngestError, match="JSON|ffprobe"):
            ingest.ingest(*args, **kw)
    assert not (tree / "capture/err.json").exists()
