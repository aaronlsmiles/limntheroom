"""seam/assemble.py (Phase 8): the gate, the masks and the lines job's output -> one p47-measure/1 file
per render, in the shape analysis/h_contact.py reads. Synthetic scene; the lines job runs for real
with a trivial line extractor (dark pixels), so its record has exactly the shape the registered job
writes."""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from analysis import h_contact
from blindkit import custody_chain
from seam import align, assemble, cells, lines_job, masks, pairs, regions

H, W, N = 180, 320, 40
CONTACT = range(14, 26)          # the creature touches the object here
M, KAPPA = 32, 0.5


def extract(frames):
    return [np.asarray(f)[..., 0] < 128 for f in frames]


def rect(y0, y1, x0, x1):
    m = np.zeros((H, W), bool)
    m[y0:y1, x0:x1] = True
    return m


class Scene:
    """40 frames of a ruled desk. The render redraws four lines on the left (1 px off, 4 px off while
    the creature touches the object), far outside the measured margin around the creature."""

    def __init__(self, tmp, render_id="t01-ink", missing_touched=3, prompt_frame=None):
        take = np.full((N, H, W, 3), 230, np.uint8)
        take[:, :, 8::16] = 60
        render = take.copy()
        for i in range(N):
            s = 4 if i in CONTACT else 1
            render[i, :, 8:64] = np.roll(take[i, :, 8:64], s, axis=1)
        self.render_id = render_id
        self.take, self.render = take, render
        self.t = np.arange(N) / 15
        self.home = rect(40, 60, 100, 120)
        self.touched = np.stack([rect(60, 110, 200, 240) if i >= missing_touched else np.zeros((H, W), bool)
                                 for i in range(N)])
        self.creature = np.stack([rect(70, 90, 176, 196) if i in CONTACT else rect(40, 60, 100, 120)
                                  for i in range(N)])
        if prompt_frame:
            self.creature[:prompt_frame] = False       # forward-only SAM: empty before the prompt frame
        self.hand = np.zeros((N, H, W), bool)
        self.gate_ok = [True] * N
        self.prompt_frame = prompt_frame
        self.valid = np.array(assemble.scored_frames(self.gate_ok, self.creature, start=prompt_frame), bool)
        self.R = assemble.region_series(self.creature, self.home, M, prompt_frame)
        self.tmp = Path(tmp)
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.seam = self.tmp / f"runs/seam/{render_id}.bin"

        def pair(path, rend):
            return pairs.write_pair(path, take=take, render=rend, valid=self.valid, R=self.R, t=self.t,
                                    creature=self.creature, homes={"ink": self.home},
                                    meta={"render": render_id, "m": M,
                                          "render_mask_digest": masks.mask_digest({"creature": self.creature})})
        self.pair = pair(self.tmp / f"{render_id}.pair.npz", render)
        self.null = pair(self.tmp / f"{render_id}.null.npz", np.roll(take, 1, axis=2))
        self.lines = lines_job.measure(self.pair, null=self.null, kappa=KAPPA, extract=extract, chamfer=None,
                                       seam_path=self.seam)
        self.gate = {"pass": True, "lag": 0, "rho": 0.8, "frames_ok": 1.0, "ok": list(self.gate_ok),
                     "reason": None}

    def assemble(self, **kw):
        a = dict(lines=self.lines, gate=self.gate, creature=self.creature, touched=self.touched,
                 hand_mask=self.hand, take_frames=self.take, home=self.home, R=self.R, m=M, kappa_keep=KAPPA,
                 kappa_source="kappa_render_p1", seam_root=self.tmp, prompt_frame=self.prompt_frame)
        a.update(kw)
        return assemble.assemble(self.render_id, **a)


@pytest.fixture(scope="module")
def scene(tmp_path_factory):
    return Scene(tmp_path_factory.mktemp("scene"))


# ---- the shape -------------------------------------------------------------------------------------------
def test_assembled_render_has_the_registered_shape(scene):
    rec = scene.assemble()
    assert rec["schema"] == "p47-measure/1" and rec["render"] == "t01-ink"
    assert set(rec["align"]) >= {"pass", "lag", "rho", "frames_ok"}
    assert rec["align"] == {"pass": True, "lag": 0, "rho": 0.8, "frames_ok": 1.0, "reason": None, "lag_source": None,
                            "lag_applicable": True, "lag_reason": None, "duration_ok": True, "lag_energy_mean": None}
    p = rec["params"]
    for k in ("m", "d", "tau", "cell", "fps", "kappa_keep", "kappa_source", "versions"):
        assert k in p, k
    assert (p["m"], p["d"], p["tau"], p["cell"], p["fps"]) == (32, 8, 2, 32, 15)
    assert p["kappa_keep"] == KAPPA and p["kappa_source"] == "kappa_render_p1"
    assert {"numpy", "opencv-python", "av", "ffmpeg"} <= set(p["versions"])
    assert p["lines"]["inkstab_version"] == scene.lines.get("inkstab_version", p["lines"]["inkstab_version"])
    s = rec["series"]
    for k in ("t", "D", "D0", "contact", "eligible", "hand", "ocr_cer", "motion", "redrawn_object", "redrawn_rest"):
        assert len(s[k]) == N, k
    assert rec["seam"] == {"file": "runs/seam/t01-ink.bin", "cols": 10, "rows": 6, "bits": 2, "frames": N}
    assert set(rec["summary"]) >= {"n_frames", "n_scored", "n_eligible", "n_contact", "r", "D", "D0", "cells"}


