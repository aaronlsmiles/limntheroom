"""seam.compile: cue sheet x laws -> p47-render/1 request + clause trace. Fixture laws only."""
import json
from pathlib import Path

import pytest

from seam import compile as C
from seam import laws as L
from seam.cues import sheet as S

FIX = Path(__file__).parent / "fixtures" / "laws_fixture.json"
PAGE = {"ink": "left", "gold": "centre", "paper": "right"}
TAKE_GLASS_INK = {"id": "t01", "cue": "glass", "target_material": "ink", "target_position": "left",
                  "touched_object": "glass", "handheld": False, "rated": True}
TAKE_GLASS_GOLD = dict(TAKE_GLASS_INK, target_material="gold", target_position="centre")
TAKE_PEN = {"id": "t03", "cue": "pen", "target_material": "ink", "target_position": "left",
            "touched_object": "pen", "handheld": False, "rated": True}


def _laws():
    return L.load_laws(FIX)


def _ev(t, cue, what, src="detector:props", t_end=None):
    return S.make_event(t=t, t_end=t_end, cue=cue, what=what, source=src, evidence={})


def _sheet(take="t01", fires="water", target="ink", events=None):
    events = events if events is not None else [
        _ev(0.6, "hand", "a hand comes into view", "detector:hands", 2.0),
        _ev(2.4, "water", "the glass is set down"),
    ]
    return S.assemble(take=take, fps=15, n_frames=165, size=[1280, 720], events=events, fires=fires, target=target)


def _compile(sheet=None, take=TAKE_GLASS_INK, model="aleph2", **kw):
    return C.compile_request(sheet or _sheet(), _laws(), take, model=model, video="take.mp4", page=PAGE, **kw)


def test_basic_prompt_and_request_shape():
    req, trace = _compile()
    assert req["schema"] == "p47-render/1" and req["model"] == "aleph2"
    assert req["inputs"]["video"] == "take.mp4"
    assert req["prompt"].startswith(C.PREAMBLE)
    assert "At 2.40 s, when the glass is set down, it juggles three ink dots (fixture)." in req["prompt"]
    assert trace["schema"] == "p47-trace/1" and trace["take"] == "t01"


def test_aleph2_over_1000_is_hard_failure():
    long_what = "the glass is set down " + "very " * 200
    with pytest.raises(C.CompileError, match="1000"):
        _compile(_sheet(events=[_ev(2.0, "water", long_what.strip())]))


def test_each_event_fires_one_clause_in_time_order():
    events = [_ev(5.0, "water", "the glass is set down again"),
              _ev(1.0, "water", "the glass is set down"),
              _ev(3.0, "water", "the glass is nudged")]
    req, trace = _compile(_sheet(events=events))
    fired = [c for c in trace["clauses"] if c["law"]]
    assert [c["t"] for c in fired] == [1.0, 3.0, 5.0]
    assert all(c["law"] == "ink.water" for c in fired)
    pos = [req["prompt"].index(c["clause"]) for c in fired]
    assert pos == sorted(pos)
    for c in fired:
        assert req["prompt"].count(c["clause"]) == 1
    assert len(fired) == sum(1 for e in _sheet(events=events)["events"] if e["target"])


def test_context_events_fire_nothing():
    req, trace = _compile()
    ctx = [c for c in trace["clauses"] if c["cue"] == "hand"]
    assert ctx == [{"event": "e01", "t": 0.6, "t_clip": 0.6, "cue": "hand", "law": None, "clause": None}]
    assert "a hand comes into view" not in req["prompt"]
    assert req["prompt"].count("At ") == 1


def test_style_lock_per_material():
    req, _ = _compile()
    looks = _laws()["materials"]
    for m in ("ink", "gold", "paper"):
        line = f"The {m} drawing stays {looks[m]['look']}."
        assert req["prompt"].count(line) == 1, m
    # in page order: left, centre, right
    idx = [req["prompt"].index(f"The {m} drawing stays ") for m in ("ink", "gold", "paper")]
    assert idx == sorted(idx)


