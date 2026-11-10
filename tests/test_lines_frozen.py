"""seam/lines_job.py enforces the frozen environment (S12): StillDrawn's extractor pinned by content (the sha256 of
each metrics/ file it uses), and the ComfyUI venv's registered versions. Every refusal is simulated here, in the repo
venv, through injected readers and a fake StillDrawn tree; the real ComfyUI venv is never touched."""
import hashlib
import json
import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace

import pytest

from seam import lines_job

REPO = Path(__file__).resolve().parents[1]
REGISTERED = {"python": "3.12.10", "numpy": "2.5.2", "opencv-contrib-python": "5.0.0.93",
              "opencv-python": "5.0.0.93", "opencv-python-headless": "5.0.0.93", "scikit-image": "0.26.0",
              "scipy": "1.18.0", "torch": "2.13.0"}


def registered():
    return dict(REGISTERED)


def fake_tree(root, version=lines_job.INKSTAB_VERSION):
    """A StillDrawn-shaped tree (metrics/ has no __init__.py, as the real one); returns {relpath: sha256}."""
    (root / "metrics").mkdir(parents=True)
    (root / "metrics/inkstab.py").write_text(
        f"DEFS = {{'version': {version!r}, 'iou_tolerance_px': 2}}\n\n\ndef _device():\n    return 'mps'\n")
    (root / "metrics/masked.py").write_text("import inkstab\n")
    return {rel: hashlib.sha256((root / rel).read_bytes()).hexdigest() for rel in lines_job.METRICS_SHA256}


# --- the registration ---------------------------------------------------------------------------------------------

def test_registered_constants():
    assert set(lines_job.METRICS_SHA256) == {"metrics/inkstab.py", "metrics/masked.py"}
    assert all(len(h) == 64 and int(h, 16) >= 0 for h in lines_job.METRICS_SHA256.values())
    assert {"python": lines_job.COMFY_PYTHON, **lines_job.COMFY_VERSIONS} == REGISTERED


def test_constants_equal_the_registration_record():
    env = REPO / "runs/registration/env.json"
    if not env.exists():
        pytest.skip("runs/registration/env.json is not here")
    venv = json.loads(env.read_text())["comfy_venv"]
    assert lines_job.COMFY_VERSIONS == venv["key"]
    assert lines_job.COMFY_PYTHON == venv["python"]


def test_the_stilldrawn_checkout_matches_the_pinned_files():
    if not (lines_job.STILLDRAWN / "metrics/inkstab.py").exists():
        pytest.skip("no StillDrawn checkout")
    assert lines_job.check_metrics() == lines_job.METRICS_SHA256


# --- the ComfyUI venv ----------------------------------------------------------------------------------------------

def test_check_venv_passes_the_registered_versions():
    assert lines_job.check_venv(read=registered) == REGISTERED


@pytest.mark.parametrize("key", sorted(REGISTERED))
@pytest.mark.parametrize("found", ["0.0.1", None])
def test_check_venv_refuses_any_other_version(key, found):
    got = {**REGISTERED, key: found}
    with pytest.raises(RuntimeError, match=f"{key} {found} \\(registered {REGISTERED[key]}\\)"):
        lines_job.check_venv(read=lambda: got)


def test_venv_versions_reads_the_installed_distributions():
    def dist(name):
        if name == "torch":
            raise metadata.PackageNotFoundError(name)
        return f"v-{name}"
    got = lines_job.venv_versions(dist_version=dist)
    assert got["python"] == platform.python_version()
    assert got["torch"] is None                                          # absent: reads as a difference
    assert {k: v for k, v in got.items() if k not in ("python", "torch")} == \
        {d: f"v-{d}" for d in lines_job.COMFY_VERSIONS if d != "torch"}


# --- StillDrawn's metrics files, pinned by content -----------------------------------------------------------------