def test_the_record_is_strict_json(scene):
    rec = scene.assemble()
    text = json.dumps(rec, allow_nan=False, sort_keys=True)
    assert json.loads(text) == rec


def test_assembled_renders_pass_h_contact_validation(scene, tmp_path):
    recs = []
    for k, rid in enumerate(("t01-ink", "t02-ink", "t03-ink", "t05-ink", "t06-ink")):   # t04-ink has no touched object
        sc = scene if k == 0 else Scene(tmp_path / f"s{k}", render_id=rid)
        recs.append(sc.assemble())
    out = h_contact.run(recs)
    assert out["primary"]["n_testable"] == 5
    rows = [r for r in out["per_render"] if r["render"] in out["renders"]]
    assert len(rows) == 5 and all(r["testable"] and r["r"] > 1.25 for r in rows), out["per_render"]
    assert out["primary"]["verdict"] == "supported"
    # and through files, the way the registered run reads them
    files = []
    for r in recs:
        files.append(assemble.write_measure(r, tmp_path / f"runs/measure/{r['render']}.json"))
    assert h_contact.main([*map(str, files), "--out", str(tmp_path / "h.json")]) == 0


def test_series_follow_the_registered_definitions(scene):
    rec = scene.assemble()
    s = rec["series"]
    D = s["D"]
    assert all(d is not None and d >= 0 for d in D)
    assert s["t"] == pytest.approx(list(scene.t))
    for i in range(N):
        want = regions.contact(scene.creature[i], scene.touched[i], scene.hand[i])
        assert s["contact"][i] == want, i
        assert s["eligible"][i] == (bool(scene.touched[i].any()) and D[i] is not None), i
    assert [i for i, c in enumerate(s["contact"]) if c] == list(CONTACT)
    assert s["eligible"][:3] == [False] * 3 and all(s["eligible"][3:])          # the object enters at frame 3
    assert sum(D[i] for i in CONTACT) / len(CONTACT) > 2 * np.mean([D[i] for i in range(N) if i not in CONTACT])


def test_d0_is_the_codec_nulls_series(scene):
    rec = scene.assemble()
    assert rec["series"]["D0"] == pytest.approx(scene.lines["D0"])


def test_motion_is_the_takes_energy_in_r(scene):
    rec = scene.assemble()
    m = rec["series"]["motion"]
    assert m[0] is None
    want = align.motion_energy(scene.take, scene.R)
    assert m[1:] == pytest.approx(list(want))


# ---- refusals ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kw", [
    {"touched": "short"}, {"creature": "short"}, {"hand_mask": "short"}, {"take_frames": "short"}, {"R": "short"},
    {"hand_drift": [0.1] * (N - 1)}, {"ocr_cer": [None] * (N + 1)},
])
def test_mismatched_lengths_are_refused(scene, kw):
    base = {"touched": scene.touched, "creature": scene.creature, "hand_mask": scene.hand,
            "take_frames": scene.take, "R": scene.R}
    kw = {k: (v if v != "short" else base[k][:-1]) for k, v in kw.items()}
    with pytest.raises(ValueError, match="length|frames"):
        scene.assemble(**kw)


def test_mismatched_gate_or_lines_series_are_refused(scene):
    with pytest.raises(ValueError, match="length|frames"):
        scene.assemble(gate={**scene.gate, "ok": scene.gate["ok"][:-1]})
    bad = {**scene.lines, "D": scene.lines["D"][:-1]}
    with pytest.raises(ValueError, match="length|frames"):
        scene.assemble(lines=bad)
    bad = {**scene.lines, "D0": scene.lines["D0"] + [None]}
    with pytest.raises(ValueError, match="length|frames"):
        scene.assemble(lines=bad)


def test_a_variant_of_the_wrong_length_is_refused(scene):
    bad = {**scene.lines, "D": scene.lines["D"][:-2], "valid": scene.lines["valid"][:-2], "t": scene.lines["t"][:-2]}
    with pytest.raises(ValueError, match="length|frames"):
        scene.assemble(extra_lines={"m48": bad})


def test_a_nan_d_is_carried_as_none(scene):
    lines = json.loads(json.dumps(scene.lines))              # a deep copy, as a file would give it
    lines["D"][10] = float("nan")
    lines["D"][11] = float("inf")
    rec = scene.assemble(lines=lines)
    assert rec["series"]["D"][10] is None and rec["series"]["D"][11] is None
    assert rec["series"]["eligible"][10] is False and rec["series"]["eligible"][11] is False
    assert rec["series"]["D"][12] is not None
    json.dumps(rec, allow_nan=False)
    assert rec["summary"]["n_scored"] == N - 2


def test_d_must_be_none_on_frames_that_were_not_scored(scene):
    lines = json.loads(json.dumps(scene.lines))
    lines["valid"][5] = False                                 # the job says unscored, but D is a number
    gate = {**scene.gate, "ok": [i != 5 for i in range(N)], "frames_ok": 39 / 40}
    with pytest.raises(ValueError, match="valid|scored"):
        scene.assemble(lines=lines, gate=gate)


def test_the_jobs_valid_must_equal_gate_and_mask_quality(scene):
    gate = {**scene.gate, "ok": [i != 7 for i in range(N)], "frames_ok": 39 / 40}  # the gate says frame 7 failed; the job scored it
    with pytest.raises(ValueError, match="valid|scored"):
        scene.assemble(gate=gate)


