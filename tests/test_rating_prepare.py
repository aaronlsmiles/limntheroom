"""rating/prepare.py on synthetic clips.

Fictional laws only: absurd labels with "(fixture)", nothing from sealed/. The blindpanel steps (lock,
build, verify, export) run through the v0.2 worktree's CLI and are skipped where node or the worktree
is missing."""
import csv
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from analysis import ratings
from rating import prepare as P
from seam.cues import sheet as cue_sheet

ROOT = Path(__file__).resolve().parents[1]
TAKES = ROOT / "capture" / "takes.json"
BP = Path(os.environ.get("BLINDPANEL_CLI") or "/nonexistent/blindpanel.mjs")   # the v0.2.0 checkout's bin/blindpanel.mjs
HAVE_BP = BP.exists() and shutil.which("node") is not None
needs_bp = pytest.mark.skipif(not HAVE_BP, reason="blindpanel v0.2 worktree or node not available")

LAW_CUES = {"glass": "water", "torch": "light", "pen": "pen", "breath": "breath", "note": "note", "hand": "hand"}
RATED = [("t01", "ink", "glass"), ("t01", "gold", "glass"), ("t01", "paper", "glass"), ("t02", "ink", "torch"),
         ("t03", "ink", "pen"), ("t04", "ink", "breath"), ("t05", "ink", "note"), ("t06", "ink", "hand")]
# absurd, fictional, and free of the words ink / gold / paper
FIXTURE_WORDS = ["Juggled dots", "Tipped a hat", "Counted to three", "Stood on its head", "Spun like a top",
                 "Hummed a tune", "Waved a flag", "Tied a bow"]


def fixture_laws():
    laws = []
    for (take, material, cue), word in zip(RATED, FIXTURE_WORDS):
        laws.append({"id": f"{material}.{LAW_CUES[cue]}", "material": material, "cue": LAW_CUES[cue],
                     "behaviour": f"{word.lower()} while a fixture band plays. A fictional fixture law.",
                     "label": f"{word} (fixture)", "clause": f"{word.lower()} with great ceremony (fixture)",
                     "touches": None, "rated": True})
    laws.append({"id": "paper.hand", "material": "paper", "cue": "hand", "behaviour": "Does a cartwheel. Fictional.",
                 "label": "Cartwheeled (fixture)", "clause": "cartwheels around the page (fixture)", "touches": "hand",
                 "rated": False})
    return {"salt": "fixture-salt", "materials": {"ink": {"look": "a wobbly fixture look"},
                                                  "gold": {"look": "a shiny fixture look"},
                                                  "paper": {"look": "a crinkly fixture look"}},
            "laws": laws, "decoys": ["Decoy one (fixture)", "Decoy two (fixture)"]}


