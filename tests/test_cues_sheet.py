"""seam.cues.sheet: the p47-cues/1 schema, assembly and determinism."""
import json

import pytest

from seam.cues import sheet

EVENT_KEYS = {"id", "t", "t_end", "cue", "what", "target", "source", "evidence"}


def _ev(t, cue="pen", src="detector:props", t_end=None, what="the pen is set down"):
    return sheet.make_event(t=t, t_end=t_end, cue=cue, what=what, source=src, evidence={"frame": int(t * 15)})


def _sheet(events, **kw):
    args = dict(take="t03", fps=15, n_frames=150, size=[1280, 720], events=events)
    args.update(kw)
    return sheet.assemble(**args)


def test_make_event_fields():
    e = sheet.make_event(t=1.234567, t_end=None, cue="pen", what="the pen is set down",
                         source="detector:props", evidence={"frame": 18})
    assert set(e) == EVENT_KEYS - {"id"}
    assert e["t"] == 1.235 and e["t_end"] is None and e["target"] is None


def test_assemble_sorts_and_numbers():
    s = _sheet([_ev(3.0), _ev(1.0, cue="hand", src="detector:hands", t_end=2.0, what="a hand comes into view"),
                _ev(2.0)])
    assert s["schema"] == "p47-cues/1"
    assert [e["id"] for e in s["events"]] == ["e01", "e02", "e03"]
    assert [e["t"] for e in s["events"]] == [1.0, 2.0, 3.0]
    assert all(set(e) == EVENT_KEYS for e in s["events"])
    assert s["vlm_log"] == []


def test_assemble_targets_only_the_take_cue():
    hand = _ev(0.5, cue="hand", src="detector:hands", t_end=1.5, what="a hand comes into view")
    water = _ev(2.0, cue="water", what="the glass is set down")
    s = _sheet([hand, water], fires="water", target="ink")
    by_cue = {e["cue"]: e for e in s["events"]}
    assert by_cue["water"]["target"] == "ink"
    assert by_cue["hand"]["target"] is None


def test_assemble_does_not_mutate_inputs():
    e = _ev(1.0)
    _sheet([e], fires="pen", target="ink")
    assert e["target"] is None and "id" not in e


@pytest.mark.parametrize("mutate", [
    lambda s: s["events"][0].update(cue="bell"),
    lambda s: s["events"][0].update(t_end=0.5),
    lambda s: s["events"][0].update(source="props"),
    lambda s: s["events"][0].update(source="detector:"),
    lambda s: s["events"][0].update(t=99.0),
    lambda s: s["events"][0].update(target="felt"),
    lambda s: s["events"][0].update(evidence="x"),
    lambda s: s.update(extra=1),
    lambda s: s.update(size=[1280]),
    lambda s: s["events"][0].update(id="e07"),
])
def test_validate_rejects(mutate):
    s = _sheet([_ev(1.0)])
    sheet.validate_sheet(s)
    mutate(s)
    with pytest.raises(ValueError):
        sheet.validate_sheet(s)


def test_write_is_deterministic(tmp_path):
    s = _sheet([_ev(1.0), _ev(2.0, cue="hand", src="detector:hands", t_end=3.0)])
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    sheet.write_sheet(a, s)
    sheet.write_sheet(b, json.loads(json.dumps(s)))
    assert a.read_bytes() == b.read_bytes()
    txt = a.read_text()
    assert txt.endswith("\n") and txt.startswith('{\n  "events"')
    sheet.validate_sheet(json.loads(txt))


def test_hand_entered_event():
    s = _sheet([sheet.make_event(t=4.0, t_end=None, cue="hand", what="a spoken line, entered by hand",
                                 source="hand", evidence={"note": "entered by hand"})])
    assert s["events"][0]["source"] == "hand"


# --- Task 9: the take orchestrator ----------------------------------------------
import subprocess
import sys

import av
import numpy as np
from scipy.io import wavfile

from seam import masks as masks_mod

FPS, N, HH, WW = 15, 60, 120, 160


def _pen_masks():
    m = np.zeros((N, HH, WW), bool)
    for i in range(N):
        if 10 <= i < 20:                          # slides in from the right
            x = 140 - 6 * (i - 10)
            m[i, 50:60, x:min(WW, x + 15)] = True
        elif i >= 20:
            m[i, 50:60, 80:95] = True
    return m


def _quiet_wav(path, seconds=N / FPS):
    rng = np.random.default_rng(0)
    wavfile.write(path, 48000, (rng.normal(0, 3e-4, int(48000 * seconds)) * 32767).astype(np.int16))
    return path