def test_scored_frames_is_gate_and_mask_quality():
    creature = np.zeros((6, 20, 20), bool)
    creature[1:5, 5:10, 5:10] = True                          # empty at 0 and 5, steady 1-4
    creature[3, 5:10, 5:12] = True                            # +40 %: fine
    ok = [True, True, True, False, True, True]
    got = assemble.scored_frames(ok, creature)
    assert got == [False, False, True, False, True, False]
    # a prompt frame: earlier frames (the drawing at home) count as scored if the gate passed them
    got = assemble.scored_frames(ok, creature, start=1)
    assert got == [True, True, True, False, True, False]
    with pytest.raises(ValueError, match="length|frames"):
        assemble.scored_frames(ok[:-1], creature)


def test_a_creature_that_appears_at_frame_20_is_at_home_before_it(tmp_path):
    """Frames before the render mask's prompt frame are the drawing at home: valid, and A(t) is the dilated home."""
    sc = Scene(tmp_path / "late", render_id="t03-ink", prompt_frame=20)
    home_only = ~regions.dilate(sc.home, M)
    assert sc.creature[:20].sum() == 0
    assert all(np.array_equal(sc.R[i], home_only) for i in range(20))
    assert not np.array_equal(sc.R[20], home_only) or not sc.creature[20].any()
    assert sc.valid[:20].all() and sc.lines["valid"][:20] == [True] * 20
    rec = sc.assemble(prompt_frame=20)
    assert rec["params"]["prompt_frame"] == 20
    assert all(d is not None for d in rec["series"]["D"][:20])
    assert not any(rec["series"]["contact"][:20])
    assert assemble.region_series(sc.creature, sc.home, M, 20)[5].tolist() == home_only.tolist()
    # without the prompt frame the same masks are scored as empty-mask failures, and the job's valid disagrees
    with pytest.raises(ValueError, match="valid|scored"):
        sc.assemble(prompt_frame=None)
    # a region built with another margin is refused
    with pytest.raises(ValueError, match="R differs"):
        sc.assemble(prompt_frame=20, R=assemble.region_series(sc.creature, sc.home, 48, 20))


@pytest.mark.parametrize("kw,match", [
    ({"kappa_source": "guess"}, "kappa_source"),
    ({"kappa_keep": 0.4}, "kappa"),
    ({"kappa_keep": float("nan")}, "kappa"),
    ({"kappa_keep": 0.0}, "kappa"),
    ({"m": 40}, "m"),
])
def test_kappa_m_and_source_are_checked(scene, kw, match):
    with pytest.raises(ValueError, match=match):
        scene.assemble(**kw)


def test_a_lines_run_without_kappa_is_refused(scene):
    lines = {**scene.lines, "params": {**scene.lines["params"], "kappa": None}, "seam": None}
    with pytest.raises(ValueError, match="kappa|seam"):
        scene.assemble(lines=lines)


def test_a_record_for_another_render_or_margin_is_refused(scene):
    lines = {**scene.lines, "meta": {"render": "t09-ink", "m": M}}
    with pytest.raises(ValueError, match="render"):
        scene.assemble(lines=lines)
    lines = {**scene.lines, "meta": {"render": "t01-ink", "m": 48}}
    with pytest.raises(ValueError, match="m"):
        scene.assemble(lines=lines)


def test_the_seam_file_must_exist_and_have_the_right_size(scene, tmp_path):
    with pytest.raises(ValueError, match="seam"):
        scene.assemble(seam_root=tmp_path / "elsewhere")                 # the job's file lies outside that root
    with pytest.raises(ValueError, match="seam"):
        scene.assemble(seam_root=tmp_path, seam_file="runs/seam/t01-ink.bin")      # nothing there
    short = tmp_path / "runs/seam/t01-ink.bin"
    short.parent.mkdir(parents=True)
    short.write_bytes(scene.seam.read_bytes()[:-3])
    with pytest.raises(ValueError, match="seam"):
        scene.assemble(seam_root=tmp_path, seam_file="runs/seam/t01-ink.bin")
    ok = scene.assemble(seam_root=tmp_path, seam_file="runs/seam/t01-ink.bin", check_files=False)
    assert ok["seam"]["file"] == "runs/seam/t01-ink.bin"


def test_a_malformed_record_fails_validation(scene):
    rec = scene.assemble()
    assemble.validate_measure(rec)
    for mutate, match in [
        (lambda r: r.update(schema="p47-measure/2"), "schema"),
        (lambda r: r["series"].update(D=r["series"]["D"][:-1]), "length"),
        (lambda r: r["params"].pop("kappa_source"), "kappa_source"),
        (lambda r: r["params"].pop("versions"), "versions"),
        (lambda r: r["align"].pop("frames_ok"), "frames_ok"),
        (lambda r: r["seam"].pop("file"), "seam"),
        (lambda r: r["series"]["D"].__setitem__(3, float("nan")), "D"),
        (lambda r: r["series"]["eligible"].__setitem__(0, 1), "eligible"),
    ]:
        bad = json.loads(json.dumps(rec))
        mutate(bad)
        with pytest.raises(ValueError, match=match):
            assemble.validate_measure(bad)


# ---- the variants, the invariants, the cells ------------------------------------------------------------------
def test_variants_from_the_masks(scene):
    rec = scene.assemble()
    v = rec["variants"]
    assert {"d4", "d16", "proximity24"} <= set(v)
    c8 = rec["series"]["contact"]
    for name, d in (("d4", 4), ("d16", 16), ("proximity24", 24)):
        want = [regions.contact(scene.creature[i], scene.touched[i], scene.hand[i], d) for i in range(N)]
        assert v[name]["contact"] == want, name
        assert v[name]["D"] == rec["series"]["D"] and v[name]["eligible"] == rec["series"]["eligible"]
    assert sum(v["proximity24"]["contact"]) >= sum(v["d16"]["contact"]) >= sum(c8) >= sum(v["d4"]["contact"])