def synth(path, *, seconds, fps, size=(640, 360), hue=0, tags=True, audio=True):
    w, h = size
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate={fps}:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    cmd += ["-vf", f"hue=h={hue}", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    if tags:
        cmd += ["-metadata", "title=Runway seedance render", "-metadata", "comment=made by kling",
                "-metadata:s:v:0", "handler_name=gemini"]
    subprocess.run(cmd + [str(path)], check=True)
    return Path(path)


def inject_c2pa(path):
    """Append a top-level C2PA-style uuid box holding a JUMBF superbox: what a signed render carries."""
    jumd = struct.pack(">I4s", 8 + 16, b"jumd") + b"c2pa" + b"\0" * 12
    jumb = struct.pack(">I4s", 8 + len(jumd), b"jumb") + jumd
    uuid = struct.pack(">I4s", 8 + 16 + len(jumb), b"uuid") + P.C2PA_UUID + jumb
    with open(path, "ab") as f:
        f.write(uuid)
    return path


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def work(tmp_path_factory):
    """Eight synthetic renders at different rates, sizes and lengths, each tagged and C2PA-signed."""
    d = tmp_path_factory.mktemp("rating")
    (d / "src").mkdir()
    shapes = [(2.4, 24, (640, 360)), (2.2, 30, (640, 360)), (2.6, 25, (320, 180)), (2.5, 24, (640, 360)),
              (2.3, 30, (960, 540)), (2.4, 24, (640, 360)), (2.7, 25, (640, 360)), (2.5, 24, (640, 360))]
    entries = []
    for i, ((take, material, cue), (sec, fps, size)) in enumerate(zip(RATED, shapes)):
        render = inject_c2pa(synth(d / "src" / f"render-{take}-{material}.mp4", seconds=sec, fps=fps, size=size, hue=40 * i))
        take_video = synth(d / "src" / f"take-{take}-{material}.mp4", seconds=3, fps=30, hue=40 * i + 10, tags=False, audio=False)
        e = {"take": take, "material": material, "render": f"src/{render.name}", "take_video": f"src/{take_video.name}"}
        if i % 2:
            e["cue_s"] = 1.0 + i * 0.1
        else:
            sc = cue_sheet.assemble(take=take, fps=30, n_frames=90, size=(640, 360), fires=LAW_CUES[cue], target=material,
                                    events=[cue_sheet.make_event(t=0.8 + i * 0.1, t_end=1.5, cue=LAW_CUES[cue], what="fixture",
                                                                 source="hand", evidence={})])
            cue_sheet.write_sheet(d / "src" / f"cues-{take}-{material}.json", sc)
            e["cues"] = f"src/cues-{take}-{material}.json"
        entries.append(e)
    (d / "inputs.json").write_text(json.dumps({"schema": P.INPUTS_SCHEMA, "entries": entries}))
    (d / "laws.json").write_text(json.dumps(fixture_laws()))
    takes = json.loads(TAKES.read_text())
    for t in takes:
        if t["id"] == "t03":
            t["ring_bbox"] = [0.3, 0.2, 0.45, 0.5]
    (d / "takes.json").write_text(json.dumps(takes))
    return d


FAST = ["--frames", "12"]          # extra builds need not be long


def args(work, out="out", sealed="sealed", *extra):
    out, sealed = (Path(x) if Path(x).is_absolute() else work / x for x in (out, sealed))
    return P.parse_args(["build", "--inputs", str(work / "inputs.json"), "--laws", str(work / "laws.json"),
                         "--takes", str(work / "takes.json"), "--out", str(out), "--sealed", str(sealed),
                         "--raters", "2", "--seconds", "2.0", *extra])


def seal_args(work, sealed="sealed", laws="laws.json", *extra):
    sealed = Path(sealed) if Path(sealed).is_absolute() else work / sealed
    return P.parse_args(["seal", "--laws", str(work / laws), "--takes", str(work / "takes.json"), "--sealed", str(sealed), *extra])


@pytest.fixture(scope="module")
def built(work):
    P.seal(seal_args(work))                                   # Gate R: once
    return P.prepare(args(work, "out", "sealed", *([] if HAVE_BP else ["--no-blindpanel"])))


def sealed_copy(work, tmp_path):
    """A private copy of the sealed pair, for tests that tamper with it."""
    d = tmp_path / "sealed"
    d.mkdir()
    for n in ("answer-key.json", "q2-options.json"):
        shutil.copy(work / "sealed" / n, d / n)
    return d


# --- the kit's code scheme ----------------------------------------------------------------------
@needs_bp
def test_opaque_codes_match_the_kit():
    script = ("import {opaqueCode} from '%s'; const out=[];"
              "for (const [s,k,i] of JSON.parse(process.argv[1])) out.push(await opaqueCode(s,k,i));"
              "console.log(JSON.stringify(out))" % (BP.parent.parent / "dist" / "core" / "codes.js"))
    cases = [["abcd1234", "clip", "t01-ink"], ["abcd1234", "panel", "t01-ink"], ["zz-seed-9", "clip", "x"],
             ["s0123456789abcdef01234567", "panel", "t06-ink"]]
    r = subprocess.run(["node", "--input-type=module", "-e", script, json.dumps(cases)], capture_output=True, text=True, check=True)
    assert json.loads(r.stdout) == [P.opaque_code(*c) for c in cases]


# --- rating copies ---------------------------------------------------------------------------
def test_the_strip_removes_tags_and_provenance(work, tmp_path):
    src = work / "src" / "render-t01-ink.mp4"
    raw = src.read_bytes()
    assert b"jumb" in raw and P.C2PA_UUID in raw and b"Runway" in raw and b"kling" in raw   # the fixture is dirty
    assert P.scan_container(src)                                                              # and the scan sees it
    dst = P.make_rating_copy(src, tmp_path / "copy.mp4", frames=40)
    out = dst.read_bytes()
    for needle in (b"jumb", b"jumd", b"c2pa", P.C2PA_UUID, b"Runway", b"seedance", b"kling", b"gemini", b"uuid"):
        assert needle not in out, needle
    facts = P.check_rating_copy(dst, frames=40)
    assert facts["width"] == 1280 and facts["height"] == 720 and facts["frames"] == 40
    d = P.probe(dst)
    assert len(d["streams"]) == 1 and d["streams"][0]["codec_type"] == "video"          # no audio stream
    assert set(d["streams"][0]["tags"]) <= {"language", "handler_name"}
    assert set(d["format"].get("tags", {})) <= P.OK_FORMAT_TAGS
    with pytest.raises(P.PrepareError, match="provenance|streams|tag"):
        P.check_rating_copy(src, frames=40)


def test_a_copy_is_byte_identical_on_a_rerun(work, tmp_path):
    src = work / "src" / "render-t02-ink.mp4"
    a = P.make_rating_copy(src, tmp_path / "a.mp4", frames=30)
    b = P.make_rating_copy(src, tmp_path / "b.mp4", frames=30)
    assert sha(a) == sha(b)


def test_a_short_source_is_refused_not_padded(work, tmp_path):
    src = work / "src" / "render-t01-ink.mp4"            # 2.4 s: 57 frames at 24 fps
    dst = P.make_rating_copy(src, tmp_path / "long.mp4", frames=200)
    with pytest.raises(P.PrepareError, match="frames, want 200"):
        P.check_rating_copy(dst, frames=200)


def test_the_registered_length_is_12_s_or_the_shortest_render(work, capsys, tmp_path):
    srcs = [work / "src" / f"render-{t}-{m}.mp4" for t, m, _ in RATED]
    shortest = min(P.available_frames(s, 24) for s in srcs)
    assert P.REGISTERED_SECONDS == 12.0
    assert P.common_frames(srcs, 24) == min(int(12.0 * 24), shortest)  # call 135: no length is chosen after the renders
    assert P.common_frames(srcs, 24, seconds=1.5) == 36
    assert P.common_frames(srcs, 24, frames=17) == 17
    with pytest.raises(P.PrepareError, match="shorter than the chosen length"):
        P.common_frames(srcs, 24, seconds=2.3)                         # the 2.2 s source is shorter: refused, not padded
    assert not (tmp_path / "x").exists()
    lines = P.describe_lengths(srcs, 24, 36)
    assert len(lines) == len(srcs) + 1 and "chosen" in lines[-1] and "36 frames" in lines[-1]
    assert "2.2" in lines[1]                                           # each source's own length is shown


def test_build_without_a_length_uses_the_registered_one(built, work, tmp_path):
    a = args(work, tmp_path / "o", work / "sealed", "--no-blindpanel")
    a.seconds = a.frames = None
    P.prepare(a)                                                       # 12 s or the shortest render, never a choice
    srcs = [work / "src" / f"render-{t}-{m}.mp4" for t, m, _ in RATED]
    want = min(int(P.REGISTERED_SECONDS * P.FPS), min(P.available_frames(s, P.FPS) for s in srcs))
    copies = sorted((tmp_path / "o" / "media").rglob("*.mp4"))
    assert copies and all(P.video_facts(c)["frames"] == want for c in copies)


def test_a_chosen_length_longer_than_a_source_stops_before_encoding(built, work, tmp_path, capsys):
    a = args(work, tmp_path / "o", work / "sealed", "--no-blindpanel")
    a.seconds = 2.5
    with pytest.raises(P.PrepareError, match="shorter than the chosen length"):
        P.prepare(a)
    assert not (tmp_path / "o" / "media").exists()
    b = args(work, tmp_path / "o2", work / "sealed", "--no-blindpanel", "--frames", "10")
    P.prepare(b)
    out = capsys.readouterr().out
    assert "chosen: 10 frames" in out and out.count("render-") == 8     # each source's own length is printed


def test_the_container_scan_finds_a_planted_xmp_box(tmp_path):
    p = tmp_path / "x.mp4"
    synth(p, seconds=1, fps=24, tags=False, audio=False)
    P.make_rating_copy(p, tmp_path / "clean.mp4", frames=12)
    assert P.scan_container(tmp_path / "clean.mp4") == []
    with open(tmp_path / "clean.mp4", "ab") as f:
        f.write(struct.pack(">I4s", 12, b"XMP_") + b"abcd")
    assert any("XMP_" in x for x in P.scan_container(tmp_path / "clean.mp4"))


# --- the pipeline ----------------------------------------------------------------------------
def test_copies_have_identical_size_and_frame_count(built, work):
    media = work / "out" / "media"
    mp4s = sorted(media.glob("*.mp4"))
    assert len(mp4s) == 8
    facts = [P.check_rating_copy(p, frames=built["frames"], banned=[]) for p in mp4s]
    assert {(f["width"], f["height"], f["frames"], f["r_frame_rate"], f["pix_fmt"]) for f in facts} == {(1280, 720, built["frames"], "24/1", "yuv420p")}
    assert built["frames"] == 48


def test_files_are_named_by_opaque_code_only(built, work):
    media = work / "out" / "media"
    names = sorted(p.name for p in media.iterdir())
    assert all(re.fullmatch(r"[cp][0-9a-hjkmnp-tv-z]{5}\.(mp4|png)", n) for n in names), names
    assert len(names) == 16
    assert not any(s in " ".join(names) for s in ("ink", "gold", "paper", "render"))
    codes = {i["clip_code"] for i in built["items"]} | {i["panel_code"] for i in built["items"]}
    assert {n.split(".")[0] for n in names} == codes
    assert set(built["studies"]) == {"limn-r1", "limn-r2"}


def test_png_stills_carry_no_text_chunks(built, work):
    for p in (work / "out" / "media").glob("*.png"):
        data = p.read_bytes()
        assert not any(c in data for c in (b"tEXt", b"iTXt", b"zTXt", b"eXIf"))


def test_the_ring_sits_where_the_box_says(built, work):
    from PIL import Image, ImageChops
    ent = {i["ref"]: i for i in built["items"]}
    inp = {(e["take"], e["material"]): e for e in json.loads((work / "inputs.json").read_text())["entries"]}
    for ref in ("t03-ink", "t01-gold", "t06-ink"):
        i = ent[ref]
        ringed = Image.open(work / "out" / "media" / f"{i['panel_code']}.png").convert("RGB")
        e = inp[(ref.split("-")[0], ref.split("-")[1])]
        plain = P.extract_frame(work / e["take_video"], i["cue_s"])
        diff = ImageChops.difference(ringed, plain).convert("L").point(lambda v: 255 if v > 8 else 0)
        box = diff.getbbox()
        cx, cy, a, b = P.ring_geometry(i["ring_bbox"])
        pad = P.RING_WIDTH + 2
        assert box is not None
        assert abs(box[0] - (cx - a)) <= pad and abs(box[2] - (cx + a)) <= pad
        assert abs(box[1] - (cy - b)) <= pad and abs(box[3] - (cy + b)) <= pad
        # the creature's box is inside the ring, untouched
        x0, y0, x1, y1 = (int(v * s) for v, s in zip(i["ring_bbox"], (1280, 720, 1280, 720)))
        assert diff.crop((x0, y0, x1, y1)).getbbox() is None
        assert ringed.size == (1280, 720)
    # every ring is the row's own ring_bbox (t03's is the fixture's override); there is no placeholder
    takes = {(t["id"], t["target_material"]): t for t in json.loads((work / "takes.json").read_text()) if t.get("rated")}
    for ref in ("t03-ink", "t01-gold", "t06-ink"):
        assert ent[ref]["ring_bbox"] == takes[tuple(ref.split("-"))]["ring_bbox"]


def test_ring_geometry_and_a_missing_box_is_refused():
    from PIL import Image
    img = Image.new("RGB", (1280, 720), (240, 235, 220))
    out = P.draw_ring(img, (0.4, 0.4, 0.6, 0.6))
    d = [(x, y) for x in range(1280) for y in range(0, 720, 3) if out.getpixel((x, y)) != img.getpixel((x, y))]
    xs, ys = [p[0] for p in d], [p[1] for p in d]
    assert abs((min(xs) + max(xs)) / 2 - 640) <= 2 and abs((min(ys) + max(ys)) / 2 - 360) <= 3
    assert out.getpixel((640, 360)) == img.getpixel((640, 360))      # inside: untouched
    assert out.getpixel((10, 10)) == img.getpixel((10, 10))          # far away: untouched
    # a neutral ring: grey, not a material colour
    ring_px = out.getpixel((min(xs) + 2, 360))
    assert max(ring_px) - min(ring_px) < 40 or ring_px == img.getpixel((min(xs) + 2, 360))
    assert P.ring_box({"id": "x", "target_position": "left", "ring_bbox": [0.1, 0.1, 0.2, 0.2]}) == (0.1, 0.1, 0.2, 0.2)
    # no placeholder from target_position: a missing, empty, short or out-of-frame box is refused
    for bad in ({"id": "x", "target_position": "left"}, {"id": "x", "target_position": "right", "ring_bbox": None},
                {"id": "x", "target_position": "left", "ring_bbox": [0.1, 0.1, 0.2]},
                {"id": "x", "target_position": "left", "ring_bbox": [0.1, 0.1, 1.2, 0.2]}):
        with pytest.raises(P.PrepareError, match="ring_bbox"):
            P.ring_box(bad)
    with pytest.raises(P.PrepareError):
        P.ring_geometry((0.6, 0.1, 0.4, 0.2))


def test_a_rated_row_without_a_ring_bbox_stops_the_build(built, work, tmp_path):
    """S11: the build never rings a guessed box. A rated row with no ring_bbox stops it before anything is encoded."""
    takes = json.loads((work / "takes.json").read_text())
    for t in takes:
        if (t["id"], t["target_material"]) == ("t01", "gold"):
            t.pop("ring_bbox", None)
    (tmp_path / "takes.json").write_text(json.dumps(takes))
    a = P.parse_args(["build", "--inputs", str(work / "inputs.json"), "--laws", str(work / "laws.json"),
                      "--takes", str(tmp_path / "takes.json"), "--out", str(tmp_path / "out"),
                      "--sealed", str(sealed_copy(work, tmp_path)), "--raters", "1", *FAST, "--no-blindpanel"])
    with pytest.raises(P.PrepareError, match=r"t01/gold.*ring_bbox"):
        P.prepare(a)
    assert not (tmp_path / "out" / "media").exists()


def test_ring_bbox_from_mask_pads_the_home_box():
    import numpy as np
    m = np.zeros((720, 1280), bool)
    m[255:318, 426:527] = True                                  # rows 255-317, columns 426-526
    p = P.RING_PAD_PX
    got = P.ring_bbox_from_mask(m)
    assert got == pytest.approx(((426 - p) / 1280, (255 - p) / 720, (527 + p) / 1280, (318 + p) / 720), abs=5e-5)
    assert all(v == round(v, 4) for v in got)                   # four places: stable through JSON
    edge = np.zeros((720, 1280), bool)
    edge[0:10, 1275:1280] = True
    assert P.ring_bbox_from_mask(edge)[1] == 0.0 and P.ring_bbox_from_mask(edge)[2] == 1.0   # clamped to the frame
    with pytest.raises(P.PrepareError):
        P.ring_bbox_from_mask(np.zeros((720, 1280), bool))      # an empty home has no box
    with pytest.raises(P.PrepareError):
        P.ring_bbox_from_mask(np.ones((360, 640), bool))        # only the registered 1280x720 grid


# --- the committed boxes against the real masks (skipped where the mask files are absent) -----------
MASKS = ROOT / "masks"


def _ring_tool():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ring_boxes", ROOT / "tools" / "ring_boxes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not all((MASKS / f"{m}.npz").exists() for m in mod.CHOSEN.values()):
        pytest.skip("the chosen takes' mask files are not here")
    return mod


def test_the_committed_ring_boxes_are_the_masks_boxes():
    """capture/takes.json carries each rated row's box, and it is exactly what the masks give."""
    tool = _ring_tool()
    takes = json.loads(TAKES.read_text())
    want = tool.boxes(takes, MASKS)
    for t, w in zip(takes, want):
        if t.get("rated"):
            assert w is not None and t.get("ring_bbox") == w, \
                f"{t['id']}/{t['target_material']}: ring_bbox {t.get('ring_bbox')} != {w} from the masks (tools/ring_boxes.py --write)"
        else:
            assert "ring_bbox" not in t and w is None


def test_each_committed_ring_holds_its_creature_and_no_other():
    """S11 on the real masks: on the 1280x720 still each ring encloses its creature's static home, at least
    MIN_CLEAR px from the stroke, and keeps every other creature's home that far outside it."""
    import cv2
    import numpy as np
    from PIL import Image
    from seam.controls_inputs import static_mask
    from seam.masks import load_masks
    MIN_CLEAR = 8
    tool = _ring_tool()
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * MIN_CLEAR + 1, 2 * MIN_CLEAR + 1))
    yy, xx = np.mgrid[0:720, 0:1280]
    for t in json.loads(TAKES.read_text()):
        if not t.get("rated"):
            continue
        _, masks = load_masks(MASKS / f"{tool.CHOSEN[t['id']]}.npz")
        ring = np.asarray(P.draw_ring(Image.new("RGB", (1280, 720)), t["ring_bbox"], colour=(255, 255, 255)).convert("L")) > 0
        cx, cy, a, b = P.ring_geometry(t["ring_bbox"])
        disc = ((xx - cx) / a) ** 2 + ((yy - cy) / b) ** 2 <= 1          # the ring and all it encloses
        for name in ("home_ink", "home_gold", "home_paper"):
            near = cv2.dilate(static_mask(masks[name]).astype(np.uint8), kernel).astype(bool)
            if name == f"home_{t['target_material']}":
                assert not (near & ring).any() and (near <= disc).all(), f"{t['id']}/{t['target_material']}: the ring crowds its creature"
            else:
                assert not (near & disc).any(), f"{t['id']}/{t['target_material']}: the ring reaches {name}"


