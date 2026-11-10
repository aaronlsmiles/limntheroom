import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from analysis import h_contact as hc

REPO = Path(__file__).resolve().parents[1]
# the seven registered renders with a touched object, sorted: the synthetic renders below take these ids in order,
# so the null's draws (in sorted render-id order) are the ones the earlier r0, r1, ... ids gave
ID = ("t01-gold", "t01-ink", "t01-paper", "t02-ink", "t03-ink", "t05-ink", "t06-ink")
BREATH = "t04-ink"
MISSING = "missing (no measure file: e.g. the blind pick was none, the render failed the gate, or it was not made)"


def row(res, rid):
    [r] = [r for r in res["per_render"] if r["render"] == rid]
    return r


def measure(render, D, contact, eligible=None, aligned=True, motion=None, **extra):
    n = len(D)
    series = {"t": [i / 15 for i in range(n)], "D": list(D), "contact": [bool(c) for c in contact],
              "eligible": [bool(e) for e in (eligible if eligible is not None else [d is not None for d in D])]}
    if motion is not None:
        series["motion"] = list(motion)
    series.update(extra.pop("series_extra", {}))
    rec = {"schema": "p47-measure/1", "render": render, "align": {"pass": aligned}, "series": series}
    rec.update(extra)
    return rec


def peaked(render, seed, effect=2.0, n=60, noise=0.05, window=(20, 36)):
    rng = np.random.default_rng(seed)
    c = np.zeros(n, bool)
    c[window[0]:window[1]] = True
    D = 1.0 + rng.normal(0, noise, n)
    D[c] *= effect
    return measure(render, [float(x) for x in D], c, motion=list(rng.random(n)))


def test_render_r_hand_computed():
    D = [1.0] * 8 + [3.0] * 8 + [None, 5.0]
    c = [False] * 8 + [True] * 8 + [True, True]
    e = [True] * 16 + [False, False]          # the last two are not eligible
    r, nc, nnc = hc.render_r(D, c, e)
    assert (r, nc, nnc) == (3.0, 8, 8)
    assert hc.render_r(D, c, [True] * 15 + [False] * 3)[0] is None     # 7 contact frames: not testable


def test_eligible_is_object_present_and_D_not_None():
    # the measure step's `eligible` may mark a frame whose D is None: it drops out, never raises
    D = [None] + [1.0] * 8 + [3.0] * 8
    c = [True] + [False] * 8 + [True] * 8
    assert hc.render_r(D, c, [True] * 17) == (3.0, 8, 8)
    rec = measure(ID[0], D, c, eligible=[True] * 17)
    pr = row(hc.run([rec]), ID[0])
    assert pr["testable"] and pr["n_contact"] == 8


def test_T_is_mean_log_r_two_renders():
    renders = [measure(ID[0], [1.0] * 8 + [2.0] * 8, [False] * 8 + [True] * 8),
               measure(ID[1], [1.0] * 8 + [4.0] * 8, [False] * 8 + [True] * 8)]
    res = hc.run(renders)
    p = res["primary"]
    assert p["n_testable"] == 2 and p["verdict"] == "not testable"
    assert p["T"] == pytest.approx((math.log(2) + math.log(4)) / 2)


def test_unaligned_render_not_testable():
    res = hc.run([peaked(ID[0], 1) | {"align": {"pass": False}}])
    pr = row(res, ID[0])
    assert not pr["testable"] and pr["reason"] == "not aligned"


def test_supported_on_strong_peaks():
    res = hc.run([peaked(ID[i], i) for i in range(6)])
    p = res["primary"]
    assert p["n_testable"] == 6 and p["median_r"] == pytest.approx(2.0, abs=0.05)
    assert p["p"] <= 0.05 and p["p"] >= 1 / 10001 * (1 - 1e-9) and p["verdict"] == "supported"
    k = round(p["p"] * 10001) - 1
    assert p["p"] == pytest.approx((1 + k) / 10001)


def test_not_supported_without_effect():
    res = hc.run([peaked(ID[i], 100 + i, effect=1.0) for i in range(6)])
    assert res["primary"]["verdict"] == "not supported"


def test_small_effect_with_small_p_not_supported():
    res = hc.run([peaked(ID[i], 200 + i, effect=1.1, noise=0.005) for i in range(6)])
    p = res["primary"]
    assert p["p"] <= 0.05 and p["median_r"] < 1.25 and p["verdict"] == "not supported"


def test_fewer_than_four_not_testable():
    res = hc.run([peaked(ID[i], i) for i in range(3)])
    assert res["primary"]["verdict"] == "not testable" and res["primary"]["p"] is None


def test_object_absent_frames_drop_out():
    rec = peaked(ID[0], 1)
    e = [True] * 60
    e[20:36] = [False] * 16                    # the touched object is never present at contact
    rec["series"]["eligible"] = e
    pr = row(hc.run([rec]), ID[0])
    assert not pr["testable"] and pr["n_contact"] == 0


