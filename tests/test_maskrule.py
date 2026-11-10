"""The A9.4 frame rule (P46 plan), as P47 uses it: a = render, b = take, R = measured region."""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.ndimage import distance_transform_edt as edt

from seam.maskrule import frame_rule, frame_rule_dt

STILLDRAWN = Path("/Users/aaron/projects/stilldrawn")
# P46's masked rule (metrics/masked.py) lives in the public StillDrawn tree once released, and before that in
# P46's working checkout, which the studio hub links under repos/: every linked checkout that has one is tested.
REPO_LINKS = Path("/Users/aaron/projects/studio/repos")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(path).parent))      # masked.py imports inkstab beside it
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return mod


def _sparse(rng, shape=(72, 128), p=0.02):
    return rng.random(shape) < p


def test_empty_maps_score_none():
    a = np.zeros((20, 20), bool)
    b = np.zeros((20, 20), bool)
    b[5, 5] = True
    R = np.ones((20, 20), bool)
    assert frame_rule(a, b, R) is None
    assert frame_rule(b, a, R) is None


def test_vanished_lines_score_one_sided_term():
    a = np.zeros((40, 40), bool)
    b = np.zeros((40, 40), bool)
    a[:, 2] = True                       # render lines only outside R
    b[:, 30] = True                      # take line inside R
    R = np.zeros((40, 40), bool)
    R[:, 20:] = True
    v = frame_rule(a, b, R)
    assert v == float(edt(~a)[b & R].mean())
    assert v == pytest.approx(28.0)


def test_mirror_and_both_empty():
    a = np.zeros((40, 40), bool)
    b = np.zeros((40, 40), bool)
    a[:, 30] = True                      # render line appeared inside R
    b[:, 2] = True                       # take lines outside R
    R = np.zeros((40, 40), bool)
    R[:, 20:] = True
    assert frame_rule(a, b, R) == float(edt(~b)[a & R].mean())
    R2 = np.zeros((40, 40), bool)
    R2[:, 10:20] = True                  # neither map has lines here
    assert frame_rule(a, b, R2) is None


def test_symmetric_case_and_shift_of_three():
    a = np.zeros((60, 200), bool)
    b = np.zeros((60, 200), bool)
    for x in (20, 60, 100, 140):
        b[:, x] = True
        a[:, x + 3] = True
    assert frame_rule(a, b, np.ones_like(a)) == pytest.approx(3.0)


def test_dt_form_equals_direct_form():
    rng = np.random.default_rng(1)
    for _ in range(20):
        a, b = _sparse(rng), _sparse(rng)
        R = rng.random(a.shape) < 0.5
        assert frame_rule_dt(a, b, edt(~b), edt(~a), R) == frame_rule(a, b, R)


@pytest.mark.skipif(not (STILLDRAWN / "metrics/inkstab.py").exists(), reason="no stilldrawn checkout")
def test_all_true_region_equals_frozen_chamfer_bit_for_bit():
    inkstab = _load(STILLDRAWN / "metrics/inkstab.py", "p47_inkstab_ref")
    rng = np.random.default_rng(2)
    for _ in range(20):
        a, b = _sparse(rng), _sparse(rng)
        assert frame_rule(a, b, np.ones(a.shape, bool)) == inkstab._chamfer(a, b)
    z = np.zeros((10, 10), bool)
    assert inkstab._chamfer(z, z) is None and frame_rule(z, z, np.ones_like(z)) is None


def _masked_rules():
    found = [STILLDRAWN / "metrics/masked.py"]
    if REPO_LINKS.is_dir():
        found += sorted(d / "metrics/masked.py" for d in REPO_LINKS.iterdir())
    out = {}
    for p in found:
        if p.exists():
            out.setdefault(p.resolve(), p)
    return list(out.values())


MASKED = _masked_rules()


@pytest.mark.skipif(not MASKED, reason="masked.py does not exist yet")
@pytest.mark.parametrize("path", MASKED, ids=[f"masked{i}" for i in range(len(MASKED))])
def test_equals_masked_py(path):
    masked = _load(path, f"p47_masked_{abs(hash(str(path)))}")
    rng = np.random.default_rng(3)
    seen = set()
    for i in range(60):
        a, b = _sparse(rng, p=0.01), _sparse(rng, p=0.01)
        R = np.zeros(a.shape, bool)
        k = i % 4
        if k == 0:
            R[:] = True
        elif k == 1:
            R[:, 64:] = True
            a[:, 64:] = False            # vanished
        elif k == 2:
            R[:, 64:] = True
            b[:, 64:] = False            # mirror
        else:
            R[:, 64:] = True
            a[:, 64:] = False
            b[:, 64:] = False            # both empty in R
        mine, theirs = frame_rule(a, b, R), masked.masked_chamfer(a, b, R)
        assert mine == theirs
        seen.add(k)
    assert seen == {0, 1, 2, 3}
