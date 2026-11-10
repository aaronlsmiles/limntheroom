import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from analysis import ratings

REPO = Path(__file__).resolve().parents[1]
HEADER = ["visitor", "instrument", "part", "position", "item", "question", "score", "flags", "option"]

# Fictional laws and labels only: nothing here is a registered law.
KEY = {
    "salt": "fixture",
    "questions": {"clip_target": "q1", "clip_behaviour": "q2", "base_target": "q1b", "base_behaviour": "q2b"},
    "clips": {"c1": {"law": "ink.cup", "target": "The cup", "behaviour": "It shrinks"},
              "c2": {"law": "gold.lamp", "target": "The lamp", "behaviour": "It glows, then dims"}},
    "baseline": {"b1": {"law": "ink.cup", "target": "The cup", "behaviour": "It shrinks"},
                 "b2": {"law": "gold.lamp", "target": "The lamp", "behaviour": "It glows, then dims"}},
}

# rater -> {(part, item, question): option}
ANSWERS = {
    "R1": {("clips", "c1", "q1"): "The cup", ("clips", "c1", "q2"): "It shrinks",
           ("clips", "c2", "q1"): "The lamp", ("clips", "c2", "q2"): "Can't tell",
           ("baseline", "b1", "q1b"): "The cup", ("baseline", "b1", "q2b"): "Nothing in particular",
           ("baseline", "b2", "q1b"): "The cup", ("baseline", "b2", "q2b"): "It glows, then dims"},
    "R2": {("clips", "c1", "q1"): "The cup", ("clips", "c1", "q2"): "It glows, then dims",
           ("clips", "c2", "q1"): "The lamp", ("clips", "c2", "q2"): "It glows, then dims",
           ("baseline", "b1", "q1b"): "The lamp", ("baseline", "b1", "q2b"): "It shrinks",
           ("baseline", "b2", "q1b"): "The lamp", ("baseline", "b2", "q2b"): "Can't tell"},
    "R3": {("clips", "c1", "q1"): "Nothing in particular", ("clips", "c1", "q2"): "It shrinks",
           ("clips", "c2", "q1"): "The lamp", ("clips", "c2", "q2"): "It glows, then dims",
           ("baseline", "b1", "q1b"): "The cup", ("baseline", "b1", "q2b"): "Nothing in particular",
           ("baseline", "b2", "q1b"): "The lamp", ("baseline", "b2", "q2b"): "It glows, then dims"},
}


def write_export(path, answers, visitors=("V0001",)):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(HEADER)
        for v in visitors:
            for pos, ((part, item, q), opt) in enumerate(sorted(answers.items()), 1):
                w.writerow([v, "p47", part, pos, item, q, 1, "", opt])
    return path


@pytest.fixture
def exports(tmp_path):
    return {r: write_export(tmp_path / f"{r}.csv", a) for r, a in ANSWERS.items()}


def test_wilson_known_values():
    lo, hi = ratings.wilson(0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.2775, abs=1e-4)
    lo, hi = ratings.wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4) and hi == pytest.approx(0.7634, abs=1e-4)
    assert ratings.wilson(0, 0) == (None, None)


def test_fleiss_wikipedia_example():
    table = [[0, 0, 0, 0, 14], [0, 2, 6, 4, 2], [0, 0, 3, 5, 6], [0, 3, 9, 2, 0], [2, 2, 8, 1, 1],
             [7, 7, 0, 0, 0], [3, 2, 6, 3, 0], [2, 5, 3, 2, 2], [6, 5, 2, 1, 0], [0, 2, 2, 3, 7]]
    assert ratings.fleiss_kappa(table) == pytest.approx(0.210, abs=5e-4)
    assert ratings.fleiss_kappa([[3], [3]]) is None


def test_read_export_parses_commas_and_refuses_two_visitors(tmp_path):
    rows = ratings.read_export(write_export(tmp_path / "a.csv", ANSWERS["R1"]))
    assert {"part": "clips", "item": "c2", "question": "q2", "option": "Can't tell"} in rows
    assert any(r["option"] == "It glows, then dims" for r in rows)
    with pytest.raises(ValueError):
        ratings.read_export(write_export(tmp_path / "b.csv", ANSWERS["R1"], visitors=("V0001", "V0002")))