def test_extra_lines_runs_become_variants(scene, tmp_path):
    other = Scene(tmp_path / "m48", render_id="t01-ink")
    lines = json.loads(json.dumps(other.lines))
    lines["D"] = [None if d is None else d * 2 for d in lines["D"]]
    rec = scene.assemble(extra_lines={"interior_excluded": lines})
    v = rec["variants"]["interior_excluded"]
    assert v["D"] == pytest.approx([d * 2 for d in rec["series"]["D"]])
    assert v["contact"] == rec["series"]["contact"]
    out = h_contact.run([rec])
    assert "interior_excluded" in out["secondary"]["variants"]


def test_no_touched_object_means_no_eligible_frames(scene):
    breath = Scene(scene.tmp / "breath", render_id="t04-ink")            # the one take with no touched object
    rec = breath.assemble(touched=None, hand_mask=None)
    s = rec["series"]
    assert not any(s["eligible"]) and not any(s["contact"])
    assert rec["summary"]["n_eligible"] == 0 and rec["summary"]["r"] is None
    assert h_contact.run([rec])["primary"]["verdict"] == "not testable"
    assert s["redrawn_object"] == [None] * N


def test_hand_contact_counts(scene):
    hand = np.zeros((N, H, W), bool)
    hand[:, 70:90, 200:220] = True                            # the hand is where the object was, from frame 0
    far = np.zeros((N, H, W), bool)
    far[:, 150:170, 10:30] = True                             # and the touched object is far from the creature
    rec = scene.assemble(hand_mask=hand, touched=far)
    assert [i for i, c in enumerate(rec["series"]["contact"]) if c] == list(CONTACT)
    assert not any(scene.assemble(hand_mask=None, touched=far)["series"]["contact"])   # the hand made the contact
    assert all(rec["series"]["eligible"])                    # eligibility is the touched object's, not the hand's


def test_hand_and_ocr_series_are_carried(scene):
    hd = [None if i % 3 else 0.05 for i in range(N)]
    ocr = [None if i % 3 else 0.2 for i in range(N)]
    rec = scene.assemble(hand_drift=hd, ocr_cer=ocr)
    assert rec["series"]["hand"] == hd and rec["series"]["ocr_cer"] == ocr
    out = h_contact.run([rec])
    assert out["secondary"]["descriptive"]["hand"]["t01-ink"]["noncontact_mean"] == pytest.approx(0.05)
    plain = scene.assemble()
    assert plain["series"]["hand"] == [None] * N and plain["series"]["ocr_cer"] == [None] * N


def test_redrawn_share_inside_the_touched_object_against_the_rest(scene):
    # a render that redraws the cells inside the object (a different texture there) but keeps the rest
    sc = Scene(scene.tmp / "redraw", render_id="t02-ink")
    render = sc.take.copy()
    render[:, 60:110, 200:256, 0] = 230                       # the take's ruled lines vanish inside the object
    sc.render = render
    pairs.write_pair(sc.pair, take=sc.take, render=render, valid=sc.valid, R=sc.R, t=sc.t, creature=sc.creature,
                     homes={"ink": sc.home}, meta={"render": "t02-ink", "m": M})
    lines = lines_job.measure(sc.pair, null=sc.null, kappa=KAPPA, extract=extract, chamfer=None, seam_path=sc.seam)
    rec = sc.assemble(lines=lines)
    ro, rr = rec["series"]["redrawn_object"], rec["series"]["redrawn_rest"]
    assert ro[10] == pytest.approx(1.0) and rr[10] == pytest.approx(0.0)
    assert ro[0] is None or ro[0] == pytest.approx(1.0)       # before the object enters there are no object cells


def test_summary_counts(scene):
    s = scene.assemble()["summary"]
    assert s["n_frames"] == N and s["n_scored"] == N
    assert s["n_eligible"] == N - 3 and s["n_contact"] == len(CONTACT)
    assert s["n_eligible_contact"] == len(CONTACT) and s["n_eligible_noncontact"] == N - 3 - len(CONTACT)
    assert s["r"] and s["r"] > 1.25
    assert s["D"]["median"] is not None and s["cells"]["kept"] + s["cells"]["redrawn"] + s["cells"]["none"] > 0
    json.dumps(s, allow_nan=False)


# ---- writing ----------------------------------------------------------------------------------------------------
def test_write_is_deterministic_sorted_json(scene, tmp_path):
    rec = scene.assemble()
    a = assemble.write_measure(rec, tmp_path / "a/t01-ink.json")
    b = assemble.write_measure(scene.assemble(), tmp_path / "b/t01-ink.json")
    assert a.read_bytes() == b.read_bytes()
    text = a.read_text()
    assert text.endswith("\n") and json.loads(text) == rec
    assert "NaN" not in text and "Infinity" not in text


def test_meta_for_h_contact(scene):
    meta = assemble.meta_for([scene.assemble()], {"t01-ink": "ink"})
    assert meta == {"t01-ink": {"material": "ink"}}


def test_the_seam_path_is_relative_even_if_the_job_wrote_an_absolute_one(scene):
    assert scene.lines["seam"]["file"] == str(scene.seam)    # absolute, as lines_job writes it
    assert scene.assemble()["seam"]["file"] == "runs/seam/t01-ink.bin"
    assert scene.assemble(seam_file="runs/seam/other.bin", check_files=False)["seam"]["file"] == "runs/seam/other.bin"


