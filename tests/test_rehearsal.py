"""The end-to-end synthetic rehearsal (tools/rehearse.py): every stage of the measurement chain in order, in a
throwaway repo, with stub blind answers and no paid or live call. Slow (SAM 2.1 on CPU), so it is deselected
by default; run it alone:

    uv run pytest -m rehearsal tests/test_rehearsal.py            # the lines job faked in this venv
    P47_REHEARSAL_LINES=comfy uv run pytest -m rehearsal tests/test_rehearsal.py    # the real lines job
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

pytestmark = pytest.mark.rehearsal


def test_the_whole_chain_runs_on_synthetic_footage(tmp_path):
    import rehearse
    if not (ROOT / "models" / "sam2.1_hiera_small.pt").exists():
        pytest.skip("SAM 2.1 checkpoint missing (models/MODELS.md)")
    lines = os.environ.get("P47_REHEARSAL_LINES", "fake")
    r = rehearse.Rehearsal(tmp_path / "repo", rehearse.default_neutral(), 6.0, lines)
    rep = r.run()
    assert [s["stage"] for s in rep["stages"] if not s["ok"]] == []
    f = rep["findings"]
    assert f["gate"]["pass"] is True
    leave = rehearse.timeline(6.0)[0]
    assert leave * 15 <= f["prompt_frame"] <= leave * 15 + 30          # clear of home after it leaves; never before
    assert f["pair"]["valid"] > 0.8 * f["pair"]["frames"]
    assert f["measure"]["n_contact"] > 0 and f["measure"]["n_eligible"] > 0
    assert f["h"]["byte_identical_rerun"] is True and f["h"]["verdict"] == "not testable"     # one render of four needed
    assert f["rating"]["studies"] == 2
