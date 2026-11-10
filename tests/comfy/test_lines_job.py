"""Lines job tests (unittest, so the ComfyUI venv, which has no pytest, can run them).

    ~/tools/ComfyUI/.venv/bin/python -m unittest discover -s tests/comfy -v

Pure parts run in either venv (pytest collects this file too); the frozen-extractor tests run
only under the ComfyUI venv and skip elsewhere.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from seam import cells, lines_job, pairs  # noqa: E402
from seam.maskrule import frame_rule      # noqa: E402

IN_COMFY = lines_job.in_comfy_venv()
H, W = 720, 1280


def dark(frames):
    return [np.asarray(f)[..., 0] < 128 for f in frames]


def drawing(shift=0, erase_right=False):
    """A light page with vertical dark strokes 80 px apart, so a horizontal shift of s px moves
    every line by s px (horizontal strokes would slide along themselves and read as ~0)."""
    f = np.full((H, W, 3), 235, np.uint8)
    for x in range(100, 1200, 80):
        f[100:620, x + shift:x + shift + 3] = 25
    if erase_right:
        f[:, 640:] = 235
    return f


def tiny_pair(tmp, shift=3, n=4, render_id="fixture", with_creature=True):
    take = np.stack([drawing()] * n)
    render = np.stack([drawing(shift)] * n)
    valid = np.array([True] * (n - 1) + [False])
    R = np.ones((n, H, W), bool)
    creature = np.zeros((n, H, W), bool)
    creature[:, 100:200, 100:200] = True
    R[:, 60:240, 60:240] = False
    home = np.zeros((H, W), bool)
    home[400:500, 900:1000] = True
    scan = drawing()[100:200, 100:200]
    return pairs.write_pair(Path(tmp) / "pair.npz", take=take, render=render, valid=valid, R=R,
                            t=np.arange(n) / 15, creature=creature if with_creature else None, homes={"rest": home},
                            scan=scan, meta={"render": render_id})


class PureTests(unittest.TestCase):
    def test_main_refuses_outside_the_comfy_venv(self):
        if IN_COMFY:
            self.skipTest("inside the ComfyUI venv")
        self.assertEqual(lines_job.main(["hash-netg"]), 2)

    def test_the_venv_and_stilldrawn_are_the_registered_ones(self):
        if not IN_COMFY:
            self.skipTest("outside the ComfyUI venv (tests/test_lines_frozen.py simulates match and mismatch)")
        self.assertEqual(lines_job.check_venv(), {"python": lines_job.COMFY_PYTHON, **lines_job.COMFY_VERSIONS})
        self.assertEqual(lines_job.check_metrics(), lines_job.METRICS_SHA256)

    def test_device_is_pinned(self):
        self.assertEqual(lines_job.DEVICE, "mps")
        self.assertEqual(lines_job.resolve_device("mps", None), ("mps", False))
        with self.assertRaises(RuntimeError):
            lines_job.resolve_device("cpu", None)             # not the registered device
        self.assertEqual(lines_job.resolve_device("cpu", "cpu"), ("cpu", True))   # explicit, recorded

    def test_stilldrawn_checkout_must_be_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                lines_job.stilldrawn_commit(Path(tmp))          # not a git checkout: empty commit
            g = ["git", "-C", tmp, "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
            subprocess.run(g + ["init", "-q"], check=True)
            (Path(tmp) / "metrics").mkdir()
            (Path(tmp) / "metrics/inkstab.py").write_text("x = 1\n")
            subprocess.run(g + ["add", "."], check=True)
            subprocess.run(g + ["commit", "-q", "-m", "c"], check=True)
            info = lines_job.stilldrawn_commit(Path(tmp))
            self.assertEqual(len(info["commit"]), 40)
            self.assertFalse(info["metrics_dirty"])
            (Path(tmp) / "metrics/inkstab.py").write_text("x = 2\n")
            with self.assertRaises(RuntimeError):
                lines_job.stilldrawn_commit(Path(tmp))          # dirty metrics/
            self.assertEqual(lines_job.STILLDRAWN, Path.home() / "projects/stilldrawn")

    def test_measure_with_a_fake_extractor(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = tiny_pair(tmp)
            null = pairs.write_pair(Path(tmp) / "null.npz", **{k: v for k, v in pairs.read_pair(p).items()
                                                               if k in ("take", "R", "t", "valid")},
                                    render=pairs.read_pair(p)["take"])
            seam = Path(tmp) / "seam.bin"
            out = lines_job.measure(p, null=null, kappa=0.8, extract=dark, chamfer=lines_job.chamfer_all,
                                    seam_path=seam)
            d = pairs.read_pair(p)
        self.assertEqual(out["schema"], "p47-lines/1")
        self.assertEqual(out["n_frames"], 4)
        want = frame_rule(dark(d["render"][:1])[0], dark(d["take"][:1])[0], d["R"][0])
        self.assertEqual(out["D"][0], want)
        self.assertAlmostEqual(want, 2.0, places=6)          # 3 px strokes moved 3 px: distances 3, 2, 1
        self.assertIsNone(out["D"][3])                       # failed the gate
        self.assertEqual(out["D0"][:3], [0.0, 0.0, 0.0])
        self.assertEqual(set(out["homes"]), {"rest"})
        self.assertIsNotNone(out["density"][0])
        self.assertIsNotNone(out["scan_chamfer"][0])
        self.assertEqual(out["seam"]["cols"], 40)
        self.assertEqual(out["seam"]["rows"], 23)
        self.assertEqual(out["kappa_codec"], 1.0)            # identical null: every IoU is 1
        self.assertGreater(out["cell_counts"][0]["redrawn"], 0)
        self.assertEqual(out["cell_counts"][3], {"none": 920, "kept": 0, "redrawn": 0, "creature": 0})

    def test_shared_distance_transforms_change_no_value(self):
        rng = np.random.default_rng(7)
        n = 3
        take = np.where(rng.random((n, H, W, 1)) < 0.01, 20, 235).astype(np.uint8).repeat(3, axis=3)
        render = np.where(rng.random((n, H, W, 1)) < 0.01, 20, 235).astype(np.uint8).repeat(3, axis=3)
        null = np.where(rng.random((n, H, W, 1)) < 0.01, 20, 235).astype(np.uint8).repeat(3, axis=3)
        R = rng.random((n, H, W)) < 0.7
        home = np.zeros((H, W), bool)
        home[100:300, 100:300] = True
        valid = np.array([True, True, False])
        with tempfile.TemporaryDirectory() as tmp:
            p = pairs.write_pair(Path(tmp) / "p.npz", take=take, render=render, valid=valid, R=R,
                                 t=np.arange(n) / 15, homes={"h": home})
            q = pairs.write_pair(Path(tmp) / "q.npz", take=take, render=null, valid=np.ones(n, bool), R=R,
                                 t=np.arange(n) / 15)
            out = lines_job.measure(p, null=q, extract=dark, chamfer=lines_job.chamfer_all)
        Lt, Lr, L0 = dark(take), dark(render), dark(null)
        self.assertEqual(out["D"], [frame_rule(Lr[i], Lt[i], R[i]) if valid[i] else None for i in range(n)])
        self.assertEqual(out["D0"], [frame_rule(L0[i], Lt[i], R[i]) for i in range(n)])
        self.assertEqual(out["homes"]["h"], [frame_rule(Lr[i], Lt[i], home) if valid[i] else None for i in range(n)])
        self.assertEqual(out["homes_null"]["h"], [frame_rule(L0[i], Lt[i], home) for i in range(n)])

    def test_line_map_cache(self):
        frames = np.stack([drawing(), drawing(3)])
        calls = []

        def ext(fr):
            calls.append(len(fr))
            return dark(fr)
        head = {"netG_sha256": "x", "defs": {"v": 1}, "device": "mps", "stilldrawn_commit": "c" * 40}
        with tempfile.TemporaryDirectory() as tmp:
            a = lines_job.cached_maps(frames, head, ext, Path(tmp))
            b = lines_job.cached_maps(frames, head, ext, Path(tmp))
            self.assertEqual(calls, [2])                          # extracted once, then read back
            self.assertTrue(all(np.array_equal(x, y) and y.dtype == bool for x, y in zip(a, b)))
            lines_job.cached_maps(frames, {**head, "device": "cpu"}, ext, Path(tmp))
            lines_job.cached_maps(frames[:1], head, ext, Path(tmp))
            self.assertEqual(calls, [2, 2, 1])                    # another header or take: a miss
            self.assertEqual(len(list(Path(tmp).glob("*.npz"))), 3)
        self.assertIn("cache/", (REPO / ".gitignore").read_text().split())

    def test_seam_file_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = tiny_pair(tmp)
            seam = Path(tmp) / "seam.bin"
            lines_job.measure(p, kappa=0.8, extract=dark, chamfer=lines_job.chamfer_all, seam_path=seam)
            data = seam.read_bytes()
        self.assertEqual(len(data), 4 * 230)
        codes = cells.unpack(data, 23, 40)
        self.assertTrue((codes[3] == cells.NONE).all())
        self.assertTrue((codes[0] == cells.CREATURE).any())

    def test_seam_needs_kappa(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = tiny_pair(tmp)
            with self.assertRaises(ValueError):
                lines_job.measure(p, extract=dark, chamfer=lines_job.chamfer_all, seam_path=Path(tmp) / "s.bin")

    def test_null_take_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = tiny_pair(tmp)
            d = pairs.read_pair(p)
            other = pairs.write_pair(Path(tmp) / "n.npz", take=d["render"], render=d["take"], valid=d["valid"],
                                     R=d["R"], t=d["t"])
            with self.assertRaises(ValueError):
                lines_job.measure(p, null=other, extract=dark, chamfer=lines_job.chamfer_all)


@unittest.skipUnless(IN_COMFY, "needs the ComfyUI venv (frozen extractor)")
class FrozenExtractorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inkstab = lines_job.load_inkstab()
        cls.maps = lines_job.line_maps(cls.inkstab, [drawing(), drawing(3), drawing(erase_right=True)],
                                       lines_job.DEVICE)

    def test_defs_and_weights(self):
        self.assertEqual(self.inkstab.DEFS["version"], lines_job.INKSTAB_VERSION)
        self.assertEqual(self.inkstab.DEFS["iou_tolerance_px"], 2)
        self.assertEqual(lines_job.sha256_file(lines_job.NETG), lines_job.NETG_SHA256)

    def test_all_true_region_equals_frozen_chamfer(self):
        a, b, _ = self.maps
        self.assertTrue(a.any() and b.any())
        R = np.ones(a.shape, bool)
        self.assertEqual(frame_rule(b, a, R), self.inkstab._chamfer(b, a))
        self.assertEqual(lines_job.chamfer_all(b, a), self.inkstab._chamfer(b, a))

    def test_three_px_shift_reads_about_three(self):
        a, b, _ = self.maps
        d = frame_rule(b, a, np.ones(a.shape, bool))
        self.assertGreater(d, 2.0)
        self.assertLess(d, 4.0)

    def test_vanished_lines_score_one_sided_term(self):
        from scipy.ndimage import distance_transform_edt as edt
        take, _, erased = self.maps
        R = np.zeros(take.shape, bool)
        R[:, 700:] = True
        self.assertFalse((erased & R).any())
        self.assertTrue((take & R).any())
        self.assertEqual(frame_rule(erased, take, R), float(edt(~erased)[take & R].mean()))

    def test_cli_measure_end_to_end(self):
        """The measure command in process, past its custody check (tested in tests/test_lines_custody.py,
        which needs committed ledgers this test cannot make)."""
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            p = tiny_pair(tmp, n=2, render_id="t01-ink")
            out = Path(tmp) / "out.json"
            with mock.patch.object(lines_job, "check_custody") as cc:
                rc = lines_job.main(["measure", "--pair", str(p), "--render", "t01-ink", "--kappa", "0.8",
                                     "--out", str(out), "--seam", str(Path(tmp) / "s.bin")])
            self.assertEqual(rc, 0)
            self.assertEqual(cc.call_count, 1)
            res = json.loads(out.read_text())
        self.assertEqual(res["netG_sha256"], lines_job.NETG_SHA256)
        self.assertEqual(res["inkstab_version"], lines_job.INKSTAB_VERSION)
        self.assertEqual((res["device"], res["device_override"]), ("mps", False))
        self.assertEqual(len(res["stilldrawn"]["commit"]), 40)
        self.assertGreater(res["D"][0], 2.0)
        self.assertLess(res["D"][0], 4.0)

    def test_cli_controls_run_on_real_maps(self):
        n = 3
        take = np.full((n, H, W, 3), 235, np.uint8)
        for y0 in range(96, 640, 32):                        # mixed ticks: no dominant orientation
            for x0 in range(96, 1184, 32):
                take[:, y0 + 2:y0 + 15, x0 + 5:x0 + 8] = 25
                take[:, y0 + 21:y0 + 24, x0 + 14:x0 + 31] = 25
        rgba = np.zeros((90, 90, 4), np.uint8)
        rgba[..., :3] = 240
        rgba[20:70, 43:47, :3] = 0
        rgba[..., 3] = 255
        with tempfile.TemporaryDirectory() as tmp:
            ci, si = Path(tmp) / "c.npz", Path(tmp) / "s.npz"
            np.savez(ci, take=take, null_1080=take, rgba=rgba, xy=np.array([600, 300]), home=np.zeros((H, W), bool))
            np.savez(si, take=take, R=np.ones((n, H, W), bool))
            wrong = subprocess.run([sys.executable, str(REPO / "seam/lines_job.py"), "paste-control", "--input", str(ci),
                                    "--model", "kling_4", "--out", str(Path(tmp) / "w.json")], capture_output=True, text=True)
            self.assertNotEqual(wrong.returncode, 0)                 # kling_4 needs null_720, absent here
            self.assertIn("null_720", wrong.stderr)
            outs = []
            for cmd, inp, extra in (("paste-control", ci, ["--model", "aleph2"]), ("shift-control", si, ["--kappa", "0.8"])):
                out = Path(tmp) / f"{cmd}.json"
                r = subprocess.run([sys.executable, str(REPO / "seam/lines_job.py"), cmd, "--input", str(inp),
                                    *extra, "--out", str(out)], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr[-2000:])
                outs.append(json.loads(out.read_text()))
        paste, shift = outs
        self.assertEqual(sorted(paste["per_m"]), ["32", "48", "64"])
        self.assertIn("testable", paste)
        self.assertEqual(paste["null_height"], 1080)
        self.assertEqual(paste["reason"], "fewer than 20 scored frames")   # 3 frames only
        self.assertTrue(shift["pass"], shift)


if __name__ == "__main__":
    unittest.main()
