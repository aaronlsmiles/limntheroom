"""Leak guard: no git-tracked file may contain the sealed laws' text.

Runs only where ``sealed/laws.json`` exists (Aaron's machine, before the rating window closes). It reads
the sealed strings at run time, so this file itself holds none of them."""
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SEALED = ROOT / "sealed" / "laws.json"

no_sealed = pytest.mark.skipif(not SEALED.exists(), reason="no sealed laws here")


GENERIC_TOUCHES = {"glass", "hand", "note", "pen"}    # objects every take shows; not law text


def _table_cells(md):
    """Behaviour, Q2 label and clause cells of every row of the sealed 18-cell table (review, call 135: the
    unrated cells live only in LAWS.md)."""
    rows = [r for r in md.splitlines() if r.startswith("|") and not r.startswith("|---")]
    if not rows:
        return set()
    head = [c.strip().lower() for c in rows[0].strip("|").split("|")]
    want = [i for i, h in enumerate(head) if h.startswith(("behaviour", "q2 label", "clause"))]
    out = set()
    for r in rows[1:]:
        cells = [c.strip() for c in r.strip("|").split("|")]
        out |= {cells[i] for i in want if i < len(cells)}
    return out


def _needles():
    d = json.loads(SEALED.read_text())
    out = {d["salt"]}
    for law in d["laws"]:
        out |= {law["clause"], law["behaviour"], law["label"]}
        if law.get("touches") and law["touches"].lower() not in GENERIC_TOUCHES:
            out.add(law["touches"])
    out |= set(d["decoys"])
    table = SEALED.parent / "LAWS.md"
    if table.exists():
        out |= _table_cells(table.read_text())
    return sorted(s.lower() for s in out if len(s) >= 6)


def test_table_cells_reads_behaviour_label_and_clause_columns():
    md = "| # | Cell | Behaviour (x) | Q2 label | Clause (y) | Touches |\n|---|---|---|---|---|---|\n| 1 | a.b | B1 | L1 | C1 | t |"
    assert _table_cells(md) == {"B1", "L1", "C1"}


def _tracked_and_staged():
    r = subprocess.run(["git", "ls-files", "--cached", "-z"], cwd=ROOT, capture_output=True, check=True)
    return [ROOT / p for p in r.stdout.decode().split("\0") if p]


def find_leaks(paths, needles, root):
    """[(relative path, "needle #i")]: a hit names the needle by its index only, never its text."""
    hits = []
    for p in paths:
        rel = Path(p).resolve().relative_to(Path(root).resolve())
        if rel.parts[:1] == ("sealed",):
            hits.append((str(rel), "a sealed/ path is tracked"))
            continue
        try:
            text = Path(p).read_text(encoding="utf-8").lower()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        hits += [(str(rel), f"needle #{i}") for i, n in enumerate(needles) if n in text]
    return hits


def test_find_leaks_reports_index_not_text(tmp_path):
    needles = ["alpha secret phrase", "beta hidden words"]
    (tmp_path / "a.md").write_text("intro BETA HIDDEN WORDS outro")
    (tmp_path / "b.md").write_text("nothing here")
    hits = find_leaks([tmp_path / "a.md", tmp_path / "b.md"], needles, tmp_path)
    assert hits == [("a.md", "needle #1")]
    assert not any(n in repr(hits).lower() for n in needles)


@no_sealed
def test_no_tracked_file_contains_sealed_text():
    hits = find_leaks(_tracked_and_staged(), _needles(), ROOT)
    assert hits == [], f"sealed text in tracked files (needle indices only): {hits}"


def commit_message_leaks(text, needles):
    """Needle indices found in commit messages (indices only, never the text)."""
    low = text.lower()
    return [f"needle #{i}" for i, n in enumerate(needles) if n in low]


def test_commit_message_scan_reports_index_not_text():
    assert commit_message_leaks("Fix: ALPHA SECRET PHRASE in a log", ["alpha secret phrase", "beta"]) == ["needle #0"]


@no_sealed
def test_no_commit_message_contains_sealed_text():
    r = subprocess.run(["git", "log", "--all", "--format=%B"], cwd=ROOT, capture_output=True, check=True)
    hits = commit_message_leaks(r.stdout.decode("utf-8", "replace"), _needles())
    assert hits == [], f"sealed text in commit messages (needle indices only): {hits}"