def test_cue_frame_comes_from_the_sheet_or_cue_s(built, work):
    by_ref = {i["ref"]: i for i in built["items"]}
    assert by_ref["t01-ink"]["cue_s"] == pytest.approx(0.8)          # entry 0: from its sheet
    assert by_ref["t01-gold"]["cue_s"] == pytest.approx(1.1)         # entry 1: cue_s


def test_the_study_asks_what_the_plan_says(built, work):
    st = json.loads((work / "out" / "studies" / "limn-r1" / "study.yaml").read_text().split("\n", 1)[1])
    q1, q2 = st["scales"]["reacts"], st["scales"]["acts"]
    assert q1["kind"] == q2["kind"] == "choice"
    assert len(q1["labels"]) == 8 and len(q2["labels"]) == 12
    assert q1["labels"][-2:] == ["Nothing in particular", "Can't tell"] == q2["labels"][-2:]
    fixture = fixture_laws()
    want = {law["label"] for law in fixture["laws"] if law["rated"]} | set(fixture["decoys"])
    assert set(q2["labels"][:-2]) == want
    law_order = [law["label"] for law in fixture["laws"] if law["rated"]] + fixture["decoys"]
    assert q2["labels"][:-2] != law_order           # shuffled at Gate R: the decoys are not parked at the end
    assert q2["labels"] == json.loads((work / "sealed" / "q2-options.json").read_text())["options"]   # and read, not redrawn
    assert [(q["id"], q["part"], q["text"]) for q in st["questions"]] == [
        ("q1b", "baseline", "If the ringed drawing came alive here, what would it react to?"),
        ("q2b", "baseline", "What would it do?"), ("q1", "clips", "What did the creature react to?"),
        ("q2", "clips", "What did it do?")]
    assert st["modes"]["public"]["tally"] is False and st["modes"]["public"]["submit"] is True
    assert st["parts"]["clips"]["session_size"] == 8 and st["parts"]["baseline"]
    assert len(st["items"]["panels"]) == len(st["items"]["clips"]) == 8
    assert all(c["reference"] == c["id"] for c in st["items"]["clips"])
    assert all(c["label"] == i["clip_code"] for c, i in zip(st["items"]["clips"], built["items"]))   # the reveal shows codes
    a = (work / "out" / "studies" / "limn-r1" / "study.yaml").read_text()
    b = (work / "out" / "studies" / "limn-r2" / "study.yaml").read_text()
    assert a != b and a.replace("limn-r1", "limn-r2") == b       # the studies differ in id only