def test_check_metrics_passes_identical_files(tmp_path, monkeypatch):
    hashes = fake_tree(tmp_path)
    monkeypatch.setattr(lines_job, "METRICS_SHA256", hashes)
    assert lines_job.check_metrics(tmp_path) == hashes


@pytest.mark.parametrize("rel", ["metrics/inkstab.py", "metrics/masked.py"])
def test_check_metrics_refuses_a_changed_or_missing_file(tmp_path, monkeypatch, rel):
    monkeypatch.setattr(lines_job, "METRICS_SHA256", fake_tree(tmp_path))
    (tmp_path / rel).write_text((tmp_path / rel).read_text() + "# one more line\n")
    with pytest.raises(RuntimeError, match=f"{rel} has sha256 [0-9a-f]{{64}}, not the registered"):
        lines_job.check_metrics(tmp_path)
    (tmp_path / rel).unlink()
    with pytest.raises(RuntimeError, match=f"{rel} is missing"):
        lines_job.check_metrics(tmp_path)


def test_check_metrics_uses_the_injected_hasher(tmp_path):
    (tmp_path / "metrics").mkdir()
    for rel in lines_job.METRICS_SHA256:
        (tmp_path / rel).write_text("anything")
    seen = []

    def same(p):
        seen.append(Path(p).relative_to(tmp_path).as_posix())
        return lines_job.METRICS_SHA256[seen[-1]]
    assert lines_job.check_metrics(tmp_path, hasher=same) == lines_job.METRICS_SHA256
    assert sorted(seen) == sorted(lines_job.METRICS_SHA256)
    with pytest.raises(RuntimeError, match="not the registered"):
        lines_job.check_metrics(tmp_path, hasher=lambda p: "0" * 64)


def test_a_new_commit_with_identical_metrics_is_not_refused(tmp_path, monkeypatch):
    """Pinned by content, not by commit: StillDrawn's public tree is regenerated elsewhere."""
    monkeypatch.setattr(lines_job, "METRICS_SHA256", fake_tree(tmp_path))
    g = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "-c", "commit.gpgsign=false"]
    subprocess.run(g + ["init", "-q"], check=True)
    subprocess.run(g + ["add", "."], check=True)
    subprocess.run(g + ["commit", "-q", "-m", "a"], check=True)
    first = lines_job.stilldrawn_commit(tmp_path)["commit"]
    (tmp_path / "README.md").write_text("regenerated\n")
    subprocess.run(g + ["add", "."], check=True)
    subprocess.run(g + ["commit", "-q", "-m", "b"], check=True)
    second = lines_job.stilldrawn_commit(tmp_path)["commit"]
    assert first != second
    assert lines_job.check_metrics(tmp_path) == lines_job.METRICS_SHA256


# --- main: the checks run before inkstab is imported, and every refusal is a clear message --------------------------

SHIFT = ["shift-control", "--input", "in.npz", "--kappa", "0.8", "--out", "out.json"]


def _metrics_modules():
    return [k for k in sys.modules if k == "metrics" or k.startswith("metrics.")]


@pytest.fixture
def comfy(tmp_path, monkeypatch):
    """main as the ComfyUI venv runs it, with a stand-in netG, the registered versions, a fake StillDrawn tree and the
    command stubbed: nothing is extracted. load_inkstab's sys.path entry and imported modules stay in this test."""
    netg = tmp_path / "netG.pth"
    netg.write_bytes(b"weights")
    monkeypatch.setattr(lines_job, "in_comfy_venv", lambda: True)
    monkeypatch.setattr(lines_job, "NETG", netg)
    monkeypatch.setattr(lines_job, "NETG_SHA256", hashlib.sha256(b"weights").hexdigest())
    monkeypatch.setattr(lines_job, "venv_versions", registered)
    sd = tmp_path / "stilldrawn"
    monkeypatch.setattr(lines_job, "METRICS_SHA256", fake_tree(sd))
    monkeypatch.setattr(lines_job, "STILLDRAWN", sd)
    monkeypatch.setattr(lines_job, "stilldrawn_commit", lambda root=None: {"commit": "c" * 40, "metrics_dirty": False})
    ran = []
    monkeypatch.setattr(lines_job, "cmd_shift", lambda a, job: ran.append(job))
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setenv("STILLDRAWN_CONTROLNET_AUX_SRC", "unused")
    for k in _metrics_modules():
        monkeypatch.delitem(sys.modules, k)
    yield SimpleNamespace(stilldrawn=sd, ran=ran)
    for k in _metrics_modules():
        del sys.modules[k]