def test_target_named_by_position():
    req, _ = _compile()
    assert "The drawing on the left of the page, the ink one, comes to life" in req["prompt"]
    assert "The gold drawing in the centre of the page stays still on the page." in req["prompt"]
    assert "The paper drawing on the right of the page stays still on the page." in req["prompt"]
    req2, _ = _compile(_sheet(target="gold"), take=TAKE_GLASS_GOLD)
    assert "The drawing in the centre of the page, the gold one, comes to life" in req2["prompt"]
    assert "The ink drawing on the left of the page stays still on the page." in req2["prompt"]


def test_the_target_steps_up_out_of_its_place_call_110():
    """Call 110: the props sit on the page, so the creature steps up out of its place on the page, not off it."""
    req, _ = _compile()
    assert ("The drawing on the left of the page, the ink one, comes to life and steps up out of its place "
            "on the page.") in req["prompt"]
    assert "off the page" not in req["prompt"] and "onto the desk" not in req["prompt"]


def test_unknown_law_is_error():
    # the fixture has no gold.pen law
    sh = _sheet(take="t03", fires="pen", target="gold", events=[_ev(2.0, "pen", "the pen is set down")])
    take = dict(TAKE_PEN, target_material="gold", target_position="centre")
    with pytest.raises(L.UnknownLaw, match="gold.pen"):
        _compile(sh, take=take)


def test_target_mismatch_is_error():
    with pytest.raises(C.CompileError):
        _compile(_sheet(target="gold"), take=TAKE_GLASS_INK)


def test_take_mismatch_and_no_cue_are_errors():
    with pytest.raises(C.CompileError):
        _compile(_sheet(take="t09"))
    with pytest.raises(C.CompileError, match="no event"):
        _compile(_sheet(events=[_ev(0.5, "hand", "a hand comes into view", "detector:hands")]))


def test_noop_is_fixed_template():
    assert C.NOOP_PROMPT == "Change nothing. Keep every object, hand and line exactly as filmed."
    req, trace = C.compile_noop(TAKE_GLASS_INK, model="aleph2", video="take.mp4")
    assert req["prompt"] == C.NOOP_PROMPT
    assert req["meta"]["purpose"] == "noop"
    assert trace["clauses"] == []
    assert req["inputs"]["references"] == []


def test_byte_identical(tmp_path):
    outs = []
    for run in ("a", "b"):
        req, trace = _compile()
        p = tmp_path / run / "t01-ink-aleph2.json"
        C.write_outputs(p, req, trace)
        outs.append((p.read_bytes(), p.with_name("t01-ink-aleph2.trace.json").read_bytes()))
    assert outs[0] == outs[1]
    assert outs[0][0].endswith(b"\n")


def test_take_cue_mapping():
    assert C.TAKE_CUE == {"glass": "water", "torch": "light", "pen": "pen", "breath": "breath",
                          "note": "note", "hand": "hand"}
    sh = _sheet(take="t03", fires="pen", events=[_ev(2.0, "pen", "the pen is set down")])
    req, trace = _compile(sh, take=TAKE_PEN)
    assert [c["law"] for c in trace["clauses"]] == ["ink.pen"]


def test_meta_records_inputs():
    req, trace = _compile()
    m = req["meta"]
    assert m["take"] == "t01" and m["material"] == "ink" and m["compiler"] == "p47-compile/1"
    assert m["laws_sha256"] == L.canonical_sha256(_laws())
    assert m["cues_sha256"] == L.canonical_sha256(_sheet())
    assert m["fires"] == ["ink.water"]


# --- Task 12: adapters, the hub client's offline estimate, sealing, CLI -----------
import os
import subprocess
import sys

import av
import numpy as np
from PIL import Image

HUB_CLIENT = C.ROOT.parent.parent / "tools" / "runway" / "runway_gen.py"


