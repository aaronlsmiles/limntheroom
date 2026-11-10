"""seam/lines_job.py measure refuses a render whose blind custody is incomplete, before any line map."""
import argparse

import numpy as np
import pytest

from blindkit import custody_chain
from seam import lines_job, pairs

N, H, W = 6, 36, 64


def pair(tmp_path, render, creature, meta=None):
    take = np.zeros((N, H, W, 3), np.uint8)
    return pairs.write_pair(tmp_path / f"{render}.npz", take=take, render=take, valid=np.ones(N, bool),
                            R=np.ones((N, H, W), bool), t=np.arange(N) / 15, creature=creature,
                            meta={"render": render, **(meta or {})})


def args(p, render, prompts=None):
    return argparse.Namespace(pair=str(p), render=render, prompts=prompts)


def creature():
    c = np.zeros((N, H, W), bool)
    c[2:, 10:20, 30:40] = True
    return c


def test_a_render_with_its_committed_custody_passes(tmp_path):
    c = custody_chain(tmp_path / "c", "t01-ink", creature=creature(), frame=2)
    lines_job.check_custody(args(pair(tmp_path, "t01-ink", creature(), c["meta"]), "t01-ink", c["prompts"]))


@pytest.mark.parametrize("case", ["no-prompts", "other-digest", "other-file", "other-render", "dirty-ledger"])
def test_measure_refuses_without_custody(tmp_path, case):
    c = custody_chain(tmp_path / "c", "t01-ink", creature=creature(), frame=2)
    meta = dict(c["meta"])
    if case == "other-digest":
        meta["render_mask_digest"] = "0" * 64
    if case == "other-file":
        meta["render_mask_file_sha256"] = "0" * 64
    if case == "dirty-ledger":
        from seam import frame_pick
        lp = frame_pick.log_path("t01-ink")
        lp.write_text(lp.read_text() + " ")
    p = pair(tmp_path, "t01-ink", creature(), meta)
    with pytest.raises(SystemExit, match="refuse"):
        lines_job.check_custody(args(p, "t02-ink" if case == "other-render" else "t01-ink",
                                     None if case == "no-prompts" else c["prompts"]))


def test_only_the_registered_noop_with_its_manifest_hash_is_exempt(tmp_path, monkeypatch):
    p = pair(tmp_path, lines_job.NOOP_ID, None, {"video_sha256": "a" * 64})
    with pytest.raises(SystemExit, match="registered no-op"):
        lines_job.check_custody(args(p, lines_job.NOOP_ID))                    # no MANIFEST.sha256 yet: closed
    man = tmp_path / "MANIFEST.sha256"
    man.write_text(f"{'a' * 64}  {lines_job.NOOP_MANIFEST_ROW}\n")
    monkeypatch.setattr(lines_job, "MANIFEST", man)
    lines_job.check_custody(args(p, lines_job.NOOP_ID))
    with pytest.raises(SystemExit, match="refuse"):
        lines_job.check_custody(args(pair(tmp_path, "t02-noop", None, {"video_sha256": "a" * 64}), "t02-noop"))
    with pytest.raises(SystemExit, match="creature"):
        lines_job.check_custody(args(pair(tmp_path, lines_job.NOOP_ID, creature(), {"video_sha256": "a" * 64}),
                                     lines_job.NOOP_ID))


def test_cmd_measure_checks_custody_before_any_line_map(tmp_path):
    p = pair(tmp_path, "t01-ink", creature())
    with pytest.raises(SystemExit, match="refuse"):
        lines_job.cmd_measure(argparse.Namespace(**vars(args(p, "t01-ink")), seam=None, kappa=None, null=None,
                                                 out=str(tmp_path / "o.json")), job=None)


def test_no_ledger_directory_options():
    import inspect
    src = inspect.getsource(lines_job.build_parser)
    assert "--pick-log" not in src and "--points-log" not in src
