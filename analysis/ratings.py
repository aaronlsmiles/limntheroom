#!/usr/bin/env python3
"""The rating study's registered numbers (R0.8), per law, null or not.

    python analysis/ratings.py --key sealed/answer-key.json --rater R1=raw/R1/ratings.csv \
        [--rater R2=...] [--study sealed/rating-manifest.json] --out analysis/out/ratings.json

Each --rater is one blindpanel v0.2 export (`ratings.csv`: visitor, instrument, part, position,
item, question, score, flags, option) of that rater's own study id. If an export holds more than one
session (visitor), the first that answers every item counts, else the first session (§17; call 136); the
output records each rater's choice under "sessions".

Answer key: {salt, questions: {clip_target, clip_behaviour, base_target, base_behaviour}
(question ids), clips: {item: {law, target, behaviour}}, baseline: {item: {law, target,
behaviour}}}. A hit is the `option` label equal to the key's label.

Per law: clip Q1 hit rate; law hit rate (Q1 and Q2 both right, same rater and clip); clip Q2
hit rate; baseline Q1b and Q2b hit rates; clip minus baseline (clip Q2 − baseline Q2b; the Q1
difference beside it); Wilson 95 % intervals and n throughout. Fleiss' κ per question over its
items, with option labels as categories (per-item-n form, equal to Fleiss with equal n; None
when expected agreement is 1). Floats rounded to 12 significant digits.

--study (deviation D3, call 143): the study's rating manifest. The key is restricted to the items that study built,
so the session rule's "every item" means every item the rater was shown; the output lists those items and the laws
with no item in the study, which are not reported with n = 0. Without it, the registered run.
"""
import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

Z95 = 1.959963984540054
COLUMNS = ["visitor", "instrument", "part", "position", "item", "question", "score", "flags", "option"]


def _r(x):
    return None if x is None else float(f"{x:.12g}")


def read_sessions(path):
    """{visitor: [rows]} in the order each visitor first appears in the export."""
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        if rd.fieldnames != COLUMNS:
            raise ValueError(f"{path}: not a blindpanel v0.2 ratings.csv (columns {rd.fieldnames})")
        rows = list(rd)
    out = {}
    for r in rows:
        out.setdefault(r["visitor"], []).append(
            {"part": r["part"], "item": r["item"], "question": r["question"], "option": r["option"]})
    return out


def expected_answers(key):
    """Every (item, question id) a complete session answers: each clip item's two questions and each baseline
    item's two."""
    q = key["questions"]
    return ({(i, q[k]) for i in key["clips"] for k in ("clip_target", "clip_behaviour")}
            | {(i, q[k]) for i in key["baseline"] for k in ("base_target", "base_behaviour")})


def study_key(key, study):
    """D3 (call 143): the key restricted to the items a study built (`study`: its rating manifest). Refuses a study with
    no items or an item twice, an item the key lacks, or an item whose law disagrees with the key's."""
    items = study.get("items") or []
    refs = [i["ref"] for i in items]
    if not refs or len(set(refs)) != len(refs):
        raise ValueError("the study manifest lists no items, or an item twice")
    for i in items:
        for part in ("clips", "baseline"):
            if i["ref"] not in key[part]:
                raise ValueError(f"study item {i['ref']} is not in the key's {part}")
            if "law" in i and key[part][i["ref"]]["law"] != i["law"]:
                raise ValueError(f"study item {i['ref']}: its law disagrees with the key")
    return {**key, "clips": {r: key["clips"][r] for r in refs}, "baseline": {r: key["baseline"][r] for r in refs}}


def choose_session(sessions, key):
    """(visitor, reason) by the registered rule (§17; Gate R review, call 136): the first session that answers every
    item counts; if none does, the first session counts, its unanswered items missing. No person chooses."""
    want = expected_answers(key)
    for v, rows in sessions.items():
        if want <= {(r["item"], r["question"]) for r in rows if r["option"].strip()}:
            return v, "the first complete session"
    return next(iter(sessions)), "no complete session: the first session"


def read_export(path, key=None, choice=None):
    """One rater's rows. An export with more than one session needs the answer key, and the session is chosen by the
    registered rule (choose_session); `choice`, if a dict, receives {visitor, reason, n_sessions}."""
    sessions = read_sessions(path)
    if not sessions:
        return []
    if len(sessions) == 1:
        v, reason = next(iter(sessions)), "the only session"
    elif key is None:
        raise ValueError(f"{path}: {len(sessions)} sessions in one rater's export; the answer key is needed to apply "
                         "the registered session rule")
    else:
        v, reason = choose_session(sessions, key)
    if isinstance(choice, dict):
        choice.update(visitor=v, reason=reason, n_sessions=len(sessions))
    return sessions[v]