@pytest.mark.parametrize("model,seed,options,refs", [
    ("aleph2", 1, {}, 0),
    ("kling_4", None, {"ratio": "auto_720p"}, 1),
    ("seedance2_5", 1, {"mode": "edit", "audio": False}, 1),
    ("gemini_omni_flash_1.1", None, {"mode": "edit", "ratio": "640:360"}, 1),
])
def test_adapter_shapes(model, seed, options, refs):
    req, _ = _compile(model=model, reference="crop.png")
    assert req.get("seed") == seed
    assert req["options"] == options
    assert len(req["inputs"]["references"]) == refs
    assert (C.REFERENCE_SENTENCE in req["prompt"]) == bool(refs)
    assert req["meta"]["seed_policy"] == ("fixed" if seed is not None else "first output")
    assert set(req) <= {"schema", "model", "prompt", "seed", "inputs", "options", "meta"}


def test_unknown_model():
    with pytest.raises(C.CompileError):
        _compile(model="gen4_aleph")


def _synthetic_mp4(path, seconds=10, fps=30, w=1280, h=720):
    with av.open(str(path), "w") as c:
        st = c.add_stream("libx264", rate=fps)
        st.width, st.height, st.pix_fmt = w, h, "yuv420p"
        st.options = {"preset": "ultrafast"}
        f = av.VideoFrame.from_ndarray(np.full((h, w, 3), 200, np.uint8), format="rgb24")
        for _ in range(seconds * fps):
            for pkt in st.encode(f):
                c.mux(pkt)
        for pkt in st.encode():
            c.mux(pkt)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    _synthetic_mp4(d / "take.mp4")
    Image.new("RGB", (64, 64), "white").save(d / "crop.png")
    return d


def _estimate(path):
    env = {k: v for k, v in os.environ.items() if k != "RUNWAY_API_KEY"}
    return subprocess.run(["python3", str(HUB_CLIENT), "estimate", str(path)], capture_output=True, text=True,
                          env=env, timeout=60)


@pytest.mark.skipif(not HUB_CLIENT.exists(), reason="hub Runway client not present (public repo)")
@pytest.mark.parametrize("model", sorted(C.MODELS))
def test_requests_pass_hub_estimate(media, model):
    req, trace = _compile(model=model, reference="crop.png")
    p = media / f"t01-ink-{model}.json"
    C.write_outputs(p, req, trace)
    r = _estimate(p)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["model"] == model and out["estimate_credits"] > 0
    assert out["warnings"] == []
    assert "warning" not in r.stderr


@pytest.mark.skipif(not HUB_CLIENT.exists(), reason="hub Runway client not present (public repo)")
def test_noop_passes_hub_estimate(media):
    req, trace = C.compile_noop(TAKE_GLASS_INK, model="aleph2", video="take.mp4")
    p = media / "t01-noop-aleph2.json"
    C.write_outputs(p, req, trace)
    r = _estimate(p)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout.strip().splitlines()[-1])["estimate_credits"] == 280   # 10 s x 28


def test_sealed_guard(tmp_path, monkeypatch):
    sealed = tmp_path / "repo" / "sealed"
    sealed.mkdir(parents=True)
    monkeypatch.setattr(C, "SEALED_DIR", sealed)
    lp = sealed / "laws.json"
    lp.write_text(FIX.read_text())
    req, trace = _compile()
    with pytest.raises(C.CompileError, match="sealed"):
        C.write_outputs(tmp_path / "repo" / "runs" / "requests" / "x.json", req, trace, laws_path=lp)
    p, t = C.write_outputs(sealed / "requests" / "x.json", req, trace, laws_path=lp)
    assert p.exists() and t.exists()
    # fixture laws outside sealed/ may be written anywhere
    C.write_outputs(tmp_path / "repo" / "runs" / "y.json", req, trace, laws_path=FIX)