def test_per_law_rates_by_hand(exports):
    res = ratings.analyse({r: ratings.read_export(p) for r, p in exports.items()}, KEY)
    cup, lamp = res["laws"]["ink.cup"], res["laws"]["gold.lamp"]
    assert cup["clip"]["q1"]["k"] == 2 and cup["clip"]["q1"]["n"] == 3
    assert cup["clip"]["q2"]["k"] == 2
    assert cup["clip"]["law"]["k"] == 1                    # only R1 has both right
    assert cup["baseline"]["q2b"]["k"] == 1                # R2
    assert cup["clip_minus_baseline"] == pytest.approx(2 / 3 - 1 / 3)
    assert lamp["clip"]["q1"]["k"] == 3 and lamp["clip"]["law"]["k"] == 2
    assert lamp["baseline"]["q2b"]["k"] == 2 and lamp["baseline"]["q1b"]["k"] == 2
    assert lamp["clip_minus_baseline"] == pytest.approx(0.0)
    assert lamp["q1_clip_minus_baseline"] == pytest.approx(1 - 2 / 3)
    lo, hi = ratings.wilson(2, 3)
    assert cup["clip"]["q1"]["ci"] == [pytest.approx(lo), pytest.approx(hi)]
    assert set(res["kappa"]) == {"q1", "q2", "q1b", "q2b"}
    assert res["n_raters"] == 3


def test_kappa_from_answers(exports):
    res = ratings.analyse({r: ratings.read_export(p) for r, p in exports.items()}, KEY)
    # q1 table over items c1, c2 (categories: The cup, The lamp, Nothing in particular)
    want = ratings.fleiss_kappa([[2, 0, 1], [0, 3, 0]])
    assert res["kappa"]["q1"] == pytest.approx(want)


def test_two_runs_byte_identical(tmp_path, exports):
    key = tmp_path / "key.json"
    key.write_text(json.dumps(KEY))
    outs = []
    for k in range(2):
        out = tmp_path / f"o{k}.json"
        args = [sys.executable, str(REPO / "analysis/ratings.py"), "--key", str(key), "--out", str(out)]
        for r, p in exports.items():
            args += ["--rater", f"{r}={p}"]
        subprocess.run(args, check=True, cwd=REPO)
        outs.append(out.read_bytes())
    assert outs[0] == outs[1]


# --- Gate R review F2 (call 136): the registered session rule; no person chooses ------------------------------------------
def _sessions(path, *answer_sets):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(HEADER)
        for k, answers in enumerate(answer_sets, 1):
            for pos, ((part, item, q), opt) in enumerate(sorted(answers.items()), 1):
                w.writerow([f"V{k:04d}", "p47", part, pos, item, q, 1, "", opt])
    return path


def test_the_first_complete_session_counts(tmp_path):
    partial = dict(sorted(ANSWERS["R1"].items())[:3])
    p = _sessions(tmp_path / "x.csv", partial, ANSWERS["R2"], ANSWERS["R3"])
    rows = ratings.read_export(p, KEY)
    assert {(r["part"], r["item"], r["question"]): r["option"] for r in rows} == ANSWERS["R2"]
    assert ratings.choose_session(ratings.read_sessions(p), KEY) == ("V0002", "the first complete session")


def test_with_no_complete_session_the_first_session_counts(tmp_path):
    p = _sessions(tmp_path / "y.csv", dict(sorted(ANSWERS["R1"].items())[:3]), dict(sorted(ANSWERS["R2"].items())[:5]))
    assert len(ratings.read_export(p, KEY)) == 3
    assert ratings.choose_session(ratings.read_sessions(p), KEY) == ("V0001", "no complete session: the first session")


def test_more_than_one_session_needs_the_key_and_main_records_the_choice(tmp_path):
    p = _sessions(tmp_path / "z.csv", dict(sorted(ANSWERS["R1"].items())[:3]), ANSWERS["R1"])
    with pytest.raises(ValueError, match="key"):
        ratings.read_export(p)
    key = tmp_path / "key.json"
    key.write_text(json.dumps(KEY))
    out = tmp_path / "out.json"
    assert ratings.main(["--key", str(key), "--rater", f"R1={p}", "--out", str(out)]) == 0
    rec = json.loads(out.read_text())
    assert rec["sessions"]["R1"] == {"visitor": "V0002", "reason": "the first complete session", "n_sessions": 2}