def test_from_take_synthetic(tmp_path):
    frames = np.full((N, HH, WW, 3), 200, np.uint8)
    pres = [0] * 8 + [1] * 15 + [0] * 37        # the hand that sets the pen down
    s = sheet.from_take(take="t03", frames=frames, fps=FPS, fires="pen", target="ink",
                        masks={"pen": _pen_masks()}, objects={"pen": "pen"},
                        wav=_quiet_wav(tmp_path / "t03.wav"), hands_presence=pres,
                        detectors=("hands", "props", "breath"))
    assert (s["take"], s["fps"], s["n_frames"], s["size"]) == ("t03", 15, N, [WW, HH])
    cues = [(e["cue"], e["target"], e["source"]) for e in s["events"]]
    assert cues == [("hand", None, "detector:hands"), ("pen", "ink", "detector:props")]


def test_from_take_rejects_mismatched_masks():
    frames = np.full((N, HH, WW, 3), 200, np.uint8)
    with pytest.raises(ValueError):
        sheet.from_take(take="t03", frames=frames, fps=FPS, fires="pen", target="ink",
                        masks={"pen": np.zeros((N - 1, HH, WW), bool)}, objects={"pen": "pen"},
                        hands_presence=[0] * N, detectors=("props",))


def test_default_detectors():
    assert sheet.DEFAULT_DETECTORS["light"] == ("hands", "torch")
    assert sheet.DEFAULT_DETECTORS["note"] == ("hands", "note")     # OCR only: no double note event
    assert set(sheet.DEFAULT_DETECTORS) == set(sheet.CUES)


def _write_video(path, frames, fps=FPS):
    with av.open(str(path), "w") as c:
        st = c.add_stream("libx264", rate=fps)
        st.width, st.height, st.pix_fmt = frames.shape[2], frames.shape[1], "yuv420p"
        for f in frames:
            for pkt in st.encode(av.VideoFrame.from_ndarray(f, format="rgb24")):
                c.mux(pkt)
        for pkt in st.encode():
            c.mux(pkt)


def test_cli_writes_sheet(tmp_path):
    frames = np.full((N, HH, WW, 3), 200, np.uint8)
    vid = tmp_path / "t03.mp4"
    _write_video(vid, frames)
    mpath = tmp_path / "t03.npz"
    masks_mod.save_masks(mpath, {"pen": _pen_masks()}, take="t03", fps=FPS)
    out = tmp_path / "cues" / "t03.json"
    r = subprocess.run([sys.executable, "-m", "seam.cues.sheet", "--take", "t03", "--video", str(vid),
                        "--fires", "pen", "--target", "ink", "--masks", str(mpath), "--object", "pen=pen",
                        "--detectors", "props", "--out", str(out)],
                       capture_output=True, text=True, cwd=sheet.ROOT)
    assert r.returncode == 0, r.stderr
    s = sheet.load_sheet(out)
    assert [e["cue"] for e in s["events"]] == ["pen"] and s["events"][0]["target"] == "ink"


def test_validate_rejects_nan_in_evidence():
    e = _ev(1.0)
    e["evidence"] = {"area_px": float("nan")}
    with pytest.raises(ValueError, match="evidence"):
        _sheet([e])


# --- call 132: the torch needs the page track; the note is read in its track's box ------------------------

def test_torch_needs_the_page_track():
    frames = np.full((N, HH, WW, 3), 200, np.uint8)
    with pytest.raises(ValueError, match="page"):
        sheet.from_take(take="t02", frames=frames, fps=FPS, fires="light", target="ink",
                        hands_presence=[0] * N, detectors=("torch",))


def test_torch_reads_light_on_the_page_only():
    frames = np.full((N, HH, WW, 3), 90, np.uint8)
    frames[:, 20:100, 40:140] = 205                        # the page
    frames[20:, 30:60, 0:30] = 255                         # a lit patch on the desk, off the page
    page = np.zeros((N, HH, WW), bool)
    page[:, 20:100, 40:140] = True
    s = sheet.from_take(take="t02", frames=frames, fps=FPS, fires="light", target="ink",
                        masks={"page": page}, hands_presence=[0] * N, detectors=("torch",))
    assert s["events"] == []


def test_note_needs_its_track_or_a_box():
    frames = np.full((N, HH, WW, 3), 255, np.uint8)
    with pytest.raises(ValueError, match="note"):
        sheet.from_take(take="t05", frames=frames, fps=FPS, fires="note", target="ink",
                        hands_presence=[0] * N, detectors=("note",))


def test_note_box_comes_from_the_note_track(monkeypatch):
    frames = np.full((N, HH, WW, 3), 255, np.uint8)
    track = np.zeros((N, HH, WW), bool)
    track[30:, 40:60, 70:110] = True
    seen = {}
    from seam.cues import note as note_mod

    def fake_detect(fr, fps, *, box=None, **kw):          # OCR itself is tested in test_cues_note
        seen["box"] = box
        return []
    monkeypatch.setattr(note_mod, "detect", fake_detect)
    sheet.from_take(take="t05", frames=frames, fps=FPS, fires="note", target="ink",
                    masks={"note": track}, hands_presence=[0] * N, detectors=("note",))
    assert seen["box"] == note_mod.box_from_track(track)