def wilson(k, n, z=Z95):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z / d * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, c - h), min(1.0, c + h))


def fleiss_kappa(table):
    """table: items × categories counts. Items with fewer than 2 ratings are skipped."""
    rows = [list(map(int, r)) for r in table if sum(r) >= 2]
    if not rows:
        return None
    P_i = [(sum(x * x for x in r) - sum(r)) / (sum(r) * (sum(r) - 1)) for r in rows]
    total = sum(sum(r) for r in rows)
    p_j = [sum(r[j] for r in rows) / total for j in range(len(rows[0]))]
    Pbar = sum(P_i) / len(P_i)
    Pe = sum(p * p for p in p_j)
    if Pe == 1:
        return None
    return (Pbar - Pe) / (1 - Pe)


def _rate(k, n):
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": _r(k / n) if n else None, "ci": [_r(lo), _r(hi)]}


def analyse(raters, key):
    q = key["questions"]
    ans = {rid: {(r["part"], r["item"], r["question"]): r["option"] for r in rows} for rid, rows in raters.items()}
    laws = sorted({v["law"] for v in key["clips"].values()} | {v["law"] for v in key["baseline"].values()})
    out = {}
    for law in laws:
        counts = defaultdict(lambda: [0, 0])
        for item, k in sorted(key["clips"].items()):
            if k["law"] != law:
                continue
            for rid in sorted(ans):
                a1 = ans[rid].get(("clips", item, q["clip_target"]))
                a2 = ans[rid].get(("clips", item, q["clip_behaviour"]))
                for name, a, want in (("q1", a1, k["target"]), ("q2", a2, k["behaviour"])):
                    if a is not None:
                        counts[name][0] += a == want
                        counts[name][1] += 1
                if a1 is not None and a2 is not None:
                    counts["law"][0] += (a1 == k["target"]) and (a2 == k["behaviour"])
                    counts["law"][1] += 1
        for item, k in sorted(key["baseline"].items()):
            if k["law"] != law:
                continue
            for rid in sorted(ans):
                for name, qid, want in (("q1b", q["base_target"], k["target"]), ("q2b", q["base_behaviour"], k["behaviour"])):
                    a = ans[rid].get(("baseline", item, qid))
                    if a is not None:
                        counts[name][0] += a == want
                        counts[name][1] += 1
        rates = {name: _rate(*counts[name]) for name in ("q1", "q2", "law", "q1b", "q2b")}

        def diff(a, b):
            return _r(rates[a]["rate"] - rates[b]["rate"]) if None not in (rates[a]["rate"], rates[b]["rate"]) else None
        out[law] = {"clip": {k: rates[k] for k in ("q1", "q2", "law")},
                    "baseline": {k: rates[k] for k in ("q1b", "q2b")},
                    "clip_minus_baseline": diff("q2", "q2b"), "q1_clip_minus_baseline": diff("q1", "q1b")}
    kappa = {}
    for part, qid, items in (("clips", q["clip_target"], key["clips"]), ("clips", q["clip_behaviour"], key["clips"]),
                             ("baseline", q["base_target"], key["baseline"]),
                             ("baseline", q["base_behaviour"], key["baseline"])):
        per_item = [Counter(a for rid in sorted(ans) if (a := ans[rid].get((part, item, qid))) is not None)
                    for item in sorted(items)]
        cats = sorted({c for ctr in per_item for c in ctr})
        kappa[qid] = _r(fleiss_kappa([[ctr[c] for c in cats] for ctr in per_item])) if cats else None
    return {"schema": "p47-ratings/1", "raters": sorted(raters), "n_raters": len(raters), "laws": out, "kappa": kappa}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True)
    ap.add_argument("--rater", action="append", required=True, help="RATER_ID=path/to/ratings.csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--study", help="D3: the study's rating manifest (sealed/rating-manifest.json); the key is restricted "
                                    "to the items it built")
    a = ap.parse_args(argv)
    full = key = json.loads(Path(a.key).read_text())
    if a.study:
        key = study_key(full, json.loads(Path(a.study).read_text()))
    raters, sessions = {}, {}
    for spec in a.rater:
        rid, _, path = spec.partition("=")
        if not rid or not path or rid in raters:
            raise SystemExit(f"bad or repeated --rater {spec!r}")
        sessions[rid] = {}
        raters[rid] = read_export(path, key, choice=sessions[rid])
    rec = analyse(raters, key)
    rec["sessions"] = sessions
    if a.study:
        rec["study_items"] = sorted(key["clips"])
        rec["not_in_study"] = sorted({v["law"] for v in full["clips"].values()} - {v["law"] for v in key["clips"].values()})
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