# ---- the command line ---------------------------------------------------------------------------------------------
def custody_args(sc, tmp_path, frame=0):
    """A committed custody for the scene's render, and a copy of its pair carrying the custody's meta."""
    from seam import blind
    c = custody_chain(tmp_path / "custody", sc.render_id, creature=sc.creature, frame=frame)
    P = pairs.read_pair(sc.pair)
    pp = pairs.write_pair(tmp_path / f"{sc.render_id}.custody.pair.npz", take=P["take"], render=P["render"],
                          valid=P["valid"], R=P["R"], t=P["t"], creature=P["creature"], homes=P["homes"],
                          meta={**P["meta"], **c["meta"], "gate": {"pass": True, "sha256": blind.sha256_json(sc.gate)}})
    return ["--prompts", str(c["prompts"]), "--pair", str(pp)]


def take_masks(tmp_path, objects, take="t01", name=None):
    """A p47-masks/1 file with the given objects (the take id as masks.save_masks records it)."""
    mp = tmp_path / (name or f"take-masks-{take}-{'-'.join(sorted(objects))}.npz")
    masks.save_masks(mp, objects, take=take)
    return str(mp)


def test_cli_assembles_from_files(scene, tmp_path):
    lines_p = tmp_path / "lines.json"
    lines_p.write_text(json.dumps(scene.lines))
    gate_p = tmp_path / "gate.json"
    gate_p.write_text(json.dumps(scene.gate))
    mp = tmp_path / "take-masks.npz"
    masks.save_masks(mp, {"glass": scene.touched, "hand": scene.hand}, take="t01")
    hd = tmp_path / "hand.json"
    hd.write_text(json.dumps([None] * N))
    out = tmp_path / "runs/measure/t01-ink.json"
    rc = assemble.main(["--render", "t01-ink", "--pair", str(scene.pair), "--lines", str(lines_p), "--gate", str(gate_p),
                        "--take-masks", str(mp), "--touched", "glass", "--hand", "hand", "--m", "32",
                        *custody_args(scene, tmp_path), "--kappa", "0.5", "--kappa-source", "kappa_render_p1",
                        "--hand-drift", str(hd), "--seam-root", str(scene.tmp), "--out", str(out)])
    assert rc == 0
    rec = json.loads(out.read_text())
    assert rec["series"]["contact"] == scene.assemble()["series"]["contact"]
    assemble.validate_measure(rec)


def test_cli_refuses_and_exits_1(scene, tmp_path, capsys):
    lines_p = tmp_path / "lines.json"
    lines_p.write_text(json.dumps(scene.lines))
    gate_p = tmp_path / "gate.json"
    gate_p.write_text(json.dumps(scene.gate))
    rc = assemble.main(["--render", "t01-ink", "--pair", str(scene.pair), "--lines", str(lines_p), "--gate", str(gate_p),
                        "--take-masks", take_masks(tmp_path, {"glass": scene.touched}),
                        "--m", "32", *custody_args(scene, tmp_path), "--kappa", "0.4", "--kappa-source", "kappa_codec",
                        "--seam-root", str(scene.tmp),
                        "--out", str(tmp_path / "x.json")])
    assert rc == 1 and "kappa" in capsys.readouterr().err
    assert not (tmp_path / "x.json").exists()


def test_cli_reads_the_prompt_frame_from_the_prompt_file(tmp_path):
    sc = Scene(tmp_path / "late", render_id="t03-ink", prompt_frame=20)
    lines_p, gate_p = tmp_path / "l.json", tmp_path / "g.json"
    lines_p.write_text(json.dumps(sc.lines))
    gate_p.write_text(json.dumps(sc.gate))
    out = tmp_path / "m.json"
    rc = assemble.main(["--render", "t03-ink", "--pair", str(sc.pair), "--lines", str(lines_p), "--gate", str(gate_p),
                        "--take-masks", take_masks(tmp_path, {"pen": sc.touched}, take="t03c"),
                        "--m", "32", "--kappa", "0.5", "--kappa-source", "kappa_codec", *custody_args(sc, tmp_path, 20),
                        "--seam-root", str(sc.tmp), "--out", str(out)])
    assert rc == 0 and json.loads(out.read_text())["params"]["prompt_frame"] == 20


# ---- the gate is cross-checked (review fix 1) ----------------------------------------------------------------------
def _gate(scene, **kw):
    return {**scene.gate, **kw}


@pytest.mark.parametrize("kw,match", [
    # a hand-edited pass: true over a gate that failed its own 90 % rule
    ({"pass": True, "ok": [i < 30 for i in range(N)], "frames_ok": 0.75, "reason": "fewer than 90 % of frames pass"}, "valid|pass"),
    ({"pass": True, "lag": 3, "reason": "lag check failed"}, "pass"),
    ({"pass": True, "duration_ok": False, "reason": "render shorter than the analysis span (duration)"}, "pass"),
    ({"pass": True, "rho": None, "reason": "rho undefined: no round-trip fit"}, "pass"),
    ({"pass": False}, "pass"),                                    # failed on paper, but nothing says why
    ({"pass": True, "reason": "lag check failed"}, "pass|reason"),
    ({"frames_ok": 0.5}, "frames_ok"),
    ({"frames_ok": 1.0, "ok": [i != 7 for i in range(N)]}, "frames_ok"),
])
def test_a_gate_that_contradicts_itself_is_refused(scene, kw, match):
    with pytest.raises(ValueError, match=match):
        scene.assemble(gate=_gate(scene, **kw))


