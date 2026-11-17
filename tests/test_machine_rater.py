import json
from pathlib import Path

from analysis import ratings
from seam import blind
from tools import machine_rater as mr


def seal_round(round_id, answers, valid=True):
    code = f"b{round_id[-5:]}"
    led = blind.rater_ledger_path(round_id)
    led.parent.mkdir(parents=True, exist_ok=True)
    led.write_text(json.dumps({"round": round_id, "result": {"status": "rated", "code": code} if valid else None}))
    out = Path(blind.SEALED) / "machine-rater" / f"{code}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    refs = {f"q{k}": ref for k, ref in enumerate(answers)}
    out.write_text(json.dumps({"round": round_id, "valid": valid, "refs": refs,
                               "output": {"items": {f"q{k}": a for k, a in enumerate(answers.values())}, "notes": ""}}))


def test_csv_is_an_export_the_registered_analysis_reads(tmp_path):
    seal_round("study-baseline", {"t01-ink": {"q1b": "The pen", "q2b": "Can't tell"}})
    seal_round("study-clips", {"t01-ink": {"q1": "The glass of water", "q2": "Nothing in particular"}})
    got = mr.write_csv(tmp_path / "m.csv")
    assert got["rows"] == 4 and got["missing"] == []
    sessions = ratings.read_sessions(tmp_path / "m.csv")
    assert list(sessions) == ["M"]
    assert {(r["part"], r["item"], r["question"], r["option"]) for r in sessions["M"]} == {
        ("baseline", "t01-ink", "q1b", "The pen"), ("baseline", "t01-ink", "q2b", "Can't tell"),
        ("clips", "t01-ink", "q1", "The glass of water"), ("clips", "t01-ink", "q2", "Nothing in particular")}


def test_a_round_without_a_valid_record_is_missing(tmp_path):
    seal_round("study-baseline", {"t01-ink": {"q1b": "The pen", "q2b": "Can't tell"}})
    seal_round("study-clips", {"t01-ink": {"q1": "The pen", "q2": "Can't tell"}}, valid=False)
    got = mr.write_csv(tmp_path / "m.csv")
    assert got["missing"] == ["study-clips"] and got["rows"] == 2