def test_secondaries_present():
    recs = [peaked(ID[i], i) for i in range(6)]
    for i, r in enumerate(recs):
        r["variants"] = {"proximity_24": {k: r["series"][k] for k in ("D", "contact", "eligible")}}
        r["series"]["hand"] = [0.01] * 60
    meta = {ID[i]: {"material": ID[i].split("-")[1]} for i in range(6)}       # four of the six are ink
    res = hc.run(recs, meta=meta)
    s = res["secondary"]
    assert set(s) >= {"all_frames", "motion_terciles", "variants", "ink_only", "descriptive"}
    assert s["variants"]["proximity_24"]["T"] == pytest.approx(res["primary"]["T"])
    assert s["ink_only"]["n_testable"] == 4
    assert len(s["motion_terciles"]) == 3
    assert "verdict" not in s["all_frames"]
    assert s["descriptive"]["hand"][ID[0]]["contact_mean"] == pytest.approx(0.01)


def test_two_runs_byte_identical(tmp_path):
    paths = []
    for i in range(5):
        p = tmp_path / f"{ID[i]}.json"
        p.write_text(json.dumps(peaked(ID[i], i)))
        paths.append(str(p))
    outs = []
    for k in range(2):
        out = tmp_path / f"h{k}.json"
        subprocess.run([sys.executable, str(REPO / "analysis/h_contact.py"), *paths, "--out", str(out)],
                       check=True, cwd=REPO)
        outs.append(out.read_bytes())
    assert outs[0] == outs[1]
    assert json.loads(outs[0])["primary"]["verdict"] == "supported"


def test_non_finite_D_is_ineligible():
    D = [float("nan"), float("inf")] + [1.0] * 8 + [3.0] * 8
    c = [True, True] + [False] * 8 + [True] * 8
    assert hc.render_r(D, c, [True] * 18) == (3.0, 8, 8)


def test_schema_and_lengths_are_validated():
    good = peaked(ID[0], 1)
    with pytest.raises(ValueError, match="schema"):
        hc.run([good | {"schema": "p47-measure/0"}])
    bad = peaked(ID[1], 2)
    bad["series"]["contact"] = bad["series"]["contact"][:-1]
    with pytest.raises(ValueError, match="lengths differ"):
        hc.run([bad])
    var = peaked(ID[2], 3)
    var["variants"] = {"proximity_24": {"D": [1.0] * 5, "contact": [True] * 6, "eligible": [True] * 5}}
    with pytest.raises(ValueError, match="lengths differ"):
        hc.run([var])


def test_observed_pattern_permutations_equal_T_bitwise():
    # contact repeats every 10 frames, so any shift by a multiple of 10 reproduces the observed pattern
    recs = []
    for i in range(2):
        rng = np.random.default_rng(50 + i)
        c = np.tile([True] * 3 + [False] * 7, 6)
        D = 1.0 + rng.random(60)
        D[c] += 0.7
        recs.append(measure(f"p{i}", [float(x) for x in D], c))
    items = [hc._per_render(r, *hc._primary_pick(r), hc.MIN_SIDE) for r in recs]
    T, Tp, shifts = hc.null_distribution(items)
    same = np.all(np.stack([s % 10 == 0 for s in shifts]), axis=0)
    assert same.sum() > 20
    assert np.all(Tp[same] == T)                       # bitwise, not approximately


def test_params_record_library_versions():
    v = hc.run([peaked(ID[0], 1)])["params"]["versions"]
    assert set(v) == {"opencv-python", "numpy", "av"} and all(v.values())


# ---- which renders enter (review S8: the H inputs are pinned in code) ------------------------------------------
def test_registered_ids_are_the_rated_rows_of_takes_json():
    rows = json.loads((REPO / "capture" / "takes.json").read_text())
    rated = [r for r in rows if r.get("rated")]
    assert list(hc.REGISTERED) == sorted(f"{r['id']}-{r['target_material']}" for r in rated)
    assert {f"{r['id']}-{r['target_material']}" for r in rated if r["paste"]["touched_mask"] is None} == {BREATH}
    assert set(hc.NEVER_TESTABLE) == {BREATH}
    assert hc.EXPECTED_TESTABLE == ID
    assert all(not r.get("rated") for r in rows if r["id"] == "t07")


@pytest.mark.parametrize("rid", ["t09-ink", "t01-glass", "a", "t01ink", "T01-ink", "t02-gold"])
def test_an_unregistered_render_id_is_refused(rid):
    with pytest.raises(ValueError, match="not a registered render"):
        hc.run([peaked(rid, 1)])


@pytest.mark.parametrize("rid", ["t07-ink", "t07-gold", "t07"])
def test_the_curtain_call_is_refused(rid):
    with pytest.raises(ValueError, match="curtain call"):
        hc.run([peaked(rid, 1)])


def test_the_cli_refuses_with_a_message_and_a_non_zero_exit(tmp_path, capsys):
    ok, bad = tmp_path / f"{ID[0]}.json", tmp_path / "t07-ink.json"
    ok.write_text(json.dumps(peaked(ID[0], 1)))
    bad.write_text(json.dumps(peaked("t07-ink", 2)))
    out = tmp_path / "h.json"
    assert hc.main([str(ok), str(bad), "--out", str(out)]) != 0
    assert "curtain call" in capsys.readouterr().err and not out.exists()