def test_the_banned_terms_file_holds_models_materials_slug_and_law_words(built, work):
    text = (work / "out" / "studies" / "limn-r1" / "banned-terms.txt").read_text()
    banned = P.parse_banned(text)
    fixture = fixture_laws()
    for must in ("seedance", "kling", "aleph", "gemini", "runway"):
        assert P.find_banned(f"made with {must.upper()} today", banned), must
    for must in ("ink", "gold", "paper"):
        assert P.find_banned(f"a {must} drawing", banned), must
    assert not P.find_banned("a --bp-ink variable and think", banned)          # the kit's own CSS and plain words are fine
    assert P.find_banned("the limntheroom repo", banned) and P.find_banned("Limn the Room", banned)
    for law in fixture["laws"]:
        assert P.find_banned(law["clause"], banned) and P.find_banned(law["id"], banned)
    assert P.find_banned(fixture["materials"]["ink"]["look"], banned)
    assert not P.find_banned("Juggled dots (fixture)", banned)                  # a label a rater sees is not banned
    assert not P.find_banned(P.public_wording(P.build_study("x", seed="abcd1234", instrument="1", q2=P.draw_q2_options(fixture, "abcd1234"),
                                                               items=[], fps=24, frames=24, media_base="")), banned)


def test_a_material_name_in_a_q2_label_stops_the_build(work, tmp_path):
    laws = fixture_laws()
    laws["laws"][0]["label"] = "Spilled ink (fixture)"
    (work / "laws-bad.json").write_text(json.dumps(laws))
    P.seal(seal_args(work, tmp_path / "s", "laws-bad.json"))
    a = args(work, tmp_path / "bad-out", tmp_path / "s", "--no-blindpanel")
    a.laws = str(work / "laws-bad.json")
    with pytest.raises(P.PrepareError, match="banned entries"):
        P.prepare(a)
    assert not (tmp_path / "bad-out" / "media").exists()          # nothing was encoded


