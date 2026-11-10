"""vendor/ and agents/ hold byte copies of hub files; their SOURCE.md rows must match the bytes."""
import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HUB = ROOT.parent.parent          # ~/projects/studio, when this repo sits in the hub's prototypes/
ROW = re.compile(r"^\| `([^`]+)` \| `([^`]+)` \| `([^`]+)` \| `([0-9a-f]{64})` \|$")


def rows(source):
    out = [ROW.match(line).groups() for line in source.read_text(encoding="utf-8").splitlines() if ROW.match(line)]
    assert out, f"{source} has no rows"
    return out


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


SOURCES = [ROOT / "vendor" / "runway" / "SOURCE.md", ROOT / "agents" / "SOURCE.md"]
CASES = [(s, *r) for s in SOURCES for r in rows(s)]


@pytest.mark.parametrize("source,name,hub_path,commit,digest", CASES, ids=lambda v: str(v)[-24:])
def test_copy_matches_its_row(source, name, hub_path, commit, digest):
    assert sha(source.parent / name) == digest
    assert commit == "uncommitted" or re.fullmatch(r"[0-9a-f]{40}", commit)


@pytest.mark.parametrize("source,name,hub_path,commit,digest", CASES, ids=lambda v: str(v)[-24:])
def test_hub_file_still_matches(source, name, hub_path, commit, digest):
    hub_file = HUB / hub_path
    if not (HUB / "AGENTS.md").exists() or not hub_file.exists():
        pytest.skip("no hub here (a public clone)")
    assert sha(hub_file) == digest, f"{hub_path} changed in the hub since it was vendored"


def test_every_vendored_file_has_a_row():
    for src in SOURCES:
        listed = {r[0] for r in rows(src)}
        present = {p.name for p in src.parent.iterdir() if p.is_file() and p.name not in ("SOURCE.md", "README.md") and p.suffix in (".py", ".md")}
        assert present == listed, src