def test_a_failed_gate_is_accepted_when_it_is_consistent(tmp_path):
    sc = Scene(tmp_path / "bad", render_id="t05-ink")
    ok = [i >= 8 for i in range(N)]                                # 8 of 40 frames fail: 80 % < 90 %
    sc.gate = {**sc.gate, "ok": ok, "pass": False, "frames_ok": 0.8, "reason": "fewer than 90 % of frames pass"}
    sc.valid = np.array(assemble.scored_frames(ok, sc.creature), bool)
    pairs.write_pair(sc.pair, take=sc.take, render=sc.render, valid=sc.valid, R=sc.R, t=sc.t, creature=sc.creature,
                     homes={"ink": sc.home}, meta={"render": "t05-ink", "m": M})
    sc.lines = lines_job.measure(sc.pair, null=sc.null, kappa=KAPPA, extract=extract, chamfer=None, seam_path=sc.seam)
    rec = sc.assemble()
    assert rec["align"]["pass"] is False and rec["align"]["frames_ok"] == 0.8
    out = h_contact.run([rec])
    [row] = [r for r in out["per_render"] if r["render"] == "t05-ink"]
    assert row["aligned"] is False and row["reason"] == "not aligned"


def test_the_lag_basis_is_carried_for_a_take_whose_lag_is_not_applicable(scene):
    gate = _gate(scene, lag=None, lag_source="hands_props", lag_applicable=False,
                 lag_reason="not applicable: motion energy below the floor", duration_ok=True, lag_energy_mean=0.02)
    rec = scene.assemble(gate=gate)                                # passes on duration and the spatial test alone
    a = rec["align"]
    assert a["pass"] is True and a["lag"] is None and a["lag_applicable"] is False
    assert a["lag_source"] == "hands_props" and a["lag_reason"].startswith("not applicable")
    assert a["duration_ok"] is True and a["lag_energy_mean"] == pytest.approx(0.02)
    # but an applicable lag of 3 frames cannot pass
    with pytest.raises(ValueError, match="pass"):
        scene.assemble(gate=_gate(scene, lag=3, lag_applicable=True))
    # and a gate from align.gate() itself is always consistent
    from seam import align as al
    g = al.gate([al.Fit(M=np.eye(2, 3), scale=1.0, residual=0.1, n_matches=50, n_inliers=40)] * N, 0.8, lag=0)
    assert scene.assemble(gate=g)["align"]["lag_applicable"] is True


# ---- the minor fixes ---------------------------------------------------------------------------------------------------
def test_cli_has_no_manual_prompt_frame_and_needs_the_custody(scene, tmp_path, capsys):
    lines_p, gate_p = tmp_path / "l.json", tmp_path / "g.json"
    lines_p.write_text(json.dumps(scene.lines))
    gate_p.write_text(json.dumps(scene.gate))
    base = ["--render", "t01-ink", "--pair", str(scene.pair), "--lines", str(lines_p), "--gate", str(gate_p), "--m", "32",
            "--kappa", "0.5", "--kappa-source", "kappa_codec", "--seam-root", str(scene.tmp),
            "--take-masks", take_masks(tmp_path, {"glass": scene.touched, "hand": scene.hand})]
    with pytest.raises(SystemExit):
        assemble.main([*base, "--prompt-frame", "0", "--out", str(tmp_path / "a.json")])
    capsys.readouterr()
    pr = tmp_path / "hand-made.json"
    pr.write_text(json.dumps({"objects": {"creature": [{"frame": 0, "x": 186, "y": 80, "positive": True}]}}))
    assert assemble.main([*base, "--prompts", str(pr), "--out", str(tmp_path / "b.json")]) == 1
    assert "refuse" in capsys.readouterr().err and not (tmp_path / "b.json").exists()
    for flag in ("--pick-log", "--points-log"):
        with pytest.raises(SystemExit):
            assemble.main([*base, "--prompts", str(pr), flag, str(tmp_path), "--out", str(tmp_path / "b.json")])
    capsys.readouterr()
    c = custody_args(scene, tmp_path)
    assert assemble.main([*base, *c, "--out", str(tmp_path / "c.json")]) == 0
    assert json.loads((tmp_path / "c.json").read_text())["params"]["prompt_frame"] == 0


def test_cli_refuses_a_pair_whose_creature_mask_is_not_the_logged_track(scene, tmp_path, capsys):
    lines_p, gate_p = tmp_path / "l.json", tmp_path / "g.json"
    lines_p.write_text(json.dumps(scene.lines))
    gate_p.write_text(json.dumps(scene.gate))
    other = scene.creature.copy()
    other[5, 0, 0] = True
    c = custody_chain(tmp_path / "custody", "t01-ink", creature=other, frame=0)
    rc = assemble.main(["--render", "t01-ink", "--pair", str(scene.pair), "--lines", str(lines_p), "--gate", str(gate_p),
                        "--m", "32", "--kappa", "0.5", "--kappa-source", "kappa_codec", "--seam-root", str(scene.tmp),
                        "--prompts", str(c["prompts"]), "--out", str(tmp_path / "x.json")])
    assert rc == 1 and "logged final track" in capsys.readouterr().err


