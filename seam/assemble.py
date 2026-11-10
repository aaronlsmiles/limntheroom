#!/usr/bin/env python3
"""Phase 8 assembly: one `p47-measure/1` file per render, in the shape analysis/h_contact.py reads.

    python seam/assemble.py --render t01-ink --pair P.npz --lines L.json --gate G.json \
        --take-masks M.npz --m 32 --kappa 0.31 --kappa-source kappa_render_p1 \
        --out runs/measure/t01-ink.json

The masks of contact and eligibility are not a choice (review S8). The render id must be one of the eight
rated renders of capture/takes.json, `<take>-<material>`; t07, the curtain call, is refused by name. The
touched object is the take-mask object that row's `paste.touched_mask` names (`registered_masks`), and
`--take-masks` must be the take's own file (its recorded take is the render's take plus at most an attempt
letter) and must hold that object. The hand applies to every take with a touched object: the take masks'
`hand` object, whenever the file has one. The breath take (touched_mask null) has no touched object and no
hand, so a take-mask file with a `hand` is refused for it. `--touched` and `--hand` are optional checks that
are refused if they name anything else. `assemble()` refuses a touched mask (or a hand mask) whose presence
disagrees with the registration.

Inputs (all for one render, all on the 15 fps analysis grid):
  gate      the alignment gate's output (seam.align.gate: pass, lag, rho, frames_ok, ok per frame);
  masks     the render's creature masks (warped onto the take grid), the touched object's and the
            hand's take masks, and the acting creature's home;
  lines     the lines job's `p47-lines/1` record from `measure` (D, D0, cells, homes, seam bin path);
  extras    hand keypoint drift and OCR CER series (seam.hands, seam.ocr), optional;
  take      the take's frames, only for the motion series (take energy in R, for the terciles).

What it adds:
  scored frames   `scored_frames`: passed the gate AND the mask quality rule (masks.quality_ok from the
                  render mask's prompt frame; frames before it are the drawing at home, so they are
                  valid and A(t) is the dilated home alone: `region_series`). The lines job's `valid`
                  must equal this, or the file is refused.
  contact         c(t) = dilate(creature, 8 px) ∩ (touched ∪ hand) ≠ ∅ (seam.regions), plus the d = 4,
                  16 and proximity-24 variants;
  eligible        the touched object's take mask is present AND D is finite (no touched object, no
                  eligible frame: the breath render is not testable for H);
  D, D0, hand, ocr_cer   carried as they are; a NaN or infinite value becomes None;
  redrawn_object / redrawn_rest   the redrawn share of the verdict cells inside the touched object
                  (cell covered at least half by its take mask) against the rest of R, per frame,
                  read from the seam bin;
  variants        d4, d16, proximity24 from the masks; any further `extra_lines` record (the touched
                  object's interior excluded; the other two margins) becomes a variant of its own.

Refused, with a message that names the series: unequal lengths, a lines record for another render or
margin, a valid mask that differs from gate + mask quality, a D on an unscored frame, a κ that differs
from the one the lines job classified with, a κ source that is not `kappa_render_p1` / `kappa_codec`,
a seam bin that is missing or the wrong size.

Run order around the no-op null: compile the no-op request with `--trim-to 10` (a 10 s clip, like the
probe) and gate its render before anything else; its `kappa_render_p1`, or the fallback `kappa_codec`,
is the κ every render here is classified with. Paste and shift controls come first (seam/controls_inputs.py).
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from seam import align, cells, masks, regions  # noqa: E402

SCHEMA = "p47-measure/1"
LINES_SCHEMA = "p47-lines/1"
ASSEMBLER = "p47-assemble/1"
FPS = 15
M_CHOICES = (32, 48, 64)
KAPPA_SOURCES = ("kappa_render_p1", "kappa_codec")
VARIANT_D = (("d4", 4), ("d16", 16), ("proximity24", regions.PROXIMITY_PX))
SERIES_KEYS = ("t", "D", "D0", "contact", "eligible", "hand", "ocr_cer")
NUMERIC_SERIES = ("D", "D0", "hand", "ocr_cer", "motion", "redrawn_object", "redrawn_rest")
BOOL_SERIES = ("contact", "eligible")
PARAM_KEYS = ("m", "d", "tau", "cell", "fps", "kappa_keep", "kappa_source", "versions")
ALIGN_KEYS = ("pass", "lag", "rho", "frames_ok", "lag_source", "lag_applicable", "lag_reason", "duration_ok",
              "lag_energy_mean")
SEAM_KEYS = ("file", "cols", "rows")
TAKES = REPO / "capture" / "takes.json"
CURTAIN = "t07"
HAND = "hand"          # the take masks' name for the hand


# ---- helpers ----------------------------------------------------------------------------------------------
def _f(x):
    """A finite float or None (None, NaN and ±inf all become None)."""
    if x is None:
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def _fl(seq):
    return [_f(x) for x in seq]


def _n(name, seq, n):
    if len(seq) != n:
        raise ValueError(f"{name}: length {len(seq)} != {n} frames")


def _stack(name, a, n, shape=None):
    a = np.asarray(a, bool)
    _n(name, a, n)
    if a.ndim != 3 or (shape is not None and a.shape[1:] != shape):
        raise ValueError(f"{name}: shape {a.shape} does not match the frames {shape}")
    return a


def _stats(xs):
    v = [x for x in xs if x is not None]
    if not v:
        return {"n": 0, "mean": None, "median": None, "p95": None}
    return {"n": len(v), "mean": float(np.mean(v)), "median": float(np.median(v)), "p95": float(np.percentile(v, 95))}


def _mean(xs):
    v = [x for x in xs if x is not None]
    return float(np.mean(v)) if v else None


def versions():
    from importlib.metadata import version

    from seam.util import ffmpeg_version
    try:
        ff = ffmpeg_version()
    except Exception:   # noqa: BLE001 - ffmpeg missing is recorded, not fatal here
        ff = None
    return {**{p: version(p) for p in ("numpy", "opencv-python", "av", "scipy", "scikit-image")},
            "python": ".".join(map(str, sys.version_info[:3])), "ffmpeg": ff}


# ---- the registered masks -----------------------------------------------------------------------------------
# The registered secondaries measured on their own pairs (§13; call 135): R(t) also without the touched object's take
# mask, and the other two margins. No other extra record enters a measure file.
EXTRA_NAMES = ("interior_excluded", "m48", "m64")


def registered_masks(render_id, takes=TAKES):
    """{take, material, touched, hand} for a registered render, from capture/takes.json: ``touched`` is the take-mask
    name of the touched object (`paste.touched_mask`; None for the breath take) and ``hand`` the hand's take-mask
    name for every take with a touched object (None for the breath take, which has no hand). Refuses the curtain
    call and any id that is not `<take>-<material>` of exactly one rated row."""
    rid = str(render_id)
    if rid == CURTAIN or rid.startswith(CURTAIN + "-"):
        raise ValueError(f"{rid}: t07 is the curtain call, which is never measured for H")
    rows = takes if isinstance(takes, list) else json.loads(Path(takes).read_text())
    take, sep, material = rid.partition("-")
    hits = [r for r in rows if r.get("rated") and r.get("id") == take and r.get("target_material") == material]
    if not sep or len(hits) != 1:
        ids = sorted(f"{r['id']}-{r['target_material']}" for r in rows if r.get("rated"))
        raise ValueError(f"{rid!r} is not a registered render id in capture/takes.json ({', '.join(ids)})")
    touched = (hits[0].get("paste") or {}).get("touched_mask")
    return {"take": take, "material": material, "touched": touched, "hand": None if touched is None else HAND}


def _check_flags(render_id, reg, touched_flag, hand_flag):
    if touched_flag is not None and touched_flag != reg["touched"]:
        raise ValueError(f"--touched {touched_flag!r} contradicts capture/takes.json: {render_id}'s touched object is "
                         f"{reg['touched']!r}")
    if hand_flag is not None and hand_flag != reg["hand"]:
        raise ValueError(f"--hand {hand_flag!r} contradicts capture/takes.json: {render_id}'s hand mask is "
                         f"{reg['hand']!r}" + (" (the breath take has no hand)" if reg["hand"] is None else ""))


def take_masks_for(render_id, reg, path, tm_meta, tm):
    """(touched, hand) mask stacks for the render from its take's p47-masks/1 file, as the registration names them."""
    if not re.fullmatch(re.escape(reg["take"]) + r"[a-z]?", str(tm_meta.get("take"))):
        raise ValueError(f"{path} holds the masks of take {tm_meta.get('take')!r}, not of {reg['take']} ({render_id})")
    if reg["touched"] is None:
        if HAND in tm:
            raise ValueError(f"{path} has a {HAND!r} mask, but {render_id} is the breath take: capture/takes.json "
                             "registers no touched object, and the take has no hand")
        return None, None
    if reg["touched"] not in tm:
        raise ValueError(f"{path} has no object {reg['touched']!r}, {render_id}'s touched object in capture/takes.json; "
                         f"it has {sorted(tm)}")
    return tm[reg["touched"]], tm.get(HAND)