def test_sealed_guard_anchors_to_the_repo(tmp_path, monkeypatch):
    sealed = tmp_path / "repo" / "sealed"
    sealed.mkdir(parents=True)
    monkeypatch.setattr(C, "SEALED_DIR", sealed)
    lp = sealed / "laws.json"
    lp.write_text(FIX.read_text())
    req, trace = _compile()
    # some other folder that happens to be called "sealed" is not the repo's sealed/
    with pytest.raises(C.CompileError, match="sealed"):
        C.write_outputs(tmp_path / "elsewhere" / "sealed" / "x.json", req, trace, laws_path=lp)
    # a path that only passes through sealed/ by name, then leaves it
    with pytest.raises(C.CompileError, match="sealed"):
        C.write_outputs(sealed / ".." / "runs" / "x.json", req, trace, laws_path=lp)
    # laws in a folder merely named "sealed" elsewhere are not the sealed laws
    other = tmp_path / "elsewhere" / "sealed" / "laws.json"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text(FIX.read_text())
    C.write_outputs(tmp_path / "runs" / "z.json", req, trace, laws_path=other)
    assert C.SEALED_DIR == sealed
    assert C.in_sealed(sealed / "requests" / "a.json") and not C.in_sealed(tmp_path / "elsewhere" / "sealed")


def test_sealed_dir_default():
    monkey_free = C.ROOT / "sealed"
    assert C.SEALED_DIR == monkey_free


def test_cli(tmp_path, media):
    sh = tmp_path / "t01.json"
    S.write_sheet(sh, _sheet())
    takes = tmp_path / "takes.json"
    takes.write_text(json.dumps([TAKE_GLASS_INK, TAKE_GLASS_GOLD,
                                 {"id": "t07", "cue": "curtain call", "target_material": ["ink", "gold", "paper"],
                                  "target_position": ["left", "centre", "right"]}]))
    out = tmp_path / "req" / "t01-ink-aleph2.json"
    args = [sys.executable, "-m", "seam.compile", "--sheet", str(sh), "--laws", str(FIX), "--takes", str(takes),
            "--take", "t01", "--material", "ink", "--model", "aleph2", "--video", str(media / "take.mp4"),
            "--out", str(out)]
    r = subprocess.run(args, capture_output=True, text=True, cwd=C.ROOT)
    assert r.returncode == 0, r.stderr
    req = json.loads(out.read_text())
    assert req["inputs"]["video"] == os.path.relpath(media / "take.mp4", out.parent)
    assert C.trace_path(out).exists()
    noop = tmp_path / "req" / "t01-noop.json"
    r = subprocess.run([sys.executable, "-m", "seam.compile", "--noop", "--takes", str(takes), "--take", "t01",
                        "--material", "ink", "--model", "aleph2", "--video", str(media / "take.mp4"),
                        "--out", str(noop)], capture_output=True, text=True, cwd=C.ROOT)
    assert r.returncode == 0, r.stderr
    assert json.loads(noop.read_text())["prompt"] == C.NOOP_PROMPT


def test_page_from_takes():
    takes = [TAKE_GLASS_INK, {"id": "t07", "cue": "curtain call", "target_material": ["ink", "gold", "paper"],
                              "target_position": ["left", "centre", "right"]}]
    assert C.page_from_takes(takes) == PAGE