def test_extra_lines_are_checked_against_the_primary_run(scene):
    def variant(**kw):
        rec = json.loads(json.dumps(scene.lines))
        for k, v in kw.items():
            if k == "kappa":
                rec["params"]["kappa"] = v
            else:
                rec["meta"] = {**rec["meta"], k: v}
        return rec
    scene.assemble(extra_lines={"interior_excluded": variant()})                  # same render, margin and kappa
    scene.assemble(extra_lines={"m48": variant(m=48), "m64": variant(m=64)})      # a margin variant names its margin
    for name, rec, match in [
        ("interior_excluded", variant(render="t09-ink"), "render"),
        ("interior_excluded", variant(kappa=0.4), "kappa"),
        ("interior_excluded", variant(m=48), "margin|m"),          # not a margin variant, so m must equal the primary
        ("m48", variant(m=64), "margin|m"),                          # named m48 but run at 64
        ("m32", variant(m=32), "margin|m"),                          # the primary's own margin is not a variant
    ]:
        with pytest.raises(ValueError, match=match):
            scene.assemble(extra_lines={name: rec})


def test_cli_refuses_a_gate_file_other_than_the_pairs(scene, tmp_path, capsys):
    lines_p, gate_p = tmp_path / "l.json", tmp_path / "g.json"
    lines_p.write_text(json.dumps(scene.lines))
    gate_p.write_text(json.dumps({**scene.gate, "rho": 0.9}))          # consistent, but not the one the pair was built under
    rc = assemble.main(["--render", "t01-ink", "--pair", str(scene.pair), "--lines", str(lines_p), "--gate", str(gate_p),
                        "--m", "32", "--kappa", "0.5", "--kappa-source", "kappa_codec", "--seam-root", str(scene.tmp),
                        *custody_args(scene, tmp_path), "--out", str(tmp_path / "x.json")])
    assert rc == 1 and "not the gate the pair was built under" in capsys.readouterr().err


def test_r_is_checked_with_the_pairs_warp_cover(scene):
    """The pair's R(t) leaves out the pixels the warp did not cover (call 126); the assembler rebuilds it with them."""
    cover = np.ones((N, H, W), bool)
    cover[:, :, W - 6:] = False
    R = assemble.region_series(scene.creature, scene.home, M, scene.prompt_frame, cover)
    assert not R[:, :, W - 6:].any() and np.array_equal(R[:, :, :W - 6], scene.R[:, :, :W - 6])
    assert scene.assemble(R=R, cover=cover)["render"] == scene.render_id
    with pytest.raises(ValueError, match="warp cover"):
        scene.assemble(R=R)


# ---- the touched object and the hand come from capture/takes.json (review S8) ----------------------------------------
REGISTERED_MASKS = {
    "t01-gold": "glass", "t01-ink": "glass", "t01-paper": "glass", "t02-ink": "standing_object", "t03-ink": "pen",
    "t04-ink": None, "t05-ink": "note", "t06-ink": "hand",
}


def test_registered_masks_are_read_from_takes_json():
    rows = json.loads((assemble.REPO / "capture" / "takes.json").read_text())
    for r in rows:
        if r.get("rated"):
            rid = f"{r['id']}-{r['target_material']}"
            got = assemble.registered_masks(rid)
            assert got == {"take": r["id"], "material": r["target_material"], "touched": r["paste"]["touched_mask"],
                           "hand": None if r["paste"]["touched_mask"] is None else "hand"}, rid
    assert {rid: assemble.registered_masks(rid)["touched"] for rid in REGISTERED_MASKS} == REGISTERED_MASKS
    assert sorted(REGISTERED_MASKS) == list(h_contact.REGISTERED)


@pytest.mark.parametrize("rid,match", [("t07-ink", "curtain call"), ("t07", "curtain call"), ("t09-ink", "registered"),
                                       ("t02-gold", "registered"), ("t01ink", "registered")])
def test_registered_masks_refuse_other_renders(rid, match):
    with pytest.raises(ValueError, match=match):
        assemble.registered_masks(rid)


def test_the_library_refuses_masks_that_contradict_the_registration(scene):
    with pytest.raises(ValueError, match="touched"):
        scene.assemble(touched=None)                               # t01-ink registers the glass
    breath = Scene(scene.tmp / "breath-lib", render_id="t04-ink")
    with pytest.raises(ValueError, match="touched"):
        breath.assemble()                                          # the breath take has no touched object
    with pytest.raises(ValueError, match="hand"):
        breath.assemble(touched=None, hand_mask=breath.hand)       # nor a hand
    assert not any(breath.assemble(touched=None, hand_mask=None)["series"]["eligible"])
    with pytest.raises(ValueError, match="registered"):
        assemble.assemble("t09-ink", lines=scene.lines, gate=scene.gate, creature=scene.creature, touched=scene.touched,
                          home=scene.home, m=M, kappa_keep=KAPPA, kappa_source="kappa_codec", seam_root=scene.tmp)


_CUSTODY = {}


def _cli(scene, tmp_path, *extra, render=None, custody=True):
    """assemble.main on the scene's files; the custody is built once per scene and test (a render's ledgers close)."""
    render = render or scene.render_id
    lines_p, gate_p = tmp_path / "l.json", tmp_path / "g.json"
    lines_p.write_text(json.dumps(scene.lines))
    gate_p.write_text(json.dumps(scene.gate))
    out = tmp_path / f"out{len(list(tmp_path.glob('out*.json')))}.json"
    if custody:
        key = (scene.render_id, str(tmp_path))
        if key not in _CUSTODY:
            _CUSTODY[key] = custody_args(scene, tmp_path)
        cust = _CUSTODY[key]
    else:
        cust = ["--prompts", str(tmp_path / "none.json")]
    argv = ["--render", render, "--pair", str(scene.pair), "--lines", str(lines_p), "--gate", str(gate_p), "--m", "32",
            "--kappa", "0.5", "--kappa-source", "kappa_codec", "--seam-root", str(scene.tmp), "--out", str(out),
            *cust, *extra]
    return assemble.main(argv), out