def _no_inkstab(*_a, **_k):
    raise AssertionError("inkstab was imported before the frozen-environment checks")


def test_main_runs_and_records_the_frozen_environment(comfy):
    assert lines_job.main(SHIFT) == 0
    (job,) = comfy.ran
    h = job.header()
    assert h["frozen"] == {"comfy_venv": REGISTERED, "metrics_sha256": lines_job.METRICS_SHA256}
    assert h["stilldrawn"] == {"commit": "c" * 40, "metrics_dirty": False}        # the commit is still recorded
    assert h["inkstab_version"] == lines_job.INKSTAB_VERSION


def test_main_refuses_another_venv_before_inkstab(comfy, monkeypatch, capsys):
    monkeypatch.setattr(lines_job, "venv_versions", lambda: {**REGISTERED, "torch": "2.14.0"})
    monkeypatch.setattr(lines_job, "load_inkstab", _no_inkstab)
    assert lines_job.main(SHIFT) == 1
    err = capsys.readouterr().err
    assert err.startswith("lines_job: refuse:") and "torch 2.14.0 (registered 2.13.0)" in err
    assert comfy.ran == []


def test_main_refuses_another_python_before_inkstab(comfy, monkeypatch, capsys):
    monkeypatch.setattr(lines_job, "venv_versions", lambda: {**REGISTERED, "python": "3.13.1"})
    monkeypatch.setattr(lines_job, "load_inkstab", _no_inkstab)
    assert lines_job.main(SHIFT) == 1
    assert "python 3.13.1 (registered 3.12.10)" in capsys.readouterr().err
    assert comfy.ran == []


@pytest.mark.parametrize("rel", ["metrics/inkstab.py", "metrics/masked.py"])
def test_main_refuses_changed_metrics_before_inkstab(comfy, monkeypatch, capsys, rel):
    p = comfy.stilldrawn / rel
    p.write_text(p.read_text() + "# regenerated with a change\n")
    monkeypatch.setattr(lines_job, "load_inkstab", _no_inkstab)
    assert lines_job.main(SHIFT) == 1
    err = capsys.readouterr().err
    assert err.startswith("lines_job: refuse:") and f"{rel} has sha256" in err
    assert comfy.ran == []


def test_main_refuses_other_defs_with_a_message(comfy, monkeypatch, capsys):
    """inkstab.py is pinned by hash, so DEFS cannot differ unless the pin does; the DEFS check still refuses cleanly."""
    for p in (comfy.stilldrawn / "metrics").iterdir():
        p.unlink()
    (comfy.stilldrawn / "metrics").rmdir()
    monkeypatch.setattr(lines_job, "METRICS_SHA256", fake_tree(comfy.stilldrawn, version="inkstab 1.1 (2026-12-01)"))
    assert lines_job.main(SHIFT) == 1
    err = capsys.readouterr().err
    assert err.startswith("lines_job: refuse:") and "inkstab 1.1 (2026-12-01)" in err and "DEFS" in err
    assert comfy.ran == []


def test_hash_netg_still_prints_the_hash_whatever_the_environment(comfy, monkeypatch, capsys):
    monkeypatch.setattr(lines_job, "venv_versions", lambda: {**REGISTERED, "torch": "2.14.0"})
    (comfy.stilldrawn / "metrics/inkstab.py").write_text("changed\n")
    assert lines_job.main(["hash-netg"]) == 0
    assert capsys.readouterr().out.strip() == lines_job.NETG_SHA256