# --- fix: gemini's 10 s input limit (R0.5 trims the probe to 10 s) -----------------
def _ffprobe_seconds(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


@pytest.fixture(scope="module")
def take11(tmp_path_factory):
    d = tmp_path_factory.mktemp("take11")
    _synthetic_mp4(d / "take11.mp4", seconds=11)
    Image.new("RGB", (64, 64), "white").save(d / "crop.png")
    return d


def test_trim_for_model(take11, tmp_path):
    src = take11 / "take11.mp4"
    assert C.MODELS["gemini_omni_flash_1.1"]["max_input_s"] == 10
    out, trim = C.trim_for_model(src, "gemini_omni_flash_1.1", tmp_path)
    assert out != src and out.parent == tmp_path
    assert 9.9 <= _ffprobe_seconds(out) <= 10.05
    assert trim == {"start_s": 0, "seconds": 10, "source": "take11.mp4", "source_sha256": C.file_sha256(src)}
    same, none = C.trim_for_model(src, "aleph2", tmp_path)
    assert same == src and none is None
    # a take already within the limit is left alone
    short, none = C.trim_for_model(out, "gemini_omni_flash_1.1", tmp_path)
    assert short == out and none is None


def test_trim_is_reused_when_identical(take11, tmp_path):
    a, _ = C.trim_for_model(take11 / "take11.mp4", "gemini_omni_flash_1.1", tmp_path)
    m = a.stat().st_mtime_ns
    b, _ = C.trim_for_model(take11 / "take11.mp4", "gemini_omni_flash_1.1", tmp_path)
    assert a == b and b.stat().st_mtime_ns == m


@pytest.mark.skipif(not HUB_CLIENT.exists(), reason="hub Runway client not present (public repo)")
@pytest.mark.parametrize("model", sorted(C.MODELS))
def test_cli_11s_input_passes_hub_estimate(take11, tmp_path, model):
    sh = tmp_path / "t01.json"
    S.write_sheet(sh, _sheet())
    takes = tmp_path / "takes.json"
    takes.write_text(json.dumps([TAKE_GLASS_INK, {"id": "t07", "cue": "curtain call",
                                                  "target_material": ["ink", "gold", "paper"],
                                                  "target_position": ["left", "centre", "right"]}]))
    out = tmp_path / "req" / f"t01-ink-{model}.json"
    r = subprocess.run([sys.executable, "-m", "seam.compile", "--sheet", str(sh), "--laws", str(FIX),
                        "--takes", str(takes), "--take", "t01", "--material", "ink", "--model", model,
                        "--video", str(take11 / "take11.mp4"), "--reference", str(take11 / "crop.png"),
                        "--out", str(out)], capture_output=True, text=True, cwd=C.ROOT)
    assert r.returncode == 0, r.stderr
    req = json.loads(out.read_text())
    if model == "gemini_omni_flash_1.1":
        assert req["inputs"]["video"] != os.path.relpath(take11 / "take11.mp4", out.parent)
        assert req["meta"]["trim"]["seconds"] == 10
    else:
        assert "trim" not in req["meta"]
    e = _estimate(out)
    assert e.returncode == 0, e.stderr
    assert json.loads(e.stdout.strip().splitlines()[-1])["warnings"] == []


# --- quality-review fixes ----------------------------------------------------------
def test_time_has_two_decimals():
    sh = _sheet(events=[_ev(2.467, "water", "the glass is set down")])
    req, trace = _compile(sh)
    assert "At 2.47 s, when the glass is set down" in req["prompt"]


def test_request_does_not_mutate_meta():
    meta = {"take": "t01", "purpose": "noop"}
    C._request("aleph2", C.NOOP_PROMPT, "take.mp4", [], None, None, meta)
    assert meta == {"take": "t01", "purpose": "noop"}


def _cli(tmp_path, *extra, laws=FIX, sheet_obj=None, takes_obj=None):
    sh = tmp_path / "s.json"
    S.write_sheet(sh, sheet_obj or _sheet())
    tk = tmp_path / "takes.json"
    tk.write_text(json.dumps(takes_obj if takes_obj is not None else
                             [TAKE_GLASS_INK, {"id": "t07", "cue": "curtain call", "target_material": ["ink", "gold", "paper"],
                                               "target_position": ["left", "centre", "right"]}]))
    args = [sys.executable, "-m", "seam.compile", "--sheet", str(sh), "--laws", str(laws), "--takes", str(tk),
            "--model", "aleph2", "--out", str(tmp_path / "o.json"), *extra]
    return subprocess.run(args, capture_output=True, text=True, cwd=C.ROOT)


def test_cli_errors_are_clean(tmp_path, media):
    vid = str(media / "take.mp4")
    r = _cli(tmp_path, "--take", "t09", "--material", "ink", "--video", vid)          # no such take
    assert r.returncode == 2 and r.stderr.startswith("compile: ") and "Traceback" not in r.stderr
    sh = _sheet(take="t01", target="gold")
    takes = [TAKE_GLASS_GOLD, {"id": "t07", "cue": "curtain call", "target_material": ["ink", "gold", "paper"],
                               "target_position": ["left", "centre", "right"]}]
    bad_laws = tmp_path / "laws.json"
    d = json.loads(FIX.read_text())
    d["laws"] = [l for l in d["laws"] if l["id"] != "gold.water"]
    bad_laws.write_text(json.dumps(d))
    r = _cli(tmp_path, "--take", "t01", "--material", "gold", "--video", vid, laws=bad_laws, sheet_obj=sh,
             takes_obj=takes)                                                        # unknown law
    assert r.returncode == 2 and "gold.water" in r.stderr and "Traceback" not in r.stderr
    r = _cli(tmp_path, "--take", "t01", "--material", "ink", "--video", str(tmp_path / "missing.mp4"))
    assert r.returncode == 2 and r.stderr.startswith("compile: ") and "Traceback" not in r.stderr
    (tmp_path / "broken.json").write_text("{")
    r = subprocess.run([sys.executable, "-m", "seam.compile", "--noop", "--takes", str(tmp_path / "broken.json"),
                        "--take", "t01", "--model", "aleph2", "--video", vid, "--out", str(tmp_path / "n.json")],
                       capture_output=True, text=True, cwd=C.ROOT)
    assert r.returncode == 2 and r.stderr.startswith("compile: ") and "Traceback" not in r.stderr


def test_find_take():
    takes = [TAKE_GLASS_INK, TAKE_GLASS_GOLD]
    assert C.find_take(takes, "t01", "gold") is TAKE_GLASS_GOLD
    assert C.find_take(takes, "t01", None, any_material=True) is TAKE_GLASS_INK
    with pytest.raises(C.CompileError):
        C.find_take(takes, "t01", None)            # ambiguous without a material
    with pytest.raises(C.CompileError):
        C.find_take(takes, "t09", None, any_material=True)


def test_missing_ffprobe_is_clear(tmp_path, monkeypatch, media):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(C.CompileError, match="ffmpeg"):
        C.video_seconds(media / "take.mp4")


# --- seedance2_5 gets a 720p copy (its edit mode renders and bills at the input's tier) ----
def _ffprobe_size(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True, check=True)
    w, h = r.stdout.strip().split(",")
    return int(w), int(h)


@pytest.fixture(scope="module")
def take11_1080(tmp_path_factory):
    d = tmp_path_factory.mktemp("take11_1080")
    _synthetic_mp4(d / "take1080.mp4", seconds=11, w=1920, h=1080)
    _synthetic_mp4(d / "take720.mp4", seconds=11, w=1280, h=720)
    Image.new("RGB", (64, 64), "white").save(d / "crop.png")
    return d


def test_prepare_input_scales_seedance_to_720p(take11_1080, tmp_path):
    src = take11_1080 / "take1080.mp4"
    assert C.MODELS["seedance2_5"]["max_height"] == 720
    out, prep = C.prepare_input_for_model(src, "seedance2_5", tmp_path)
    assert out != src and _ffprobe_size(out) == (1280, 720)
    assert 10.95 <= _ffprobe_seconds(out) <= 11.05                     # never trimmed
    assert prep == {"scale": {"width": 1280, "height": 720, "source": "take1080.mp4",
                              "source_sha256": C.file_sha256(src)}}
    again, _ = C.prepare_input_for_model(src, "seedance2_5", tmp_path)
    assert again == out                                               # reused when identical
    # a 720p input is left alone
    same, none = C.prepare_input_for_model(take11_1080 / "take720.mp4", "seedance2_5", tmp_path)
    assert same == take11_1080 / "take720.mp4" and none is None


def test_prepare_input_per_model(take11_1080, tmp_path):
    src = take11_1080 / "take1080.mp4"
    for model in ("aleph2", "kling_4"):                               # full resolution, full length
        p, prep = C.prepare_input_for_model(src, model, tmp_path)
        assert p == src and prep is None
    g, prep = C.prepare_input_for_model(src, "gemini_omni_flash_1.1", tmp_path)
    assert set(prep) == {"trim"} and _ffprobe_size(g) == (1920, 1080)
    assert 9.9 <= _ffprobe_seconds(g) <= 10.05


@pytest.mark.skipif(not HUB_CLIENT.exists(), reason="hub Runway client not present (public repo)")
def test_seedance_estimate_is_720p_tier(take11_1080, tmp_path):
    def run(model, video):
        out = tmp_path / f"{model}-{video}.json"
        r = subprocess.run([sys.executable, "-m", "seam.compile", "--sheet", str(_sheet_file(tmp_path)),
                            "--laws", str(FIX), "--takes", str(_takes_file(tmp_path)), "--take", "t01",
                            "--material", "ink", "--model", model, "--video", str(take11_1080 / video),
                            "--reference", str(take11_1080 / "crop.png"), "--out", str(out)],
                           capture_output=True, text=True, cwd=C.ROOT)
        assert r.returncode == 0, r.stderr
        e = _estimate(out)
        assert e.returncode == 0, e.stderr
        return json.loads(out.read_text()), json.loads(e.stdout.strip().splitlines()[-1])
    req, est = run("seedance2_5", "take1080.mp4")
    assert req["meta"]["scale"]["height"] == 720
    assert est["tier"] == "720p" and est["estimate_credits"] == 495 and est["warnings"] == []   # 11 x (30 + 15)
    # kling_4: the price depends on duration and options.ratio only, not on the input's resolution
    _, k1080 = run("kling_4", "take1080.mp4")
    _, k720 = run("kling_4", "take720.mp4")
    assert k1080["tier"] == k720["tier"] == "720p" and k1080["estimate_credits"] == k720["estimate_credits"]


def _sheet_file(d):
    p = d / "sheet.json"
    S.write_sheet(p, _sheet())
    return p


def _takes_file(d):
    p = d / "takes.json"
    p.write_text(json.dumps([TAKE_GLASS_INK, {"id": "t07", "cue": "curtain call",
                                              "target_material": ["ink", "gold", "paper"],
                                              "target_position": ["left", "centre", "right"]}]))
    return p


# --- probe and draft trims for any model (R0.5) ---------------------------------------
def _run_cli(tmp_path, d, model, *extra, video="take1080.mp4", name=None):
    out = tmp_path / (name or f"{model}.json")
    r = subprocess.run([sys.executable, "-m", "seam.compile", "--sheet", str(_sheet_file(tmp_path)),
                        "--laws", str(FIX), "--takes", str(_takes_file(tmp_path)), "--take", "t01",
                        "--material", "ink", "--model", model, "--video", str(d / video),
                        "--reference", str(d / "crop.png"), "--out", str(out), *extra],
                       capture_output=True, text=True, cwd=C.ROOT)
    return r, out


@pytest.mark.skipif(not HUB_CLIENT.exists(), reason="hub Runway client not present (public repo)")
@pytest.mark.parametrize("model", sorted(C.MODELS))
def test_probe_arms_all_trimmed_to_10s(take11_1080, tmp_path, model):
    r, out = _run_cli(tmp_path, take11_1080, model, "--trim-to", "10")
    assert r.returncode == 0, r.stderr
    req = json.loads(out.read_text())
    assert req["meta"]["trim"]["start_s"] == 0 and req["meta"]["trim"]["seconds"] == 10
    assert 9.9 <= _ffprobe_seconds(out.parent / req["inputs"]["video"]) <= 10.05
    assert "At 2.40 s" in req["prompt"]                       # a trim from 0 leaves times alone
    e = _estimate(out)
    assert e.returncode == 0, e.stderr
    est = json.loads(e.stdout.strip().splitlines()[-1])
    assert est["input_seconds"] <= 10.05 and est["warnings"] == []


@pytest.mark.skipif(not HUB_CLIENT.exists(), reason="hub Runway client not present (public repo)")
@pytest.mark.parametrize("model", sorted(C.MODELS))
def test_draft_window_shifts_clause_times(take11_1080, tmp_path, model):
    r, out = _run_cli(tmp_path, take11_1080, model, "--window", "1.5", "4")
    assert r.returncode == 0, r.stderr
    req = json.loads(out.read_text())
    trace = json.loads(C.trace_path(out).read_text())
    assert req["meta"]["trim"]["start_s"] == 1.5 and req["meta"]["trim"]["seconds"] == 4
    assert 3.95 <= _ffprobe_seconds(out.parent / req["inputs"]["video"]) <= 4.05
    assert "At 0.90 s, when the glass is set down" in req["prompt"] and "At 2.40 s" not in req["prompt"]
    fired = [c for c in trace["clauses"] if c["law"]]
    assert fired[0]["t"] == 2.4 and fired[0]["t_clip"] == 0.9            # take time kept, clip time added
    assert [c["t_clip"] for c in trace["clauses"] if not c["law"]] == [None]   # the hand at 0.6 s is outside
    e = _estimate(out)
    assert e.returncode == 0, e.stderr
    assert json.loads(e.stdout.strip().splitlines()[-1])["warnings"] == []


def test_targeted_event_outside_window_is_error():
    trim = {"start_s": 5, "seconds": 4, "source": "x.mp4", "source_sha256": "0" * 64}
    with pytest.raises(C.CompileError, match="window"):
        _compile(trim=trim)                                   # the water cue at 2.4 s is before the window


def test_window_options(take11_1080, tmp_path):
    src = take11_1080 / "take1080.mp4"
    out, prep = C.prepare_input_for_model(src, "aleph2", tmp_path, window=(2.0, 4.0))
    assert prep["trim"]["start_s"] == 2.0 and prep["trim"]["seconds"] == 4.0
    assert 3.95 <= _ffprobe_seconds(out) <= 4.05
    s_out, s_prep = C.prepare_input_for_model(src, "seedance2_5", tmp_path, window=(2.0, 4.0))
    assert set(s_prep) == {"trim", "scale"} and _ffprobe_size(s_out) == (1280, 720)
    with pytest.raises(C.CompileError, match="10"):
        C.prepare_input_for_model(src, "gemini_omni_flash_1.1", tmp_path, window=(0, 11))
    with pytest.raises(C.CompileError):
        C.prepare_input_for_model(src, "aleph2", tmp_path, window=(9.0, 4.0))   # past the take's end
    r, _ = _run_cli(tmp_path, take11_1080, "aleph2", "--trim-to", "10", "--window", "0", "4")
    assert r.returncode != 0                                  # one or the other


# --- Gate R review note 8 (call 136): the draft window is computed from the cue sheet, never typed ------------------------
def test_draft_window_starts_one_second_before_the_firing_event():
    sheet = {"events": [{"id": "e01", "t": 0.6, "cue": "hand", "target": None},
                        {"id": "e02", "t": 2.4, "cue": "water", "target": "ink"}]}
    assert C.draft_window(sheet, "ink") == (1.4, 4.0)
    early = {"events": [{"id": "e01", "t": 0.5, "cue": "water", "target": "ink"}]}
    assert C.draft_window(early, "ink") == (0.0, 4.0)                    # not before 0 s
    with pytest.raises(C.CompileError, match="fires"):
        C.draft_window(sheet, "gold")
    assert (C.DRAFT_BEFORE_S, C.DRAFT_SECONDS) == (1.0, 4.0)


def test_the_cli_draft_window_is_the_registered_one(take11_1080, tmp_path):
    r, out = _run_cli(tmp_path, take11_1080, "aleph2", "--draft-window", name="draft.json")
    assert r.returncode == 0, r.stderr
    req = json.loads(out.read_text())
    assert req["meta"]["trim"]["start_s"] == 1.4 and req["meta"]["trim"]["seconds"] == 4.0
    r, _ = _run_cli(tmp_path, take11_1080, "aleph2", "--draft-window", "--window", "0", "4", name="x.json")
    assert r.returncode != 0
