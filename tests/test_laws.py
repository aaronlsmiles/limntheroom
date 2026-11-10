"""seam.laws: load and validate p47-laws/1. Fixture laws only: the real ones stay sealed."""
import copy
import json
from pathlib import Path

import pytest

from seam import laws

FIX = Path(__file__).parent / "fixtures" / "laws_fixture.json"


def _raw():
    return json.loads(FIX.read_text())


def test_loads_fixture():
    L = laws.load_laws(FIX)
    assert laws.get_law(L, "ink.pen")["clause"] == "spins on the spot like a top (fixture)"
    assert sorted(L["materials"]) == ["gold", "ink", "paper"]


def test_unknown_law_errors():
    L = laws.load_laws(FIX)
    with pytest.raises(laws.UnknownLaw) as ei:
        laws.get_law(L, "gold.light")
    assert "gold.light" in str(ei.value)
    assert isinstance(ei.value, KeyError)


def test_rejects_felt():
    d = _raw()
    d["materials"]["felt"] = {"look": "a felt cut-out"}
    d["laws"].append({"id": "felt.hand", "material": "felt", "cue": "hand", "behaviour": "x",
                      "label": "Felt thing (fixture)", "clause": "spins when it hears a bell", "touches": None,
                      "rated": False})
    with pytest.raises(ValueError, match="felt"):
        laws.validate_laws(d)


def _mut(fn):
    d = _raw()
    fn(d)
    return d


@pytest.mark.parametrize("d", [
    _mut(lambda d: d["laws"][0].update(id="ink-pen")),                              # id not <material>.<cue>
    _mut(lambda d: d["laws"][0].update(id="ink.bell", cue="bell")),                 # unknown cue
    _mut(lambda d: d["laws"].append(copy.deepcopy(d["laws"][0]))),                  # duplicate id
    _mut(lambda d: d.pop("salt")),                                                  # missing salt
    _mut(lambda d: d.update(salt="")),                                              # empty salt
    _mut(lambda d: d.update(extra=1)),                                              # extra key
    _mut(lambda d: d["laws"][0].update(extra=1)),                                   # extra law key
    _mut(lambda d: d.update(decoys=[d["laws"][0]["label"], "Decoy B (fixture)"])),  # decoy equals a label
    _mut(lambda d: d.update(decoys=["Decoy A (fixture)"])),                         # not exactly two
    _mut(lambda d: d.update(decoys=["Same", "Same"])),                              # not distinct
    _mut(lambda d: d["laws"][0].update(rated="yes")),                               # rated not bool
    _mut(lambda d: d["laws"][0].update(clause=" ")),                                # empty clause
    _mut(lambda d: d["laws"][0].update(clause="spins. Then a new sentence")),       # clause must be one phrase
    _mut(lambda d: d["materials"]["ink"].update(look="")),                          # empty look
    _mut(lambda d: d["laws"][0].update(touches=5)),                                 # touches str or null
])
def test_rejects(d):
    with pytest.raises(ValueError):
        laws.validate_laws(d)


def test_canonical_sha256():
    a = _raw()
    b = json.loads(json.dumps(a), object_pairs_hook=lambda kv: dict(reversed(kv)))
    assert laws.canonical_sha256(a) == laws.canonical_sha256(b)
    b["salt"] = "other"
    assert laws.canonical_sha256(a) != laws.canonical_sha256(b)


def test_load_rejects_bad_json(tmp_path):
    p = tmp_path / "l.json"
    p.write_text("{")
    with pytest.raises(ValueError):
        laws.load_laws(p)
