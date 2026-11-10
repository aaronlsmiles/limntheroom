"""Load and validate a laws file in ``p47-laws/1`` (JSON):

    {salt, materials: {ink|gold|paper: {look}},
     laws: [{id: "<material>.<cue>", material, cue, behaviour, label, clause, touches, rated}],
     decoys: [label, label]}

- ``look`` completes the style-lock sentence "The <material> drawing stays <look>."
- ``clause`` is one verb phrase completing "At <t> s, when <what>, it <clause>." (no full stop).
- ``label`` is the rater-facing behaviour label (Q2); ``decoys`` are two labels from unrendered cells.
- ``touches`` names the touched object (the contact tag for H), or null.

The real laws file lives only in the gitignored ``sealed/`` folder until the rating window closes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .cues.sheet import CUES, MATERIALS

TOP_KEYS = {"salt", "materials", "laws", "decoys"}
LAW_KEYS = {"id", "material", "cue", "behaviour", "label", "clause", "touches", "rated"}


class UnknownLaw(KeyError, ValueError):
    """A KeyError (a missing key in the laws) that is also a ValueError (bad input to the compiler)."""

    def __str__(self):
        return f"no law {self.args[0]!r} in the laws file"


def _text(x) -> bool:
    return isinstance(x, str) and bool(x.strip())


def validate_laws(d: dict) -> dict:
    def bad(msg):
        raise ValueError(f"laws: {msg}")

    if not isinstance(d, dict) or set(d) != TOP_KEYS:
        bad(f"top-level keys must be exactly {sorted(TOP_KEYS)}")
    if not _text(d["salt"]):
        bad("salt must be a non-empty string")
    mats = d["materials"]
    if not isinstance(mats, dict) or not mats:
        bad("materials must be a non-empty object")
    for m, v in mats.items():
        if m not in MATERIALS:
            bad(f"material {m!r} is not one of {MATERIALS}")
        if not isinstance(v, dict) or set(v) != {"look"} or not _text(v["look"]):
            bad(f"material {m!r} needs exactly a non-empty 'look'")
    if not isinstance(d["laws"], list) or not d["laws"]:
        bad("laws must be a non-empty list")
    seen, labels = set(), set()
    for law in d["laws"]:
        if not isinstance(law, dict) or set(law) != LAW_KEYS:
            bad(f"each law needs exactly {sorted(LAW_KEYS)}")
        lid = law["id"]
        if law["material"] not in mats:
            bad(f"{lid}: material {law['material']!r} is not in materials")
        if law["cue"] not in CUES:
            bad(f"{lid}: cue {law['cue']!r} is not one of {CUES}")
        if lid != f"{law['material']}.{law['cue']}":
            bad(f"id {lid!r} must be '<material>.<cue>'")
        if lid in seen:
            bad(f"duplicate law {lid}")
        seen.add(lid)
        for k in ("behaviour", "label", "clause"):
            if not _text(law[k]):
                bad(f"{lid}: {k} must be a non-empty string")
        if "." in law["clause"]:
            bad(f"{lid}: clause must be one phrase without a full stop")
        if law["touches"] is not None and not _text(law["touches"]):
            bad(f"{lid}: touches must be a non-empty string or null")
        if not isinstance(law["rated"], bool):
            bad(f"{lid}: rated must be true or false")
        labels.add(law["label"])
    dec = d["decoys"]
    if not (isinstance(dec, list) and len(dec) == 2 and all(_text(x) for x in dec) and dec[0] != dec[1]):
        bad("decoys must be two distinct non-empty labels")
    if set(dec) & labels:
        bad("a decoy repeats a law's label")
    return d


def load_laws(path) -> dict:
    p = Path(path)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{p.name}: not valid JSON ({e})") from None
    return validate_laws(d)


def get_law(laws: dict, law_id: str) -> dict:
    for law in laws["laws"]:
        if law["id"] == law_id:
            return law
    raise UnknownLaw(law_id)


def canonical_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                          .encode("utf-8")).hexdigest()