# --- D3 (call 143): the failure path's study builds three of the key's items; --study restricts the key to them ---------
def _wide_key():
    """Three items sharing refs across the parts, as the real key does; the study builds two of them."""
    e = {"g1": {"law": "ink.cup", "target": "The cup", "behaviour": "It shrinks"},
         "g2": {"law": "gold.cup", "target": "The cup", "behaviour": "It glows, then dims"},
         "x1": {"law": "ink.lamp", "target": "The lamp", "behaviour": "It hums"}}
    return {"salt": "fixture", "questions": dict(KEY["questions"]), "clips": e, "baseline": json.loads(json.dumps(e))}


STUDY = {"failure_path": True, "items": [{"ref": "g1", "law": "ink.cup"}, {"ref": "g2", "law": "gold.cup"}]}
STUDY_ANSWERS = {("clips", "g1", "q1"): "The cup", ("clips", "g1", "q2"): "It shrinks",
                 ("clips", "g2", "q1"): "The cup", ("clips", "g2", "q2"): "It hums",
                 ("baseline", "g1", "q1b"): "The cup", ("baseline", "g1", "q2b"): "Can't tell",
                 ("baseline", "g2", "q1b"): "The lamp", ("baseline", "g2", "q2b"): "It glows, then dims"}


def test_a_study_manifest_restricts_the_key_to_the_items_it_built():
    k = ratings.study_key(_wide_key(), STUDY)
    assert sorted(k["clips"]) == sorted(k["baseline"]) == ["g1", "g2"]
    assert k["questions"] == KEY["questions"] and k["clips"]["g2"] == _wide_key()["clips"]["g2"]
    with pytest.raises(ValueError, match="not in the key"):
        ratings.study_key(_wide_key(), {"items": [{"ref": "zz"}]})
    with pytest.raises(ValueError, match="law disagrees"):
        ratings.study_key(_wide_key(), {"items": [{"ref": "g1", "law": "gold.cup"}]})
    with pytest.raises(ValueError, match="no items"):
        ratings.study_key(_wide_key(), {"items": []})


def test_with_a_study_the_first_session_that_answers_its_items_is_complete(tmp_path):
    p = _sessions(tmp_path / "s.csv", dict(sorted(STUDY_ANSWERS.items())[:3]), STUDY_ANSWERS)
    s = ratings.read_sessions(p)
    assert ratings.choose_session(s, _wide_key()) == ("V0001", "no complete session: the first session")   # registered
    assert ratings.choose_session(s, ratings.study_key(_wide_key(), STUDY)) == ("V0002", "the first complete session")


def test_main_with_a_study_reports_its_laws_and_lists_the_rest(tmp_path):
    key, study, out, reg = tmp_path / "key.json", tmp_path / "study.json", tmp_path / "out.json", tmp_path / "reg.json"
    key.write_text(json.dumps(_wide_key()))
    study.write_text(json.dumps(STUDY))
    p = write_export(tmp_path / "r1.csv", STUDY_ANSWERS)
    assert ratings.main(["--key", str(key), "--study", str(study), "--rater", f"R1={p}", "--out", str(out)]) == 0
    rec = json.loads(out.read_text())
    assert sorted(rec["laws"]) == ["gold.cup", "ink.cup"] and rec["not_in_study"] == ["ink.lamp"]
    assert rec["study_items"] == ["g1", "g2"]
    assert rec["laws"]["ink.cup"]["clip"]["law"] == {"k": 1, "n": 1, "rate": 1.0, "ci": rec["laws"]["ink.cup"]["clip"]["law"]["ci"]}
    assert rec["laws"]["gold.cup"]["clip"]["q2"]["k"] == 0
    assert ratings.main(["--key", str(key), "--rater", f"R1={p}", "--out", str(reg)]) == 0      # the registered run is unchanged
    r = json.loads(reg.read_text())
    assert "not_in_study" not in r and "study_items" not in r and r["laws"]["ink.lamp"]["clip"]["q1"]["n"] == 0