# ---- scored frames and the region ---------------------------------------------------------------------------
def scored_frames(gate_ok, creature, start=None):
    """A frame is scored only if it passed the alignment gate and the mask quality rule
    (masks.quality_ok; ``start`` = the render mask's prompt frame, before which the creature is the
    drawing at home and the frame is valid if the gate passed it)."""
    creature = np.asarray(creature, bool)
    _n("gate.ok", gate_ok, len(creature))
    q = masks.quality_ok(creature, start=start)
    return [bool(g) and bool(x) for g, x in zip(gate_ok, q)]


def region_series(creature, home, m, prompt_frame=None, cover=None):
    """R(t) for every frame: ~dilate(creature ∪ home, m), and before the prompt frame ~dilate(home, m).
    ``cover`` (n,H,W): the pixels the gate's warp covered; the rest leave R(t) (call 126)."""
    pf = 0 if prompt_frame is None else int(prompt_frame)
    R = np.stack([regions.measured_region(c, home, m, at_home=i < pf) for i, c in enumerate(creature)])
    return R if cover is None else R & np.asarray(cover, bool)


def contact_series(creature, touched, hand, ds):
    """{d: [bool per frame]}: c(t) = dilate(creature, d) ∩ (touched ∪ hand) ≠ ∅, from one distance
    transform per frame (dilate(mask, d) is EDT(~mask) <= d)."""
    from scipy.ndimage import distance_transform_edt
    n = len(creature)
    out = {d: [False] * n for d in ds}
    for i in range(n):
        other = np.zeros(creature[i].shape, bool)
        if touched is not None:
            other |= touched[i]
        if hand is not None:
            other |= hand[i]
        if not creature[i].any() or not other.any():
            continue
        near = float(distance_transform_edt(~creature[i])[other].min())
        for d in ds:
            out[d][i] = near <= d
    return out


