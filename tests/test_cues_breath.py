"""seam.cues.breath: an audio burst (30 dB over the room for 0.5 s, edges ignored) on the take's WAV, plus page flow."""
import numpy as np
import pytest
from scipy.io import wavfile

from seam.cues import breath

SR = 48000


def _db(x):
    return 10 ** (x / 20)


def _wind(rng, n, level_db):
    """Noise low-passed at 1 kHz, as a blow through the straw reaches the iPhone's mic (call 124)."""
    from scipy.signal import butter, lfilter
    y = lfilter(*butter(4, 1000, fs=SR), rng.normal(0, 1, n))
    return y / np.sqrt(np.mean(y ** 2)) * _db(level_db)


def _wav(tmp_path, burst=None, seconds=6.0, stereo=False, seed=0, name="take.wav", level_db=-20.0):
    """A room at about -60 dBFS; burst = (start s, duration s, kind) at level_db (RMS)."""
    rng = np.random.default_rng(seed)
    y = rng.normal(0, _db(-60), int(SR * seconds))
    if burst is not None:
        start, dur, kind = burst
        a, b = int(start * SR), int((start + dur) * SR)
        if kind == "noise":
            y[a:b] += rng.normal(0, _db(level_db), b - a)
        elif kind == "wind":
            y[a:b] += _wind(rng, b - a, level_db)
        else:
            y[a:b] += _db(level_db) * np.sqrt(2) * np.sin(2 * np.pi * 440 * np.arange(b - a) / SR)
    data = (np.clip(y, -1, 1) * 32767).astype(np.int16)
    if stereo:
        data = np.stack([data, data], axis=1)
    p = tmp_path / name
    wavfile.write(p, SR, data)
    return p


def test_noise_burst_detected(tmp_path):
    (e,) = breath.detect(_wav(tmp_path, (3.0, 0.8, "noise")))
    assert e["cue"] == "breath" and e["source"] == "detector:breath"
    assert e["what"] == "someone breathes out across the page"
    assert abs(e["t"] - 3.0) <= 0.05 and abs(e["t_end"] - 3.8) <= 0.1
    ev = e["evidence"]
    assert ev["rms_db_peak"] > -30 and ev["rise_db_peak"] >= 30 and abs(ev["noise_floor_db"] + 60) < 1
    assert "flatness_mean" not in ev
    assert ev["flow_confirmed"] is None          # no frames given


def test_low_frequency_wind_detected(tmp_path):
    # the iPhone records almost nothing above 3 kHz: a real blow is low-frequency wind, not hiss (call 124)
    (e,) = breath.detect(_wav(tmp_path, (2.4, 2.0, "wind")))
    assert abs(e["t"] - 2.4) <= 0.05 and abs(e["t_end"] - 4.4) <= 0.1


def test_short_click_rejected(tmp_path):
    assert breath.detect(_wav(tmp_path, (3.0, 0.04, "noise"))) == []


def test_burst_under_half_a_second_rejected(tmp_path):
    assert breath.detect(_wav(tmp_path, (3.0, 0.4, "noise"))) == []
    assert len(breath.detect(_wav(tmp_path, (3.0, 0.6, "noise")))) == 1


def test_burst_under_30_db_over_the_room_rejected(tmp_path):
    assert breath.detect(_wav(tmp_path, (3.0, 1.0, "wind"), level_db=-35.0)) == []      # about 25 dB over
    assert len(breath.detect(_wav(tmp_path, (3.0, 1.0, "wind"), level_db=-25.0))) == 1  # about 35 dB over


def test_first_and_last_half_second_ignored(tmp_path):
    # the record button: loud for 0.45 s at either end, and nothing counts
    assert breath.detect(_wav(tmp_path, (0.0, 0.45, "noise"))) == []
    assert breath.detect(_wav(tmp_path, (5.55, 0.45, "noise"))) == []
    # a burst that starts inside the first 0.5 s is timed from where the take starts counting
    (e,) = breath.detect(_wav(tmp_path, (0.2, 1.2, "noise")))
    assert 0.5 <= e["t"] <= 0.55 and abs(e["t_end"] - 1.4) <= 0.1


def test_silence(tmp_path):
    assert breath.detect(_wav(tmp_path)) == []


def _page_frames(n=90, fps=15, move=None, seed=1):
    rng = np.random.default_rng(seed)
    tex = (rng.random((140, 220)) * 255).astype(np.uint8)
    tex = np.kron(tex, np.ones((2, 2), np.uint8))             # 280x440 texture, coarse enough for flow
    out = []
    for i in range(n):
        off = 0
        if move and move[0] <= i / fps < move[1]:
            off = 2 * (i - int(move[0] * fps))
        f = np.full((240, 400), 90, np.uint8)
        f[20:220, 40:360] = tex[20:220, 40 + off % 40:360 + off % 40]
        out.append(np.repeat(f[..., None], 3, axis=2))
    return np.stack(out)


def test_page_flow_confirms(tmp_path):
    wav = _wav(tmp_path, (3.0, 0.8, "noise"))
    box = (40, 20, 320, 200)
    (e,) = breath.detect(wav, frames=_page_frames(move=(3.0, 3.8)), fps=15, page_box=box)
    assert e["evidence"]["flow_confirmed"] is True and e["evidence"]["flow_peak"] > 0.5
    (e,) = breath.detect(wav, frames=_page_frames(), fps=15, page_box=box)
    assert e["evidence"]["flow_confirmed"] is False


def test_stereo_input(tmp_path):
    (e,) = breath.detect(_wav(tmp_path, (2.0, 0.6, "noise"), stereo=True))
    assert abs(e["t"] - 2.0) <= 0.05


def test_features_shapes(tmp_path):
    t, rms_db = breath.audio_features(*breath.read_wav(_wav(tmp_path)))
    assert t.shape == rms_db.shape and np.all(np.diff(t) > 0)


def test_thresholds_are_named_constants():
    import inspect
    b = breath
    assert (b.RISE_DB, b.MERGE_GAP_S, b.MIN_DUR_S, b.EDGE_S, b.ABS_FLOOR_DB, b.FLOW_MARGIN_S, b.FLOW_PX) == \
        (30.0, 0.1, 0.5, 0.5, -55.0, 0.2, 0.5)
    assert not hasattr(b, "MIN_FLATNESS") and not hasattr(b, "BAND")     # the flatness test went (call 126)
    p = inspect.signature(b.bursts).parameters
    assert p["abs_floor_db"].default == b.ABS_FLOOR_DB and p["rise_db"].default == b.RISE_DB
    assert p["min_dur"].default == b.MIN_DUR_S and p["edge_s"].default == b.EDGE_S
    assert inspect.signature(b.detect).parameters["flow_px"].default == b.FLOW_PX
