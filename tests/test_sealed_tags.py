"""Gate R review F1 (call 136): every rated law's sealed contact tag names its take's public touched object (§13).

The tags are sealed; the public name is `touched_object` in capture/takes.json. Where the tag names the same object in
other words (one cell, call 135 item 1), the sealed alias table `sealed/tag-aliases.json` maps that cell to the public
name. Runs only where the sealed files exist; failures name cell ids only, never the text."""
import json
from pathlib import Path

import pytest

from seam.compile import TAKE_CUE

ROOT = Path(__file__).resolve().parent.parent
LAWS = ROOT / "sealed" / "laws.json"
ALIASES = ROOT / "sealed" / "tag-aliases.json"

no_sealed = pytest.mark.skipif(not LAWS.exists(), reason="no sealed laws here")


def mismatches(laws, takes, aliases):
    """Cell ids whose tag (or its alias) does not name the touched object of the take row its cue and material pick."""
    by_cell = {}
    for row in takes:
        if row.get("rated"):
            by_cell[f"{row['target_material']}.{TAKE_CUE[row['cue']]}"] = row.get("touched_object")
    bad = []
    for law in laws["laws"]:
        if not law["rated"]:
            continue
        cell, tag = law["id"], law.get("touches")
        public = by_cell.get(cell)
        if (tag is None) != (public is None):
            bad.append(cell)
        elif tag is not None and tag != public and aliases.get(cell) != public:
            bad.append(cell)
    return sorted(bad)


def test_mismatches_reports_cell_ids_only():
    laws = {"laws": [{"id": "ink.water", "rated": True, "touches": "glass"},
                     {"id": "ink.light", "rated": True, "touches": "secret words"},
                     {"id": "ink.breath", "rated": True, "touches": None}]}
    takes = [{"rated": True, "target_material": "ink", "cue": "glass", "touched_object": "glass"},
             {"rated": True, "target_material": "ink", "cue": "torch", "touched_object": "standing object"},
             {"rated": True, "target_material": "ink", "cue": "breath", "touched_object": None}]
    assert mismatches(laws, takes, {}) == ["ink.light"]
    assert mismatches(laws, takes, {"ink.light": "standing object"}) == []


@no_sealed
def test_every_sealed_tag_names_its_takes_touched_object():
    laws = json.loads(LAWS.read_text())
    takes = json.loads((ROOT / "capture" / "takes.json").read_text())
    aliases = json.loads(ALIASES.read_text())["aliases"] if ALIASES.exists() else {}
    assert mismatches(laws, takes, aliases) == [], "sealed tags that name no public touched object (cell ids only)"
    assert len(aliases) <= 1                                     # one alias, the torch take's (call 135 item 1)