def test_inputs_must_match_the_rated_takes_and_laws(work, tmp_path):
    doc = json.loads((work / "inputs.json").read_text())
    laws, takes = P.load_laws(work / "laws.json"), json.loads((work / "takes.json").read_text())
    ok = tmp_path / "ok.json"
    shutil.copytree(work / "src", tmp_path / "src")
    ok.write_text(json.dumps(doc))
    assert len(P.load_inputs(ok, takes, laws)) == 8
    short = tmp_path / "short.json"
    short.write_text(json.dumps({**doc, "entries": doc["entries"][:-1]}))
    with pytest.raises(P.PrepareError, match="disagree"):
        P.load_inputs(short, takes, laws)
    laws2 = fixture_laws()
    laws2["laws"] = [law for law in laws2["laws"] if law["id"] != "ink.hand"]
    with pytest.raises(P.PrepareError, match="ink.hand"):
        P.load_inputs(ok, takes, laws2)


# --- the sealed answer key ------------------------------------------------------------------
def test_the_answer_key_has_ratings_py_shape_codes_and_a_salt(built, work):
    key = json.loads((work / "sealed" / "answer-key.json").read_text())
    assert re.fullmatch(r"[0-9a-f]{32}", key["salt"]) and key["seed"] == P.seed_from_salt(key["salt"])
    assert key["questions"] == {"clip_target": "q1", "clip_behaviour": "q2", "base_target": "q1b", "base_behaviour": "q2b"}
    assert sorted(key["clips"]) == sorted(key["baseline"]) == sorted(f"{t}-{m}" for t, m, _ in RATED)
    k = key["clips"]["t01-gold"]
    assert k == {"law": "gold.water", "target": "The glass of water", "behaviour": "Tipped a hat (fixture)"}
    assert key["clips"]["t06-ink"]["target"] == "The hand" and key["clips"]["t02-ink"]["target"] == "The torch's light"
    assert key["baseline"] == key["clips"]
    # the codes are the sealed ones: the studies and the media use them
    assert {i["ref"]: i["clip_code"] for i in built["items"]} == key["codes"]["clips"]
    assert {i["ref"]: i["panel_code"] for i in built["items"]} == key["codes"]["panels"]
    man = json.loads((work / "sealed" / "rating-manifest.json").read_text())
    assert man["key_sha256"] == sha(work / "sealed" / "answer-key.json") and man["salt"] == key["salt"]
    assert man["q2_options_sha256"] == sha(work / "sealed" / "q2-options.json")