def test_every_registered_render_is_listed_and_the_missing_ones_say_why():
    have = [ID[0], ID[2], ID[3], ID[4], ID[6]]                # t01-ink and t05-ink have no measure file
    res = hc.run([peaked(rid, i) for i, rid in enumerate(have)])
    assert [r["render"] for r in res["per_render"]] == list(hc.REGISTERED)
    assert res["renders"] == have and res["missing"] == [ID[1], ID[5]]
    for rid in (ID[1], ID[5]):
        assert row(res, rid) == {"render": rid, "aligned": None, "n_contact": None, "n_noncontact": None, "r": None,
                                 "testable": False, "reason": MISSING}
    assert row(res, BREATH) == {"render": BREATH, "aligned": None, "n_contact": None, "n_noncontact": None, "r": None,
                                "testable": False, "reason": hc.NEVER_TESTABLE[BREATH]}
    assert "no touched object" in hc.NEVER_TESTABLE[BREATH]
    assert res["primary"]["n_testable"] == 5 and res["primary"]["verdict"] == "supported"


def test_the_listing_changes_no_number():
    # the same five measure files: T, p, the median r and every secondary are what they were before the listing
    recs = [peaked(ID[i], i) for i in range(5)]
    res = hc.run(recs)
    items = [hc._per_render(r, *hc._primary_pick(r), hc.MIN_SIDE) for r in recs]
    want = hc.permutation_test(items)
    for k in ("n_testable", "T", "p", "median_r"):
        assert res["primary"][k] == hc._clean(want[k]), k
    assert [r["render"] for r in res["per_render"] if r["testable"]] == list(ID[:5])


def test_the_breath_render_is_listed_as_never_testable_when_its_file_is_given():
    n = 60
    breath = measure(BREATH, [1.0] * n, [False] * n, eligible=[False] * n)
    res = hc.run([peaked(ID[i], i) for i in range(4)] + [breath])
    r = row(res, BREATH)
    assert not r["testable"] and r["reason"] == hc.NEVER_TESTABLE[BREATH] and r["aligned"] is True
    assert BREATH in res["renders"] and BREATH not in res["missing"]
    assert res["primary"]["n_testable"] == 4


@pytest.mark.parametrize("where", ["eligible", "contact", "variant"])
def test_a_breath_file_with_an_eligible_or_contact_frame_is_refused(where):
    n = 60
    flags = [i < 20 for i in range(n)]
    breath = measure(BREATH, [1.0] * n, flags if where == "contact" else [False] * n,
                     eligible=flags if where == "eligible" else [False] * n)
    if where == "variant":
        breath["variants"] = {"d16": {"D": [1.0] * n, "contact": flags, "eligible": [False] * n}}
    with pytest.raises(ValueError, match="breath"):
        hc.run([breath])


def test_meta_must_agree_with_the_render_ids():
    recs = [peaked(ID[i], i) for i in range(4)]
    good = {r["render"]: {"material": r["render"].split("-")[1]} for r in recs}
    hc.run(recs, meta=good)
    with pytest.raises(ValueError, match="material"):
        hc.run(recs, meta={**good, ID[0]: {"material": "ink"}})          # t01-gold called ink
    with pytest.raises(ValueError, match="meta"):
        hc.run(recs, meta={k: v for k, v in good.items() if k != ID[1]})  # a measured render left out of the meta
    with pytest.raises(ValueError, match="registered"):
        hc.run(recs, meta={**good, "t09-ink": {"material": "ink"}})


# --- Gate R review F3 (call 136): drift that grows with time must not pass as a contact effect -----------------------------
def test_the_time_matched_window_is_contact_and_two_seconds_either_side():
    n = 120
    c = np.zeros(n, bool)
    c[60:70] = True
    _, _, e = hc._time_matched_pick(measure(ID[0], [1.0] * n, c))
    e = np.asarray(e)
    assert hc.WINDOW_FRAMES == 30
    assert e[30:100].all() and not e[:30].any() and not e[100:].any()


def _trend(render, n=120, contact=(90, 100)):
    c = np.zeros(n, bool)
    c[contact[0]:contact[1]] = True
    return measure(render, [1.0 + 0.02 * i for i in range(n)], c)      # D rises with time; contact comes late


def test_a_pure_time_trend_is_flagged_by_the_time_matched_r_and_the_slope():
    recs = [_trend(ID[i]) for i in range(6)]
    res = hc.run(recs)
    s = res["secondary"]
    assert res["primary"]["median_r"] > 1.25                            # the trend alone passes the r floor
    assert s["time_matched"]["median_r"] < res["primary"]["median_r"]
    assert s["time_matched"]["median_r"] < 1.1                          # matched in time, the contact excess shrinks
    t = s["trend"][ID[0]]
    assert t["slope_per_s"] == pytest.approx(0.02 * 15) and t["n"] == 110