def redrawn_shares(codes, touched, shape):
    """Per frame, the redrawn share (redrawn / (kept + redrawn)) of the verdict cells inside the touched
    object (a cell its take mask covers at least half) and of the verdict cells outside it. None where
    a side has no verdict cell."""
    n = len(codes)
    area = cells.cell_sums(np.ones(shape, bool))
    obj_s, rest_s = [], []
    for i in range(n):
        verdict = (codes[i] == cells.KEPT) | (codes[i] == cells.REDRAWN)
        inobj = (cells.cell_sums(touched[i]) >= 0.5 * area) if touched is not None else np.zeros(area.shape, bool)
        for sel, out in ((verdict & inobj, obj_s), (verdict & ~inobj, rest_s)):
            k = int(sel.sum())
            out.append(float((codes[i][sel] == cells.REDRAWN).sum() / k) if k else None)
    if touched is None:
        obj_s = [None] * n
    return obj_s, rest_s


def check_gate(gate, n):
    """Refuse a gate that contradicts itself: `pass` must be what align.gate would conclude from the
    per-frame `ok` list, rho, the lag (when applicable) and the duration check, `frames_ok` must be
    mean(ok), and `reason` is null exactly when the render passes. A hand-edited `pass` is caught here."""
    ok = gate.get("ok")
    if ok is None:
        raise ValueError("gate has no per-frame 'ok' list")
    _n("gate.ok", ok, n)
    frac = float(np.mean([bool(v) for v in ok])) if n else 0.0
    fo = gate.get("frames_ok")
    if fo is None or abs(float(fo) - frac) > 1e-9:
        raise ValueError(f"gate frames_ok {fo!r} is not the mean of its ok list ({frac})")
    applicable = gate.get("lag_applicable", True)
    lag = gate.get("lag")
    reasons = []
    if gate.get("rho") is None:
        reasons.append("rho undefined")
    if applicable and not align.lag_ok(lag):
        reasons.append("lag")
    if gate.get("duration_ok", True) is False:
        reasons.append("duration")
    if frac < align.MIN_FRAC and gate.get("rho") is not None:
        reasons.append("frames")
    expected = not reasons
    if bool(gate.get("pass")) != expected:
        raise ValueError(f"gate pass is {bool(gate.get('pass'))} but its own numbers say "
                         f"{'pass' if expected else 'fail (' + ', '.join(reasons) + ')'}")
    if (gate.get("reason") is None) != expected:
        raise ValueError(f"gate reason {gate.get('reason')!r} disagrees with pass {bool(gate.get('pass'))}")


