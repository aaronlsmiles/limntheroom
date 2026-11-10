#!/usr/bin/env python3
"""Hypothesis H (R0.4): drift outside the creature peaks at contact.

    python analysis/h_contact.py runs/measure/*.json [--meta META.json] --out analysis/out/h_contact.json

Input: p47-measure/1 files (render, align.pass, series.{D, contact, eligible, ...}, optional
variants). META = {render: {material}} for the ink-only secondary.

Which renders enter (pinned here, not by the glob; review S8):
  registered       exactly the eight rated renders of capture/takes.json, `<take>-<material>`
                   (REGISTERED; a test holds the two equal). A measure file for any other id is
                   refused, and t07 (the curtain call, never measured) is refused by name;
  expected         the seven with a touched object (EXPECTED_TESTABLE). One with no measure file
                   is listed in per_render as not testable, reason MISSING, and in `missing`;
  breath           t04-ink has no touched object and is never testable for H: always listed with
                   that reason, and its measure file, if given, is refused if any frame is eligible
                   or in contact (series or variants);
  META             names every measured render, with the material its id names, or is refused.
per_render has one row for each of the eight, in sorted id order. None of this moves a number:
T, p and the median r are computed from the measure files exactly as before. The CLI refuses with
`h_contact: refuse: <why>`, exit 1, and writes nothing.

Primary test, exactly as registered:
  eligible frames  the touched object's take mask is present (the measure step's `eligible`)
                   AND D finite: the two are intersected here, so a None, NaN or ±inf D
                   drops out; D, contact and eligible must have equal lengths;
  per render       r = mean D over eligible contact frames / mean D over eligible non-contact
                   frames;
  testable render  aligned, with at least 8 eligible frames on each side (and a non-zero
                   non-contact mean, else r is undefined);
  statistic        T = mean over testable renders of log r;
  null             each render's contact indicator shifted circularly within its eligible
                   frames, k uniform on {0..n−1}; 10,000 draws; numpy.random.default_rng(20261101),
                   drawn per render in sorted render-id order (rng.integers(0, n_i, 10000));
                   one-sided p = (1 + #{T_π ≥ T}) / 10,001 (an undefined shifted r counts as ≥ T);
  verdict          supported iff ≥ 4 testable renders, p ≤ 0.05 and median r ≥ 1.25; not
                   testable with fewer than 4 (then no p is reported; T and median r are);
                   not supported otherwise.

Secondaries (no verdict; p printed; each with its own default_rng(20261101)): r over all
frames with D not None; r within terciles of the take's motion energy in R (per render, cut at
its eligible frames' 1/3 and 2/3 quantiles; at least 3 frames a side); each named variant in
the measure files (proximity 24 px, touched interior excluded, m and d sensitivity); ink only; the
time-matched r (contact against eligible non-contact frames within 2 s of contact, call 136); and
descriptive: contact vs non-contact means of hand drift, note CER and redrawn-cell shares, and the slope of
D against t over eligible non-contact frames.
Floats are rounded to 12 significant digits; output is byte-identical across runs.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

SEED = 20261101
DRAWS = 10_000
MIN_SIDE = 8
MIN_SIDE_TERCILE = 3
MIN_TESTABLE = 4
ALPHA = 0.05
MIN_MEDIAN_R = 1.25
REGISTERED = ("t01-gold", "t01-ink", "t01-paper", "t02-ink", "t03-ink", "t04-ink", "t05-ink", "t06-ink")
NEVER_TESTABLE = {"t04-ink": "no touched object (the breath take): never testable for H"}
EXPECTED_TESTABLE = tuple(r for r in REGISTERED if r not in NEVER_TESTABLE)
CURTAIN = "t07"
MISSING = "missing (no measure file: e.g. the blind pick was none, the render failed the gate, or it was not made)"
DESCRIPTIVE = ("hand", "ocr_cer", "redrawn_object", "redrawn_rest")
PARAMS = {"seed": SEED, "draws": DRAWS, "min_side": MIN_SIDE, "min_side_tercile": MIN_SIDE_TERCILE,
          "min_testable": MIN_TESTABLE, "alpha": ALPHA, "min_median_r": MIN_MEDIAN_R,
          "registered_renders": list(REGISTERED)}


def versions():
    from importlib.metadata import version
    return {p: version(p) for p in ("opencv-python", "numpy", "av")}


def _round(x):
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, np.integer)):
        return int(x)
    x = float(x)
    if math.isnan(x):
        return "nan"
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return float(f"{x:.12g}")


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (int, float, np.integer, np.floating)):
        return _round(o)
    return o


SCHEMA_IN = "p47-measure/1"


def _finite(d):
    return d is not None and math.isfinite(d)


def _check_lengths(D, contact, eligible, where):
    if not (len(D) == len(contact) == len(eligible)):
        raise ValueError(f"{where}: series lengths differ (D {len(D)}, contact {len(contact)}, "
                         f"eligible {len(eligible)})")


def _eligible_arrays(D, contact, eligible):
    """Eligible = the touched object present (the measure step's flag) AND D finite (not None,
    NaN or ±inf)."""
    _check_lengths(D, contact, eligible, "series")
    e = np.asarray(eligible, bool) & np.array([_finite(d) for d in D], bool)
    d = np.array([D[i] for i in np.flatnonzero(e)], float)
    c = np.asarray(contact, bool)[e]
    return d, c


def _log_r(d, c):
    """log(mean d[c] / mean d[~c]); nan when undefined."""
    with np.errstate(divide="ignore", invalid="ignore"):
        mc, mn = d[c].mean() if c.any() else np.nan, d[~c].mean() if (~c).any() else np.nan
        return float(np.log(mc / mn)) if mn != 0 else float("nan")


def render_r(D, contact, eligible, min_side=MIN_SIDE):
    """(r or None, n_contact, n_noncontact) over eligible frames."""
    d, c = _eligible_arrays(D, contact, eligible)
    nc, nn = int(c.sum()), int((~c).sum())
    if nc < min_side or nn < min_side:
        return None, nc, nn
    mn = d[~c].mean()
    if mn == 0:
        return None, nc, nn
    return float(d[c].mean() / mn), nc, nn


def _per_render(rec, D, contact, eligible, min_side):
    rid = rec["render"]
    _check_lengths(D, contact, eligible, rid)
    aligned = bool(rec.get("align", {}).get("pass"))
    r, nc, nn = render_r(D, contact, eligible, min_side)
    reason = None
    if not aligned:
        reason = "not aligned"
    elif nc < min_side or nn < min_side:
        reason = f"fewer than {min_side} eligible frames on a side"
    elif r is None:
        reason = "non-contact mean is 0"
    out = {"render": rid, "aligned": aligned, "n_contact": nc, "n_noncontact": nn,
           "r": r, "testable": reason is None, "reason": reason}
    if reason is None:
        out["_d"], out["_c"] = _eligible_arrays(D, contact, eligible)
    return out


def _statistic(table, shifts):
    """T for each column of shifts: the mean over renders of log r at that shift. The observed T
    and the permuted T_π go through this one code path, so a shift that reproduces the observed
    pattern gives a bitwise-equal value."""
    return np.mean(np.stack([t[s] for t, s in zip(table, shifts)]), axis=0)


def null_distribution(items, draws=DRAWS, seed=SEED):
    """(T, T_π array, shifts per render) for testable items, in sorted render-id order."""
    items = sorted(items, key=lambda x: x["render"])
    rng = np.random.default_rng(seed)
    table = []
    for it in items:
        d, c = it["_d"], it["_c"]
        table.append(np.array([_log_r(d, np.roll(c, k)) for k in range(len(c))]))
    T = float(_statistic(table, [np.zeros(1, np.int64) for _ in table])[0])
    shifts = [rng.integers(0, len(t), size=draws) for t in table]
    return T, _statistic(table, shifts), shifts


def permutation_test(items, draws=DRAWS, seed=SEED):
    """items: testable per-render dicts (with _d, _c), any order. Returns T, p, median r."""
    if not items:
        return {"n_testable": 0, "T": None, "p": None, "median_r": None}
    T, Tp, _ = null_distribution(items, draws, seed)
    k = int(np.sum((Tp >= T) | np.isnan(Tp)))
    return {"n_testable": len(items), "T": T, "p": (1 + k) / (draws + 1), "k": k,
            "median_r": float(np.median([it["r"] for it in items]))}


def verdict(res):
    if res["n_testable"] < MIN_TESTABLE:
        return "not testable"
    if res["p"] <= ALPHA and res["median_r"] >= MIN_MEDIAN_R:
        return "supported"
    return "not supported"


def _analyse(recs, pick, min_side=MIN_SIDE):
    per = [_per_render(r, *pick(r), min_side) for r in recs]
    res = permutation_test([p for p in per if p["testable"]])
    for p in per:
        p.pop("_d", None)
        p.pop("_c", None)
    return res, per


def _primary_pick(r):
    s = r["series"]
    return s["D"], s["contact"], s["eligible"]


def _all_frames_pick(r):
    s = r["series"]
    return s["D"], s["contact"], [d is not None for d in s["D"]]


WINDOW_FRAMES = 30   # 2 s at 15 analysis frames a second (Gate R review F3, call 136)


def _time_matched_pick(r, w=WINDOW_FRAMES):
    """The time-matched secondary: eligible frames that are contact, or within w frames (2 s) of a contact frame. A
    drift that only grows with time then barely separates contact from its neighbours; the shift null runs within
    these frames, as for the primary."""
    s = r["series"]
    e = np.asarray(s["eligible"], bool)
    c = np.asarray(s["contact"], bool)
    near = np.zeros(len(e), bool)
    for i in np.flatnonzero(c & e):
        near[max(0, i - w):i + w + 1] = True
    return s["D"], s["contact"], list(e & (c | near))


def _trend(recs):
    """Descriptive: per render, the least-squares slope of D against t (per second) over eligible non-contact frames
    with a finite D, and how many frames it rests on (Gate R review F3, call 136)."""
    out = {}
    for r in recs:
        s = r["series"]
        e = np.asarray(s["eligible"], bool) & ~np.asarray(s["contact"], bool)
        pts = [(s["t"][i], s["D"][i]) for i in np.flatnonzero(e) if _finite(s["D"][i])]
        slope = float(np.polyfit([t for t, _ in pts], [d for _, d in pts], 1)[0]) if len(pts) >= 2 else None
        out[r["render"]] = {"slope_per_s": slope, "n": len(pts)}
    return out


def _tercile_pick(k):
    def pick(r):
        s = r["series"]
        e = np.asarray(s["eligible"], bool)
        m = np.asarray([np.nan if v is None else v for v in s.get("motion", [None] * len(e))], float)
        e = e & ~np.isnan(m)
        if not e.any():
            return s["D"], s["contact"], [False] * len(e)
        q1, q2 = np.quantile(m[e], [1 / 3, 2 / 3])
        band = [m <= q1, (m > q1) & (m <= q2), m > q2][k]
        return s["D"], s["contact"], list(e & band)
    return pick


def _variant_pick(name):
    def pick(r):
        v = r.get("variants", {}).get(name)
        if v is None:
            n = len(r["series"]["D"])
            return [None] * n, [False] * n, [False] * n
        return v["D"], v["contact"], v["eligible"]
    return pick


def _descriptive(recs):
    out = {}
    for key in DESCRIPTIVE:
        rows = {}
        for r in recs:
            s = r["series"]
            if key not in s:
                continue
            e = np.asarray(s["eligible"], bool)
            c = np.asarray(s["contact"], bool)
            v = s[key]
            def mean(mask):
                xs = [v[i] for i in np.flatnonzero(mask) if v[i] is not None]
                return float(np.mean(xs)) if xs else None
            rows[r["render"]] = {"contact_mean": mean(e & c), "noncontact_mean": mean(e & ~c)}
        if rows:
            out[key] = rows
    return out


def _summary(res, per=None, with_verdict=False):
    out = {k: res[k] for k in ("n_testable", "T", "p", "median_r")}
    if with_verdict:
        out["verdict"] = verdict(res)
    if per is not None:
        out["per_render"] = per
    return out


def check_render_id(rid):
    """Refuse a render id that is not one of the eight registered renders; the curtain call by name."""
    if isinstance(rid, str) and (rid == CURTAIN or rid.startswith(CURTAIN + "-")):
        raise ValueError(f"{rid}: t07 is the curtain call, which is never measured for H")
    if rid not in REGISTERED:
        raise ValueError(f"{rid!r} is not a registered render id ({', '.join(REGISTERED)})")


def _check_never_testable(r):
    """A render with no touched object (the breath take) can have no eligible or contact frame anywhere."""
    rid = r["render"]
    for name, s in [("series", r["series"]), *((f"variant {k}", v) for k, v in sorted(r.get("variants", {}).items()))]:
        for key in ("eligible", "contact"):
            if any(s.get(key) or []):
                raise ValueError(f"{rid}: the breath render has no touched object, but its {name} marks "
                                 f"{key} frames")


def _check_meta(meta, rids):
    for rid, m in sorted(meta.items()):
        check_render_id(rid)
        want, got = rid.split("-", 1)[1], m.get("material") if isinstance(m, dict) else None
        if got != want:
            raise ValueError(f"meta: {rid} has material {got!r}, but its id names {want!r}")
    left = sorted(set(rids) - set(meta))
    if left:
        raise ValueError(f"meta names no material for the measured render(s) {left}")


def _listing(per):
    """per_render for all eight registered renders: the measured ones as computed (the breath render's
    reason replaced by its registered one), the rest as not testable with the reason they did not enter."""
    rows = {p["render"]: p for p in per}
    out = []
    for rid in REGISTERED:
        p = rows.get(rid) or {"render": rid, "aligned": None, "n_contact": None, "n_noncontact": None, "r": None,
                              "testable": False, "reason": MISSING}
        if rid in NEVER_TESTABLE:
            p = {**p, "testable": False, "reason": NEVER_TESTABLE[rid]}
        out.append(p)
    return out


def run(recs, meta=None):
    for r in recs:
        if r.get("schema") != SCHEMA_IN:
            raise ValueError(f"{r.get('render')}: schema {r.get('schema')!r}, expected {SCHEMA_IN}")
    for r in recs:
        check_render_id(r.get("render"))
    recs = sorted(recs, key=lambda r: r["render"])
    if len({r["render"] for r in recs}) != len(recs):
        raise ValueError("duplicate render ids")
    for r in recs:
        if r["render"] in NEVER_TESTABLE:
            _check_never_testable(r)
    if meta:
        _check_meta(meta, [r["render"] for r in recs])
    res, per = _analyse(recs, _primary_pick)
    secondary = {}
    s, _ = _analyse(recs, _all_frames_pick)
    secondary["all_frames"] = _summary(s)
    if any("motion" in r["series"] for r in recs):
        secondary["motion_terciles"] = [_summary(_analyse(recs, _tercile_pick(k), MIN_SIDE_TERCILE)[0])
                                        for k in range(3)]
    names = sorted({n for r in recs for n in r.get("variants", {})})
    secondary["variants"] = {n: _summary(_analyse(recs, _variant_pick(n))[0]) for n in names}
    if meta:
        ink = [r for r in recs if meta.get(r["render"], {}).get("material") == "ink"]
        secondary["ink_only"] = _summary(_analyse(ink, _primary_pick)[0])
    secondary["time_matched"] = _summary(_analyse(recs, _time_matched_pick)[0])
    secondary["trend"] = _trend(recs)
    secondary["descriptive"] = _descriptive(recs)
    primary = {**_summary(res, with_verdict=True), "k": res.get("k")}
    if primary["verdict"] == "not testable":         # no p for a test that is not run
        primary["p"] = primary["k"] = None
    measured = [r["render"] for r in recs]
    return _clean({"schema": "p47-h/1", "params": {**PARAMS, "versions": versions()}, "renders": measured,
                   "missing": [rid for rid in EXPECTED_TESTABLE if rid not in measured],
                   "primary": primary,
                   "per_render": _listing(per), "secondary": secondary})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("measure", nargs="+")
    ap.add_argument("--meta")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        recs = [json.loads(Path(p).read_text()) for p in a.measure]
        meta = json.loads(Path(a.meta).read_text()) if a.meta else None
        res = run(recs, meta)
    except (ValueError, KeyError, OSError) as e:
        print(f"h_contact: refuse: {e}", file=sys.stderr)
        return 1
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