def test_build_refuses_without_the_sealed_key_or_options(work, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(P.PrepareError, match="answer-key.json is missing"):
        P.prepare(args(work, tmp_path / "o", empty, "--no-blindpanel"))
    d = sealed_copy(work, tmp_path)
    (d / "q2-options.json").unlink()
    with pytest.raises(P.PrepareError, match="q2-options.json is missing"):
        P.prepare(args(work, tmp_path / "o", d, "--no-blindpanel", *FAST))
    assert not (tmp_path / "o" / "media").exists()


def test_build_refuses_codes_that_do_not_match_the_clips(work, tmp_path):
    d = sealed_copy(work, tmp_path)
    key = json.loads((d / "answer-key.json").read_text())

    def run(k):
        (d / "answer-key.json").write_text(json.dumps(k))
        return P.prepare(args(work, tmp_path / "o", d, "--no-blindpanel", *FAST))

    bad = json.loads(json.dumps(key))
    bad["codes"]["clips"]["t03-ink"] = "c00000"                       # a code the kit would not derive
    with pytest.raises(P.PrepareError, match="t03-ink.*not the kit's code"):
        run(bad)
    bad = json.loads(json.dumps(key))
    bad["seed"] = "s" + "0" * 24                                      # a different seed: every code is wrong
    with pytest.raises(P.PrepareError, match="not the kit's code"):
        run(bad)
    bad = json.loads(json.dumps(key))
    del bad["clips"]["t04-ink"], bad["baseline"]["t04-ink"]
    with pytest.raises(P.PrepareError, match="not the rated takes"):
        run(bad)
    bad = json.loads(json.dumps(key))
    bad["codes"]["panels"].pop("t02-ink")
    with pytest.raises(P.PrepareError, match="do not cover"):
        run(bad)
    bad = json.loads(json.dumps(key))
    bad["clips"]["t05-ink"]["behaviour"] = "Something else (fixture)"
    with pytest.raises(P.PrepareError, match="disagrees with the takes and laws"):
        run(bad)
    assert not (tmp_path / "o" / "media").exists()
    run(key)                                                          # the untouched key builds


def test_the_q2_order_is_read_never_reordered(work, tmp_path):
    d = sealed_copy(work, tmp_path)
    q = json.loads((d / "q2-options.json").read_text())
    custom = list(reversed(q["options"][:-2])) + q["options"][-2:]    # a hand-picked order, as sealed
    (d / "q2-options.json").write_text(json.dumps({**q, "options": custom}))
    P.prepare(args(work, tmp_path / "o", d, "--no-blindpanel", *FAST))
    st = json.loads((tmp_path / "o" / "studies" / "limn-r1" / "study.yaml").read_text().split("\n", 1)[1])
    assert st["scales"]["acts"]["labels"] == custom
    # the fixed pair must stay last, and the set must be the laws' labels and decoys
    for bad in (custom[:-2] + [custom[-1], custom[-2]], custom[:-3] + ["Another (fixture)"] + custom[-2:], custom[:-1]):
        (d / "q2-options.json").write_text(json.dumps({**q, "options": bad}))
        with pytest.raises(P.PrepareError, match="disagrees with the laws file"):
            P.prepare(args(work, tmp_path / "o", d, "--no-blindpanel", *FAST))


def test_seal_draws_once_and_refuses_to_overwrite(work, tmp_path):
    P.seal(seal_args(work, tmp_path / "s"))
    first = {n: sha(tmp_path / "s" / n) for n in ("answer-key.json", "q2-options.json")}
    with pytest.raises(P.PrepareError, match="drawn once"):
        P.seal(seal_args(work, tmp_path / "s"))
    assert first == {n: sha(tmp_path / "s" / n) for n in first}
    P.seal(seal_args(work, tmp_path / "s", "laws.json", "--force"))
    assert sha(tmp_path / "s" / "answer-key.json") != first["answer-key.json"]
    k = json.loads((tmp_path / "s" / "answer-key.json").read_text())
    assert k["ids"]["t01-ink"] == P.kit_id(k["salt"], "t01-ink")
    assert k["codes"]["clips"]["t01-ink"] == P.opaque_code(k["seed"], "clip", k["ids"]["t01-ink"])
    o = json.loads((tmp_path / "s" / "q2-options.json").read_text())["options"]
    assert len(o) == 12 and o[-2:] == ["Nothing in particular", "Can't tell"]


def test_a_rerun_keeps_codes_and_bytes(work, tmp_path):
    a = args(work, tmp_path / "o", work / "sealed", "--no-blindpanel", *FAST)
    m1, m2 = P.prepare(a), P.prepare(a)
    assert m1["items"] == m2["items"] and m1["key_sha256"] == m2["key_sha256"] == sha(work / "sealed" / "answer-key.json")
    assert [i["clip_code"] for i in m1["items"]] == [i["clip_code"] for i in m2["items"]]


def _export_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(ratings.COLUMNS)
        w.writerows(rows)


def test_the_key_scores_a_fixture_export(built, work, tmp_path):
    key = json.loads((work / "sealed" / "answer-key.json").read_text())
    st = json.loads((work / "out" / "studies" / "limn-r1" / "study.yaml").read_text().split("\n", 1)[1])
    hand = key["clips"]["t06-ink"]["behaviour"]
    wrong = next(x for x in st["scales"]["acts"]["labels"] if x != hand)
    rows, pos = [], 0
    for ref, k in sorted(key["clips"].items()):
        pos += 1
        # a perfect rater, except that the hand take's behaviour is wrong
        beh = wrong if ref == "t06-ink" else k["behaviour"]
        rows += [["V0001", "1", "clips", pos, ref, "q1", 1, "", k["target"]], ["V0001", "1", "clips", pos, ref, "q2", 1, "", beh],
                 ["V0001", "1", "baseline", pos, ref, "q1b", 1, "", "Nothing in particular"],
                 ["V0001", "1", "baseline", pos, ref, "q2b", 1, "", "Can't tell"]]
    _export_csv(tmp_path / "ratings.csv", rows)
    out = ratings.analyse({"R1": ratings.read_export(tmp_path / "ratings.csv")}, key)
    assert sorted(out["laws"]) == sorted(law["id"] for law in fixture_laws()["laws"] if law["rated"])
    assert out["laws"]["ink.water"]["clip"]["law"]["k"] == 1
    assert out["laws"]["ink.hand"]["clip"]["q1"]["k"] == 1 and out["laws"]["ink.hand"]["clip"]["law"]["k"] == 0
    assert out["laws"]["ink.hand"]["baseline"]["q1b"]["k"] == 0 and out["laws"]["gold.water"]["baseline"]["q2b"]["n"] == 1


# --- blindpanel ----------------------------------------------------------------------------
@needs_bp
def test_every_study_is_locked_built_and_verified(built, work):
    for sid in built["studies"]:
        d = work / "out" / "studies" / sid
        lock = json.loads((d / "study.lock.json").read_text())
        assert lock["instrument"] == "1" and re.fullmatch(r"[0-9a-f]{64}", lock["text_sha256"])
        code = subprocess.run(["node", str(BP), "verify", str(d / "study.yaml"), "--dist", str(d / "dist")], capture_output=True, text=True)
        assert code.returncode == 0, code.stdout
        assert "all " in code.stdout and "checks passed" in code.stdout
    assert built["locks"]["limn-r1"] == built["locks"]["limn-r2"]            # same wording, same hash


@needs_bp
def test_banned_terms_are_absent_from_the_built_study(built, work):
    banned = P.parse_banned((work / "out" / "studies" / "limn-r1" / "banned-terms.txt").read_text())
    for sid in built["studies"]:
        dist = work / "out" / "studies" / sid / "dist"
        for f in dist.rglob("*"):
            assert not P.find_banned(f.name, banned), f
            if f.suffix in (".html", ".js", ".css", ".json") and f.name != "reveal.json":
                assert not P.find_banned(f.read_text(), banned), f
        reveal = json.loads((dist / "reveal.json").read_text())
        assert all(v["label"] == k and v["meta"] == {} for k, v in reveal["items"].items())
        assert reveal["reference"] is None
        study = json.loads((dist / "study.json").read_text())
        assert study["modes"]["public"]["tally"] is False
        assert not any(w in json.dumps(study) for w in ("t01", "t02", "-ink", "render-"))     # no item ids or refs on the page
    # the media the raters fetch carry no provenance
    for f in (work / "out" / "studies" / "limn-r1" / "dist" / "media").glob("*.mp4"):
        assert P.scan_container(f, banned) == []


@needs_bp
def test_a_changed_wording_without_a_new_instrument_stops_the_lock(work, tmp_path):
    P.seal(seal_args(work, tmp_path / "s"))
    a = args(work, tmp_path / "o", tmp_path / "s", *FAST)
    P.prepare(a)
    P.prepare(a)                                              # same wording: the lock still matches
    laws = fixture_laws()
    laws["decoys"][0] = "Decoy uno (fixture)"
    (work / "laws2.json").write_text(json.dumps(laws))
    P.seal(seal_args(work, tmp_path / "s", "laws2.json", "--force"))      # Gate R redone with a changed label
    b = args(work, tmp_path / "o", tmp_path / "s", *FAST)
    b.laws = str(work / "laws2.json")
    with pytest.raises(P.PrepareError, match="lock"):
        P.prepare(b)
    b.instrument = "2"
    assert P.prepare(b)["locks"]["limn-r1"]["instrument"] == "2"      # a new instrument re-locks


@needs_bp
def test_the_real_export_path_matches_the_key(built, work, tmp_path):
    """A visitor's submission goes through `blindpanel export`; ratings.py scores its ratings.csv with our key."""
    sid = built["studies"][0]
    d = work / "out" / "studies" / sid
    study = json.loads((d / "dist" / "study.json").read_text())
    session = "0b9a6b1e-3c2d-4e5f-8a7b-1c2d3e4f5a6b"
    js = ("import {participantOrder} from '%s'; import fs from 'node:fs';"
          "const s=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));"
          "console.log(JSON.stringify(await participantOrder(s, process.argv[2])))" % (BP.parent.parent / "dist" / "core" / "order.js"))
    order = json.loads(subprocess.run(["node", "--input-type=module", "-e", js, str(d / "dist" / "study.json"), session],
                                      capture_output=True, text=True, check=True).stdout)
    assert len(order["blocks"]) == 1 and len(order["blocks"][0]["baseline"]) == 8 and len(order["blocks"][0]["clips"]) == 8
    by_clip = {i["clip_code"]: i for i in built["items"]}
    by_panel = {i["panel_code"]: i for i in built["items"]}
    key = json.loads((work / "sealed" / "answer-key.json").read_text())
    q1, q2 = study["scales"]["reacts"]["labels"], study["scales"]["acts"]["labels"]
    perfect = {"clips": {}, "baseline": {}}
    for code in order["clips"]:
        k = key["clips"][by_clip[code]["ref"]]
        perfect["clips"][code] = {"q1": q1.index(k["target"]) + 1, "q2": q2.index(k["behaviour"]) + 1}
    for code in order["baseline"]:
        k = key["baseline"][by_panel[code]["ref"]]
        perfect["baseline"][code] = {"q1b": q1.index("Nothing in particular") + 1, "q2b": q2.index(k["behaviour"]) + 1}
    row = {"study": sid, "instrument": "1", "session": session,
           "order": {"baseline": order["baseline"], "clips": order["clips"]}, "answers": perfect,
           "delivery": {"autoplay": True, "keyboard": False, "duration_s": 120, "ui": "blindpanel@0.2.0"},
           "flags": [], "received_day": "2026-10-31"}
    data = tmp_path / "data"
    data.mkdir()
    (data / f"{sid}.jsonl").write_text(json.dumps(row) + "\n")
    r = subprocess.run(["node", str(BP), "export", str(d / "study.yaml"), "--store", "file", "--data", str(data), "--out", str(tmp_path / "exp")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    got = ratings.analyse({"R1": ratings.read_export(tmp_path / "exp" / "ratings.csv")}, key)
    assert sorted(got["laws"]) == sorted(law["id"] for law in fixture_laws()["laws"] if law["rated"])
    for law, v in got["laws"].items():
        assert v["clip"]["q1"]["k"] == v["clip"]["q2"]["k"] == v["clip"]["law"]["k"] == 1, law      # every clip scored a hit
        assert v["baseline"]["q1b"]["k"] == 0 and v["baseline"]["q2b"]["k"] == 1 and v["baseline"]["q2b"]["n"] == 1, law
    out = tmp_path / "ratings-out.json"
    assert ratings.main(["--key", str(work / "sealed" / "answer-key.json"), "--rater", f"R1={tmp_path / 'exp' / 'ratings.csv'}",
                         "--out", str(out)]) == 0
    assert json.loads(out.read_text())["n_raters"] == 1


# --- review fixes: guessable ids, banned terms, atomic seal, cue times, malformed input -----------------
def guessable(seed, codes, takes):
    """Codes recoverable from a human-readable id built from the takes x materials (the seed is public)."""
    mats = {"ink", "gold", "paper"} | {t["target_material"] for t in takes if isinstance(t.get("target_material"), str)}
    ids = {t["id"] for t in takes}
    laws = {f"{m}.{c}" for m in mats for c in ("water", "light", "pen", "breath", "note", "hand")}
    guesses = set(laws) | ids | mats
    for t in ids:
        for m in mats:
            for f in ("{t}-{m}", "{t}_{m}", "{t}{m}", "{m}-{t}", "{m}_{t}", "{t}.{m}", "{m}.{t}", "{t}-{m}-clip", "{t}-{m}-panel",
                      "c-{t}-{m}", "p-{t}-{m}", "b-{t}-{m}", "clip-{t}-{m}", "panel-{t}-{m}", "{t}-{m}.mp4", "{t}-{m}.png"):
                guesses.add(f.format(t=t, m=m))
    return sorted(g for g in guesses for kind in ("clip", "panel") if P.opaque_code(seed, kind, g) in codes)


def test_kit_ids_come_from_the_salt_so_no_code_is_guessable(built, work):
    key = json.loads((work / "sealed" / "answer-key.json").read_text())
    takes = json.loads(TAKES.read_text())
    codes = set(key["codes"]["clips"].values()) | set(key["codes"]["panels"].values())
    assert guessable(key["seed"], codes, takes) == []
    # the test has teeth: codes made from the human-readable refs would be found
    old = {P.opaque_code(key["seed"], k, ref) for ref in key["clips"] for k in ("clip", "panel")}
    assert len(guessable(key["seed"], old, takes)) >= len(key["clips"])
    for ref, kid in key["ids"].items():
        assert re.fullmatch(r"i[0-9a-f]{10}", kid) and kid == P.kit_id(key["salt"], ref)
        assert kid == "i" + hashlib.sha256(f"{key['salt']}:{ref}".encode()).hexdigest()[:10]
    st = json.loads((work / "out" / "studies" / "limn-r1" / "study.yaml").read_text().split("\n", 1)[1])
    assert {c["id"] for c in st["items"]["clips"]} == {p["id"] for p in st["items"]["panels"]} == set(key["ids"].values())
    assert {c["ref"] for c in st["items"]["clips"]} == set(key["clips"])      # refs stay local, in the unshipped study.yaml


def test_read_key_refuses_ids_not_derived_from_the_salt(work, tmp_path):
    d = sealed_copy(work, tmp_path)
    key = json.loads((d / "answer-key.json").read_text())
    key["ids"]["t03-ink"] = "t03-ink"
    key["codes"]["clips"]["t03-ink"] = P.opaque_code(key["seed"], "clip", "t03-ink")
    key["codes"]["panels"]["t03-ink"] = P.opaque_code(key["seed"], "panel", "t03-ink")
    (d / "answer-key.json").write_text(json.dumps(key))
    with pytest.raises(P.PrepareError, match="t03-ink.*not derived from the salt"):
        P.prepare(args(work, tmp_path / "o", d, "--no-blindpanel", *FAST))
    assert not (tmp_path / "o" / "media").exists()


def test_the_wording_check_catches_materials_and_model_ids_in_any_shape():
    laws = fixture_laws()
    strict = P.parse_banned("\n".join(P.banned_lines(laws, strict_materials=True)))
    for text in ("t01-ink", "inky", "ink-stained", "the Gold one", "paperwork", "a PAPER cut-out", "x-gold"):
        assert P.find_banned(text, strict), text
    for mid in P.MODELS:
        assert P.find_banned(f"clip from {mid} here", strict) and P.find_banned(mid.upper(), strict), mid
    assert not P.find_banned("They think about pinks", strict)
    dist = P.parse_banned("\n".join(P.banned_lines(laws)))
    for mid in P.MODELS:
        assert P.find_banned(f"x {mid} y", dist), mid
    assert not P.find_banned("var(--bp-ink) and var(--bp-paper)", dist)       # the kit's CSS passes the dist scan only
    assert P.find_banned("var(--bp-ink)", strict)
    assert {"aleph2", "kling_4", "seedance2_5", "gemini_omni_flash_1.1"} <= set(P.MODELS)
    text = "\n".join(P.banned_lines(laws))
    assert all(mid in text.splitlines() for mid in P.MODELS)                    # plain-substring lines


def test_a_q2_label_with_a_hyphenated_material_stops_the_build(work, tmp_path):
    laws = fixture_laws()
    laws["laws"][1]["label"] = "Ink-stained dance (fixture)"
    (work / "laws-hy.json").write_text(json.dumps(laws))
    P.seal(seal_args(work, tmp_path / "s", "laws-hy.json"))
    a = args(work, tmp_path / "o", tmp_path / "s", "--no-blindpanel", *FAST)
    a.laws = str(work / "laws-hy.json")
    with pytest.raises(P.PrepareError, match="banned entries"):
        P.prepare(a)


def test_seal_is_atomic(work, tmp_path, monkeypatch):
    s = tmp_path / "s"
    real, calls = P.os.replace, []

    def flaky(a, b):
        calls.append(b)
        if len(calls) == 2:
            raise OSError("disk full")
        return real(a, b)

    monkeypatch.setattr(P.os, "replace", flaky)
    with pytest.raises(OSError):
        P.seal(seal_args(work, s))
    assert not (s / "answer-key.json").exists() and not (s / "q2-options.json").exists()      # neither
    assert [x.name for x in s.iterdir()] == []                                               # and no temp files
    monkeypatch.setattr(P.os, "replace", real)
    P.seal(seal_args(work, s))
    before = {n: (s / n).read_bytes() for n in ("answer-key.json", "q2-options.json")}
    calls.clear()
    monkeypatch.setattr(P.os, "replace", flaky)
    with pytest.raises(OSError):
        P.seal(seal_args(work, s, "laws.json", "--force"))
    assert {n: (s / n).read_bytes() for n in before} == before                                # the old pair survives
    assert sorted(x.name for x in s.iterdir()) == sorted(before)


def test_a_cue_sheet_without_the_materials_own_event_is_an_error(work, tmp_path):
    sc = cue_sheet.assemble(take="t01", fps=30, n_frames=90, size=(640, 360), fires="water", target="gold",
                            events=[cue_sheet.make_event(t=1.0, t_end=1.5, cue="water", what="fixture", source="hand", evidence={})])
    path = cue_sheet.write_sheet(tmp_path / "c.json", sc)
    assert P.cue_time(path, "water", "gold") == pytest.approx(1.0)
    with pytest.raises(P.PrepareError, match="no water event aimed at ink"):
        P.cue_time(path, "water", "ink")                    # never falls back to another material's event
    with pytest.raises(P.PrepareError, match="no light event"):
        P.cue_time(path, "light", "gold")


def test_malformed_inputs_give_clean_errors(work, tmp_path):
    laws, takes = P.load_laws(work / "laws.json"), json.loads((work / "takes.json").read_text())
    shutil.copytree(work / "src", tmp_path / "src")
    doc = json.loads((work / "inputs.json").read_text())
    bad = json.loads(json.dumps(doc))
    del bad["entries"][2]["render"]
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    with pytest.raises(P.PrepareError, match="render"):
        P.load_inputs(tmp_path / "bad.json", takes, laws)
    bad = json.loads(json.dumps(doc))
    bad["entries"].append({"take": "t01"})                   # no material
    (tmp_path / "bad2.json").write_text(json.dumps(bad))
    with pytest.raises(P.PrepareError):
        P.load_inputs(tmp_path / "bad2.json", takes, laws)
    t2 = json.loads(json.dumps(takes))
    del next(t for t in t2 if t["id"] == "t03")["cue"]
    with pytest.raises(P.PrepareError, match="lacks .cue."):
        P.rated_items(t2, laws)
    assert P.main(["build", "--inputs", str(tmp_path / "bad.json"), "--laws", str(work / "laws.json"), "--takes", str(work / "takes.json"),
                   "--sealed", str(work / "sealed"), "--out", str(tmp_path / "o"), "--seconds", "1", "--no-blindpanel"]) == 1


def test_the_container_scan_lives_in_its_own_module():
    from rating import container
    assert P.scan_container is container.scan_container and P.C2PA_UUID == container.C2PA_UUID


# --- review finding 7 (call 135): the drawn Q2 order never follows the Q1 order ----------------------------------------------
def test_the_q2_order_never_lists_the_rated_labels_in_q1_order():
    full = fixture_laws()
    two = [next(l for l in full["laws"] if l["rated"] and l["cue"] == c) for c in ("water", "light")]
    laws = {**full, "laws": two}                    # two rated cues: a bare shuffle follows the Q1 order half the time
    seeds = [f"s{i}" for i in range(40)]
    assert any(P.follows_q1_order(_hash_order(laws, s), laws) for s in seeds)
    for s in seeds:
        drawn = P.draw_q2_options(laws, s)
        assert not P.follows_q1_order(drawn[:-2], laws) and drawn[-2:] == [P.NOTHING, P.CANT_TELL]
    assert P.draw_q2_options(laws, "s0") == P.draw_q2_options(laws, "s0")      # still drawn by the seed alone
    assert P.follows_q1_order(["Decoy one (fixture)", two[0]["label"], two[1]["label"]], laws)
    assert not P.follows_q1_order([two[1]["label"], two[0]["label"]], laws)


def _hash_order(laws, seed):
    import hashlib
    return sorted(P.q2_labels(laws), key=lambda s: hashlib.sha256(f"{seed}:q2order:{s}".encode()).hexdigest())


# --- Gate R review F5 (call 136): no default path to a blindpanel checkout ---------------------------------------------------
def test_the_blindpanel_cli_comes_only_from_the_flag_or_BLINDPANEL_CLI(built, work, tmp_path, monkeypatch):
    monkeypatch.delenv("BLINDPANEL_CLI", raising=False)
    assert not hasattr(P, "DEFAULT_BLINDPANEL")
    a = P.parse_args(["build", "--inputs", str(work / "inputs.json"), "--laws", str(work / "laws.json"),
                      "--takes", str(work / "takes.json"), "--out", str(tmp_path / "o"), "--sealed", str(work / "sealed"),
                      "--raters", "2", "--seconds", "2.0"])
    assert a.blindpanel is None
    with pytest.raises(P.PrepareError, match="BLINDPANEL_CLI"):
        P.prepare(a)
    assert not (tmp_path / "o" / "media").exists()