# ---- checking a lines record ----------------------------------------------------------------------------------
def _check_lines(rec, n, name):
    if rec.get("schema") != LINES_SCHEMA:
        raise ValueError(f"{name}: schema {rec.get('schema')!r}, expected {LINES_SCHEMA}")
    for k in ("t", "D", "valid"):
        _n(f"{name}.{k}", rec[k], n)
    if rec.get("D0") is not None:
        _n(f"{name}.D0", rec["D0"], n)


def _check_variant_run(name, rec, render_id, kappa, m):
    """A further lines run must be the same render and κ as the primary. Its margin is the primary's, except
    that a variant named m32 / m48 / m64 is a margin sensitivity run and must have been run at that other margin."""
    where = f"extra_lines[{name}]"
    meta = rec.get("meta") or {}
    if "render" in meta and meta["render"] != render_id:
        raise ValueError(f"{where}: lines record is for render {meta['render']!r}, not {render_id!r}")
    used = (rec.get("params") or {}).get("kappa")
    if used is None or abs(float(used) - kappa) > 1e-12:
        raise ValueError(f"{where}: kappa {used!r} differs from the primary run's {kappa}")
    named = re.fullmatch(r"m(\d+)", name)
    want = int(named.group(1)) if named else m
    if named and (want not in M_CHOICES or want == m):
        raise ValueError(f"{where}: a margin variant must name one of the other margins {[x for x in M_CHOICES if x != m]}")
    if "m" in meta and meta["m"] != want:
        raise ValueError(f"{where}: lines record was run at margin m = {meta['m']}, expected {want}")


def _check_d_scored(rec, name):
    for i, (d, v) in enumerate(zip(rec["D"], rec["valid"])):
        if d is not None and not v:
            raise ValueError(f"{name}: D[{i}] is a number on a frame the job did not score (valid false)")