@pytest.mark.parametrize("flags,match", [
    (["--touched", "torch"], "glass"),                 # t01's touched object is the glass, not the torch
    (["--touched", "hand"], "glass"),
    (["--hand", "pen"], "hand"),
])
def test_cli_refuses_a_flag_that_contradicts_takes_json(scene, tmp_path, capsys, flags, match):
    mp = take_masks(tmp_path, {"glass": scene.touched, "hand": scene.hand, "torch": scene.touched, "pen": scene.touched})
    rc, out = _cli(scene, tmp_path, "--take-masks", mp, *flags)
    err = capsys.readouterr().err
    assert rc == 1 and "takes.json" in err and match in err and not out.exists()


def test_cli_reads_the_touched_object_and_the_hand_without_flags(scene, tmp_path):
    hand = np.zeros((N, H, W), bool)
    hand[:5, 40:60, 100:120] = True                    # the hand over the creature's home in the first five frames
    mp = take_masks(tmp_path, {"glass": scene.touched, "hand": hand, "torch": np.zeros_like(hand)})
    rc, out = _cli(scene, tmp_path, "--take-masks", mp)
    assert rc == 0
    rec = json.loads(out.read_text())
    want = scene.assemble(hand_mask=hand)["series"]
    assert rec["series"]["contact"] == want["contact"] and rec["series"]["eligible"] == want["eligible"]
    assert rec["series"]["contact"][:5] == [True] * 5            # the hand applies without --hand
    rc2, out2 = _cli(scene, tmp_path, "--take-masks", mp, "--touched", "glass", "--hand", "hand")   # agreeing flags
    assert rc2 == 0 and json.loads(out2.read_text())["series"] == rec["series"]


@pytest.mark.parametrize("objects,take,match", [
    (None, None, "take-masks"),                                   # no take masks for a take with a touched object
    ({"torch": "touched", "hand": "hand"}, "t01", "glass"),       # the registered object is not in the file
    ({"glass": "touched", "hand": "hand"}, "t02e", "take"),       # another take's masks
])
def test_cli_refuses_take_masks_that_do_not_carry_the_registered_object(scene, tmp_path, capsys, objects, take, match):
    extra = []
    if objects is not None:
        extra = ["--take-masks", take_masks(tmp_path, {k: getattr(scene, v) for k, v in objects.items()}, take=take)]
    rc, out = _cli(scene, tmp_path, *extra)
    err = capsys.readouterr().err
    assert rc == 1 and match in err and not out.exists(), err


def test_cli_refuses_the_curtain_call(scene, tmp_path, capsys):
    rc, out = _cli(scene, tmp_path, render="t07-ink", custody=False)
    assert rc == 1 and "curtain call" in capsys.readouterr().err and not out.exists()


def test_cli_breath_render_has_no_touched_object_and_no_hand(tmp_path, capsys):
    sc = Scene(tmp_path / "breath", render_id="t04-ink")
    rc, out = _cli(sc, tmp_path)                                  # no take masks needed
    assert rc == 0
    rec = json.loads(out.read_text())
    assert not any(rec["series"]["eligible"]) and not any(rec["series"]["contact"])
    capsys.readouterr()
    rc, out = _cli(sc, tmp_path, "--take-masks", take_masks(tmp_path, {"page": sc.touched, "hand": sc.touched}, take="t04d"))
    assert rc == 1 and "hand" in capsys.readouterr().err
    rc, out = _cli(sc, tmp_path, "--take-masks", take_masks(tmp_path, {"page": sc.touched}, take="t04d"), "--touched", "page")
    assert rc == 1 and "takes.json" in capsys.readouterr().err


# --- review (call 135): the home and the extra records' names are registered, not command-line choices -------------------
def _cli_args(scene, tmp_path, extra=()):
    lines_p = tmp_path / "lines.json"
    lines_p.write_text(json.dumps(scene.lines))
    gate_p = tmp_path / "gate.json"
    gate_p.write_text(json.dumps(scene.gate))
    mp = tmp_path / "take-masks.npz"
    masks.save_masks(mp, {"glass": scene.touched, "hand": scene.hand}, take="t01")
    return ["--render", "t01-ink", "--pair", str(scene.pair), "--lines", str(lines_p), "--gate", str(gate_p),
            "--take-masks", str(mp), "--m", "32", *custody_args(scene, tmp_path), "--kappa", "0.5",
            "--kappa-source", "kappa_render_p1", "--seam-root", str(scene.tmp), *extra]


def test_cli_refuses_a_home_that_is_not_the_renders(scene, tmp_path, capsys):
    rc = assemble.main([*_cli_args(scene, tmp_path, ["--home", "home_gold"]), "--out", str(tmp_path / "x.json")])
    assert rc == 1 and "is not t01-ink's home" in capsys.readouterr().err


def test_cli_takes_extra_records_only_under_registered_names(scene, tmp_path, capsys):
    ex = tmp_path / "ex.json"
    ex.write_text(json.dumps(scene.lines))
    base = _cli_args(scene, tmp_path)                       # one custody chain per scene: build the arguments once
    rc = assemble.main([*base, "--extra", f"whatever={ex}", "--out", str(tmp_path / "x.json")])
    assert rc == 1 and "registered extra" in capsys.readouterr().err
    assert assemble.EXTRA_NAMES == ("interior_excluded", "m48", "m64")
    rc = assemble.main([*base, "--extra", f"interior_excluded={ex}", "--out", str(tmp_path / "y.json")])
    assert rc == 0