def _seam_info(lines, seam_file, seam_root, check_files, n):
    sm = lines.get("seam")
    if not sm:
        raise ValueError("lines record has no seam: the job ran without kappa, so no cell was classified")
    cols, rows = int(sm["cols"]), int(sm["rows"])
    root = Path(seam_root)
    f = Path(seam_file if seam_file else sm["file"] or "")
    if not str(f) or str(f) == ".":
        raise ValueError("seam: the lines record names no seam file")
    if f.is_absolute():
        try:
            rel = f.resolve().relative_to(root.resolve())
        except ValueError:
            raise ValueError(f"seam file {f} is outside {root}; pass seam_file relative to the seam root") from None
    else:
        rel = f
    path = root / rel
    stride = -(-rows * cols // 4)
    codes = None
    if check_files:
        if not path.is_file():
            raise ValueError(f"seam file {path} does not exist")
        size = path.stat().st_size
        if size != n * stride:
            raise ValueError(f"seam file {path} is {size} bytes, expected {n} frames x {stride} bytes")
        codes = cells.unpack(path.read_bytes(), rows, cols)
    return {"file": rel.as_posix(), "cols": cols, "rows": rows, "bits": 2, "frames": n}, codes


# ---- the assembly -------------------------------------------------------------------------------------------------
def assemble(render_id, *, lines, gate, creature, touched, hand_mask=None, home, m, kappa_keep, kappa_source,
             prompt_frame=None, R=None, cover=None, take_frames=None, hand_drift=None, ocr_cer=None, extra_lines=None,
             meta=None, seam_file=None, seam_root=REPO, check_files=True, d=regions.CONTACT_PX):
    """The `p47-measure/1` record of one render. ``touched`` (n,H,W) is the touched object's take mask
    (None: the breath take); ``hand_mask`` the hand's; ``home`` (H,W) the acting creature's home;
    ``R``, if given, must equal the region built from the home, m, prompt frame and ``cover`` (the pair's).
    ``render_id`` must be registered, and ``touched`` given exactly when capture/takes.json registers a touched
    object for it; a ``hand_mask`` is refused for the breath take."""
    reg = registered_masks(render_id)
    if (touched is None) != (reg["touched"] is None):
        raise ValueError(f"{render_id}: capture/takes.json registers touched object {reg['touched']!r}, but a touched "
                         f"mask was {'not ' if touched is None else ''}given")
    if hand_mask is not None and reg["hand"] is None:
        raise ValueError(f"{render_id}: a hand mask was given, but the breath take has no hand (capture/takes.json "
                         "registers no touched object)")
    n = len(lines["t"])
    _check_lines(lines, n, "lines")
    if m not in M_CHOICES:
        raise ValueError(f"m must be one of {M_CHOICES}, got {m!r}")
    if kappa_source not in KAPPA_SOURCES:
        raise ValueError(f"kappa_source must be one of {KAPPA_SOURCES}, got {kappa_source!r}")
    kappa = _f(kappa_keep)
    if kappa is None or not 0 < kappa <= 1:
        raise ValueError(f"kappa_keep must be a number in (0, 1], got {kappa_keep!r}")
    used = (lines.get("params") or {}).get("kappa")
    if used is None:
        raise ValueError("lines record has no kappa: cells were not classified (rerun the job with --kappa and --seam)")
    if abs(float(used) - kappa) > 1e-12:
        raise ValueError(f"kappa_keep {kappa} differs from the kappa the lines job classified with ({used})")
    lm = lines.get("meta") or {}
    if "render" in lm and lm["render"] != render_id:
        raise ValueError(f"lines record is for render {lm['render']!r}, not {render_id!r}")
    if "m" in lm and lm["m"] != m:
        raise ValueError(f"lines record was run with m = {lm['m']}, not {m}")

    creature = np.asarray(creature, bool)
    _n("creature", creature, n)
    shape = creature.shape[1:]
    creature = _stack("creature", creature, n, shape)
    touched = None if touched is None else _stack("touched", touched, n, shape)
    hand_mask = None if hand_mask is None else _stack("hand_mask", hand_mask, n, shape)
    home = np.asarray(home, bool)
    if home.shape != shape:
        raise ValueError(f"home: shape {home.shape} does not match the frames {shape}")
    if cover is not None:
        cover = _stack("cover", cover, n, shape)
    region = region_series(creature, home, m, prompt_frame, cover)
    if R is not None:
        R = _stack("R", R, n, shape)
        if not np.array_equal(R, region):
            raise ValueError("R differs from the region built from the home, m, prompt frame and warp cover")
    if take_frames is not None:
        _n("take_frames", take_frames, n)

    check_gate(gate, n)
    ok = gate["ok"]
    want = scored_frames(ok, creature, start=prompt_frame)
    if [bool(v) for v in lines["valid"]] != want:
        bad = [i for i, (a, b) in enumerate(zip(lines["valid"], want)) if bool(a) != b][:5]
        raise ValueError(f"the lines job's valid frames differ from gate + mask quality (scored) at frames {bad}")
    _check_d_scored(lines, "lines")

    D = _fl(lines["D"])
    D0 = _fl(lines["D0"]) if lines.get("D0") is not None else [None] * n
    present = [bool(touched[i].any()) for i in range(n)] if touched is not None else [False] * n
    eligible = [p and x is not None for p, x in zip(present, D)]
    ds = sorted({d, *[v for _, v in VARIANT_D]})
    cs = contact_series(creature, touched, hand_mask, ds)
    contact = cs[d]
    for name, series in (("hand_drift", hand_drift), ("ocr_cer", ocr_cer)):
        if series is not None:
            _n(name, series, n)
    hand = _fl(hand_drift) if hand_drift is not None else [None] * n
    ocr = _fl(ocr_cer) if ocr_cer is not None else [None] * n
    motion = [None] + [_f(x) for x in align.motion_energy(take_frames, region)] if take_frames is not None else [None] * n

    seam, codes = _seam_info(lines, seam_file, seam_root, check_files, n)
    if codes is not None:
        r_obj, r_rest = redrawn_shares(codes, touched, shape)
    else:
        r_obj, r_rest = [None] * n, [None] * n

    variants = {name: {"D": list(D), "contact": cs[v], "eligible": list(eligible)} for name, v in VARIANT_D}
    for name, rec in sorted((extra_lines or {}).items()):
        _check_lines(rec, n, f"extra_lines[{name}]")
        _check_variant_run(name, rec, render_id, kappa, m)
        if [bool(v) for v in rec["valid"]] != [bool(v) for v in lines["valid"]]:
            raise ValueError(f"extra_lines[{name}]: valid frames differ from the primary run")
        _check_d_scored(rec, f"extra_lines[{name}]")
        vd = _fl(rec["D"])
        variants[name] = {"D": vd, "contact": list(contact), "eligible": [p and x is not None for p, x in zip(present, vd)]}

    series = {"t": [float(x) for x in lines["t"]], "D": D, "D0": D0, "contact": contact, "eligible": eligible,
              "hand": hand, "ocr_cer": ocr, "motion": motion, "redrawn_object": r_obj, "redrawn_rest": r_rest}
    lp = {k: lines.get(k) for k in ("inkstab_version", "stilldrawn", "netG_sha256", "device", "device_registered",
                                     "device_override")}
    params = {"m": int(m), "d": int(d), "tau": cells.TAU, "cell": cells.CELL, "fps": FPS, "kappa_keep": kappa,
              "kappa_source": kappa_source, "min_px": cells.MIN_PX, "prompt_frame": prompt_frame,
              "versions": versions(), "lines": lp,
              "gate": {"params": gate.get("params"), "versions": gate.get("versions")}, "assembler": ASSEMBLER}
    rec = {"schema": SCHEMA, "render": render_id, "meta": dict(meta or {}),
           "align": {"pass": bool(gate.get("pass")), "lag": gate.get("lag"), "rho": _f(gate.get("rho")),
                     "frames_ok": _f(gate.get("frames_ok")), "reason": gate.get("reason"),
                     "lag_source": gate.get("lag_source"), "lag_applicable": bool(gate.get("lag_applicable", True)),
                     "lag_reason": gate.get("lag_reason"), "duration_ok": bool(gate.get("duration_ok", True)),
                     "lag_energy_mean": _f(gate.get("lag_energy_mean"))},
           "params": params, "series": series, "variants": variants, "seam": seam,
           "summary": _summary(series, lines, kappa)}
    validate_measure(rec)
    return rec


def _summary(series, lines, kappa):
    from analysis.h_contact import render_r
    D, c, e = series["D"], series["contact"], series["eligible"]
    r, nc, nn = render_r(D, c, e)
    counts = {k: 0 for k in ("none", "kept", "redrawn", "creature")}
    for cc in lines.get("cell_counts") or []:
        for k in counts:
            counts[k] += int(cc[k])
    verdict = counts["kept"] + counts["redrawn"]
    counts["redrawn_share"] = counts["redrawn"] / verdict if verdict else None
    homes = {}
    for name, v in (lines.get("homes") or {}).items():
        homes[name] = {"D": _stats(_fl(v))["median"],
                       "D0": _stats(_fl((lines.get("homes_null") or {}).get(name, [])))["median"]}
    return {"n_frames": len(D), "n_scored": sum(x is not None for x in D), "n_eligible": int(sum(e)),
            "n_contact": int(sum(c)), "n_eligible_contact": nc, "n_eligible_noncontact": nn, "r": r,
            "D": _stats(D), "D0": _stats(series["D0"]), "cells": counts, "homes": homes,
            "hand_mean": _mean(series["hand"]), "ocr_cer_mean": _mean(series["ocr_cer"]),
            "motion_mean": _mean(series["motion"]), "density_mean": _mean(_fl(lines.get("density") or [])),
            "scan_chamfer_mean": _mean(_fl(lines.get("scan_chamfer") or [])),
            "kappa_render_p1": _f(lines.get("kappa_render_p1")), "kappa_codec": _f(lines.get("kappa_codec")),
            "kappa_keep": kappa}


# ---- validation and writing ------------------------------------------------------------------------------------------
def validate_measure(rec):
    """Raise ValueError unless rec is a well-formed p47-measure/1 (what h_contact reads and the web view needs)."""
    if rec.get("schema") != SCHEMA:
        raise ValueError(f"schema {rec.get('schema')!r}, expected {SCHEMA}")
    if not isinstance(rec.get("render"), str) or not rec["render"]:
        raise ValueError("render id missing")
    for key, need in (("align", ALIGN_KEYS), ("params", PARAM_KEYS), ("seam", SEAM_KEYS)):
        sec = rec.get(key)
        if not isinstance(sec, dict):
            raise ValueError(f"{key} missing")
        for k in need:
            if k not in sec:
                raise ValueError(f"{key}.{k} missing")
    p = rec["params"]
    if not isinstance(p["versions"], dict) or not p["versions"]:
        raise ValueError("params.versions must be a non-empty map")
    if p["kappa_source"] not in KAPPA_SOURCES:
        raise ValueError(f"params.kappa_source {p['kappa_source']!r} not in {KAPPA_SOURCES}")
    if _f(p["kappa_keep"]) is None:
        raise ValueError("params.kappa_keep is not a finite number")
    s = rec.get("series")
    if not isinstance(s, dict):
        raise ValueError("series missing")
    for k in SERIES_KEYS:
        if k not in s:
            raise ValueError(f"series.{k} missing")
    n = len(s["t"])
    for k, v in s.items():
        if len(v) != n:
            raise ValueError(f"series length differs: {k} has {len(v)}, t has {n}")
    for k in NUMERIC_SERIES:
        for i, x in enumerate(s.get(k, [])):
            if x is not None and (isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)):
                raise ValueError(f"series {k}[{i}] = {x!r} is not a finite number or None")
    for k in BOOL_SERIES:
        for i, x in enumerate(s[k]):
            if not isinstance(x, bool):
                raise ValueError(f"series {k}[{i}] = {x!r} is not a bool")
    for name, v in rec.get("variants", {}).items():
        for k in ("D", "contact", "eligible"):
            if len(v.get(k, [])) != n:
                raise ValueError(f"variant {name}: length of {k} differs from the {n} frames")
    return rec


def write_measure(rec, path):
    validate_measure(rec)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=1, sort_keys=True, allow_nan=False) + "\n")
    return path


def meta_for(recs, materials):
    """The META file h_contact reads for the ink-only secondary: {render: {material}}."""
    return {r["render"]: {"material": materials[r["render"]]} for r in recs}


# ---- command line --------------------------------------------------------------------------------------------------------
def _load_json(p):
    return json.loads(Path(p).read_text())


def main(argv=None):
    from seam import pairs
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--render", required=True)
    ap.add_argument("--pair", required=True, help="the pair npz the lines job measured (take, creature, homes)")
    ap.add_argument("--lines", required=True)
    ap.add_argument("--gate", required=True)
    ap.add_argument("--take-masks", help="the take's p47-masks/1 file (required unless the take has no touched object)")
    ap.add_argument("--touched", help="optional check: refused unless it is the touched object capture/takes.json names")
    ap.add_argument("--hand", help=f"optional check: refused unless it is {HAND!r} for a take with a touched object")
    ap.add_argument("--home", help="home name in the pair (default: the acting home its writer named, else its only home)")
    ap.add_argument("--m", type=int, required=True)
    ap.add_argument("--kappa", type=float, required=True)
    ap.add_argument("--kappa-source", required=True)
    ap.add_argument("--prompts", required=True,
                    help="the render mask's final prompt file; its first creature point is the blind pick")
    ap.add_argument("--hand-drift")
    ap.add_argument("--ocr")
    ap.add_argument("--extra", action="append", default=[], metavar="NAME=LINES.json")
    ap.add_argument("--meta", help="JSON map merged into the record's meta")
    ap.add_argument("--seam-root", default=str(REPO))
    ap.add_argument("--seam-file")
    ap.add_argument("--no-check-files", action="store_true")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        reg = registered_masks(a.render)
        _check_flags(a.render, reg, a.touched, a.hand)
        from seam import points
        P = pairs.read_pair(a.pair)
        # every render's prompt frame is the blind pick, and its creature mask the logged final track (call 106)
        if P["creature"] is None:
            raise ValueError("the pair has no creature mask")
        pf = points.custody(a.render, prompts=a.prompts, pair_meta=P["meta"], creature=P["creature"])
        n, shape = len(P["t"]), P["take"].shape[1:3]
        gate = _load_json(a.gate)
        from seam import blind
        if blind.sha256_json(gate) != P["meta"]["gate"]["sha256"]:
            raise ValueError("the gate file is not the gate the pair was built under")
        reg_home = f"home_{reg['material']}"
        if a.home is not None and a.home not in (P["meta"].get("home"), reg_home, reg["material"]):
            raise ValueError(f"--home {a.home!r} is not {a.render}'s home ({reg_home}; call 135)")
        name = a.home or P["meta"].get("home")
        if name is None and len(P["homes"]) == 1:
            home = next(iter(P["homes"].values()))
        elif name in P["homes"]:
            home = P["homes"][name]
        else:
            raise ValueError(f"name the home with --home; the pair has {sorted(P['homes'])}")
        touched = hand = None
        if a.take_masks:
            tm_meta, tm = masks.load_masks(a.take_masks)
            touched, hand = take_masks_for(a.render, reg, a.take_masks, tm_meta, tm)
            if a.hand is not None and hand is None:
                raise ValueError(f"{a.take_masks} has no object {a.hand!r}; it has {sorted(tm)}")
        elif reg["touched"] is not None:
            raise ValueError(f"--take-masks is required: capture/takes.json registers {a.render}'s touched object "
                             f"{reg['touched']!r}")
        if masks.prompt_frame(masks.load_prompts(a.prompts, shape, n), "creature") != pf:
            raise ValueError("the prompt file's first creature frame is not the blind pick")
        extra = {}
        for e in a.extra:
            name, _, path = e.partition("=")
            if name not in EXTRA_NAMES:
                raise ValueError(f"--extra {name!r} is not a registered extra record ({', '.join(EXTRA_NAMES)}; call 135)")
            extra[name] = _load_json(path)
        rec = assemble(a.render, lines=_load_json(a.lines), gate=gate, creature=P["creature"],
                       touched=touched, hand_mask=hand, home=home, m=a.m, kappa_keep=a.kappa,
                       kappa_source=a.kappa_source, prompt_frame=pf, R=P["R"], cover=P["cover"], take_frames=P["take"],
                       hand_drift=_load_json(a.hand_drift) if a.hand_drift else None,
                       ocr_cer=_load_json(a.ocr) if a.ocr else None, extra_lines=extra or None,
                       meta=_load_json(a.meta) if a.meta else None, seam_file=a.seam_file,
                       seam_root=a.seam_root, check_files=not a.no_check_files)
        write_measure(rec, a.out)
    except (ValueError, KeyError, OSError) as e:
        print(f"assemble: refuse: {e}", file=sys.stderr)
        return 1
    print(f"{a.render}: {rec['summary']['n_scored']}/{rec['summary']['n_frames']} scored, "
          f"{rec['summary']['n_eligible']} eligible, r = {rec['summary']['r']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
