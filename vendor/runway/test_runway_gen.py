#!/usr/bin/env python3
"""Tests for runway_gen.py. HTTP is mocked: no test may touch the network or spend credits.

Run with plain python3, NOT through runway.sh, so no real key is ever loaded:

    cd tools/runway && python3 -m unittest test_runway_gen -v
"""
import argparse
import contextlib
import copy
import hashlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from datetime import date
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import runway_gen as rg  # noqa: E402

TEST_KEY = "test-key-not-a-secret"
CDN = "https://cdn.example.test"
UPLOAD_URL = "https://upload.example.test/put"


class FakeResponse:
    def __init__(self, body=b""):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self._buf = io.BytesIO(body)

    def read(self, n=-1):
        return self._buf.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeRunway:
    """Stands in for urllib's urlopen. Routes by (METHOD, url) and records every call.

    A route holds a list of responses, served in order (the last one repeats).
    A response is a dict or bytes (200 body), an int (HTTP error status), an exception to raise,
    or a function(req) returning one of those (used to inspect state at the moment of the call).
    """

    def __init__(self):
        self.calls = []  # (method, url, headers, body)
        self.routes = {}

    def on(self, method, url, *responses):
        self.routes[(method, url)] = list(responses)
        return self

    def __call__(self, req, timeout=None):
        method, url = req.get_method(), req.full_url
        self.calls.append((method, url, dict(req.header_items()), req.data))
        queue = self.routes.get((method, url))
        if not queue:
            raise AssertionError(f"unmocked HTTP call: {method} {url}")
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if callable(item):
            item = item(req)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, int):
            raise urllib.error.HTTPError(url, item, "err", {}, io.BytesIO(b'{"error":"boom"}'))
        return FakeResponse(item)

    def to(self, method, url):
        return [c for c in self.calls if c[0] == method and c[1] == url]


class RunwayTestCase(unittest.TestCase):
    def setUp(self):
        self.api = FakeRunway()
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="rg-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        patches = [
            mock.patch.object(rg, "_urlopen", self.api),
            mock.patch.dict(os.environ, {"RUNWAY_API_KEY": TEST_KEY}),
            mock.patch("sys.stderr", io.StringIO()),   # keep retry and progress chatter out of the test report
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        sleeper = mock.patch("time.sleep")
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)

    def run_cli(self, *argv):
        """Run main(argv). Returns (exit_code, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rg.main(list(argv))
            except SystemExit as e:
                if isinstance(e.code, str):
                    err.write(e.code)
                    code = 1
                else:
                    code = e.code or 0
        return code, out.getvalue(), err.getvalue()


class HttpSeamTests(RunwayTestCase):
    def test_req_sends_bearer_and_version_headers(self):
        self.api.on("GET", rg.BASE + "/tasks/t1", {"id": "t1"})
        self.assertEqual(rg._req("GET", "/tasks/t1"), {"id": "t1"})
        headers = self.api.calls[0][2]
        self.assertEqual(headers["Authorization"], "Bearer " + TEST_KEY)
        self.assertEqual(headers["X-runway-version"], "2024-11-06")

    def test_missing_key_exits_before_any_call(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("RUNWAY_API_KEY")
            with self.assertRaises(SystemExit):
                rg._req("GET", "/tasks/t1")
        self.assertEqual(self.api.calls, [])

    def test_http_error_becomes_apierror(self):
        self.api.on("POST", rg.BASE + "/video_to_video", 400)
        with self.assertRaises(rg.ApiError) as cm:
            rg._req("POST", "/video_to_video", {"x": 1})
        self.assertEqual(cm.exception.status, 400)
        self.assertIn("boom", str(cm.exception))

    def test_get_is_retried_on_503_then_succeeds(self):
        self.api.on("GET", rg.BASE + "/tasks/t1", 503, 503, {"ok": 1})
        self.assertEqual(rg._req("GET", "/tasks/t1"), {"ok": 1})
        self.assertEqual(len(self.api.calls), 3)
        self.assertEqual(self.sleep.call_count, 2)

    def test_get_gives_up_after_max_retries(self):
        self.api.on("GET", rg.BASE + "/tasks/t1", 503)
        with self.assertRaises(rg.ApiError):
            rg._req("GET", "/tasks/t1")
        self.assertEqual(len(self.api.calls), rg.MAX_RETRIES + 1)

    def test_post_is_not_retried_on_503(self):
        # A 5xx on a POST may mean the task was created: never send it twice.
        self.api.on("POST", rg.BASE + "/video_to_video", 503, {"id": "x"})
        with self.assertRaises(rg.ApiError):
            rg._req("POST", "/video_to_video", {})
        self.assertEqual(len(self.api.calls), 1)

    def test_post_is_retried_on_429(self):
        # 429 means the request was refused, so a retry cannot double-bill.
        self.api.on("POST", rg.BASE + "/video_to_video", 429, {"id": "x"})
        self.assertEqual(rg._req("POST", "/video_to_video", {}), {"id": "x"})
        self.assertEqual(len(self.api.calls), 2)

    def test_get_retries_network_errors(self):
        self.api.on("GET", rg.BASE + "/tasks/t1", urllib.error.URLError("reset"), {"ok": 1})
        self.assertEqual(rg._req("GET", "/tasks/t1"), {"ok": 1})

    def test_post_network_error_is_status_zero_and_not_retried(self):
        self.api.on("POST", rg.BASE + "/video_to_video", urllib.error.URLError("reset"))
        with self.assertRaises(rg.ApiError) as cm:
            rg._req("POST", "/video_to_video", {})
        self.assertEqual(cm.exception.status, 0)
        self.assertEqual(len(self.api.calls), 1)

    def test_download_is_atomic_and_sends_no_credentials(self):
        self.api.on("GET", CDN + "/out.mp4?sig=1", b"MP4DATA")
        out = self.tmp / "sub" / "out.mp4"
        rg._download(CDN + "/out.mp4?sig=1", str(out))
        self.assertEqual(out.read_bytes(), b"MP4DATA")
        self.assertFalse(out.with_name("out.mp4.part").exists())
        self.assertNotIn("Authorization", self.api.calls[0][2])


class EstimateTests(RunwayTestCase):
    def est(self, model, i, o, tier, refs=0, today=date(2026, 11, 1)):
        return rg.estimate_v2v(model, in_seconds=i, out_seconds=o, tier=tier, n_refs=refs, today=today)

    def test_aleph2_is_28_a_second_with_a_56_minimum(self):
        self.assertEqual(self.est("aleph2", 10, 10, "any"), 280)
        self.assertEqual(self.est("aleph2", 2, 2, "any"), 56)

    def test_seedance_prices_output_and_input_seconds_by_tier(self):
        self.assertEqual(self.est("seedance2_5", 10, 10, "720p"), 450)    # 10*30 + 10*15, the master plan's figure
        self.assertEqual(self.est("seedance2_5", 10, 10, "480p"), 300)    # 10*20 + 10*10
        self.assertEqual(self.est("seedance2_5", 10, 10, "1080p"), 1020)  # 10*68 + 10*34
        self.assertEqual(self.est("seedance2_5", 1, 1, "480p"), 80)       # 80 minimum

    def test_gemini_adds_input_seconds_and_a_credit_per_reference(self):
        self.assertEqual(self.est("gemini_omni_flash_1.1", 10, 10, "360p", refs=1), 45)   # 34 + 10 + 1
        self.assertEqual(self.est("gemini_omni_flash_1.1", 10, 10, "720p"), 110)          # 100 + 10
        self.assertEqual(self.est("gemini_omni_flash_1.1", 3, 3, "360p"), 14)             # 10.2 + 3, rounded up

    def test_kling_promo_rounds_the_list_price_up_then_the_discount_up(self):
        self.assertEqual(self.est("kling_4", 5, 5, "720p", today=date(2026, 11, 30)), 76)    # list 94 -> 75.2 -> 76
        self.assertEqual(self.est("kling_4", 10, 10, "1080p", today=date(2026, 11, 30)), 226) # list 282 -> 225.6 -> 226
        self.assertEqual(self.est("kling_4", 12, 10, "720p", today=date(2026, 11, 30)), 166)  # 9.4*10 + 9.4*max(12,10) = 206.8 -> 207 -> 165.6 -> 166

    def test_kling_list_price_applies_from_1_december(self):
        self.assertEqual(self.est("kling_4", 5, 5, "720p", today=date(2026, 12, 1)), 94)

    def test_unknown_tier_or_model_raises(self):
        with self.assertRaises(ValueError):
            self.est("seedance2_5", 10, 10, "4K")
        with self.assertRaises(ValueError):
            self.est("gen4_turbo", 10, 10, "any")

    def test_whole_seconds_rounds_up_but_forgives_container_slack(self):
        self.assertEqual(rg._whole_seconds(10.008), 10)
        self.assertEqual(rg._whole_seconds(10.06), 11)
        self.assertEqual(rg._whole_seconds(10), 10)

    def test_simple_estimates_for_image_and_video(self):
        self.assertEqual(rg.estimate_simple("gemini_2.5_flash"), 5)   # 5 credits, docs pricing guide read 3 Nov 2026
        self.assertEqual(rg.estimate_simple("gen4_turbo", 5), 25)
        self.assertIsNone(rg.estimate_simple("no_such_model", 5))

    def test_cost_note_text_is_unchanged(self):
        self.assertEqual(rg._cost_note("gen4_turbo", 5), "(cost: ~25 cr ≈ $0.25)")
        self.assertIn("unknown model", rg._cost_note("no_such_model"))


class LogTests(RunwayTestCase):
    def test_log_row_appends_one_json_line_each_with_a_utc_time(self):
        log = self.tmp / "nested" / "spend.jsonl"
        rg.log_row(log, {"event": "pre", "model": "aleph2"})
        rg.log_row(log, {"event": "final", "cost_credits": 280})
        lines = log.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        rows = [json.loads(line) for line in lines]
        self.assertEqual(rows[0]["event"], "pre")
        self.assertEqual(rows[1]["cost_credits"], 280)
        for row in rows:
            self.assertRegex(row["time"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$")

    def test_log_row_never_rewrites_earlier_lines(self):
        log = self.tmp / "spend.jsonl"
        rg.log_row(log, {"n": 1})
        first = log.read_text()
        rg.log_row(log, {"n": 2})
        self.assertTrue(log.read_text().startswith(first))

    def test_sha256_json_ignores_key_order_and_whitespace(self):
        a = {"model": "aleph2", "inputs": {"video": "a.mp4"}}
        b = {"inputs": {"video": "a.mp4"}, "model": "aleph2"}
        self.assertEqual(rg.sha256_json(a), rg.sha256_json(b))
        self.assertEqual(rg.sha256_json(a), hashlib.sha256(
            b'{"inputs":{"video":"a.mp4"},"model":"aleph2"}').hexdigest())
        self.assertNotEqual(rg.sha256_json(a), rg.sha256_json({"model": "kling_4"}))

    def test_file_sha256_streams_a_file(self):
        f = self.tmp / "x.bin"
        f.write_bytes(b"abc" * 1000)
        self.assertEqual(rg.file_sha256(f), hashlib.sha256(b"abc" * 1000).hexdigest())


class ProbeTests(RunwayTestCase):
    def fake_run(self, stdout, returncode=0, stderr=""):
        return mock.patch.object(rg.subprocess, "run", return_value=SimpleNamespace(
            returncode=returncode, stdout=stdout, stderr=stderr))

    def test_probe_parses_seconds_size_and_fractional_fps(self):
        payload = json.dumps({"streams": [{"width": 1280, "height": 720, "r_frame_rate": "30000/1001"}],
                              "format": {"duration": "9.976"}})
        with self.fake_run(payload):
            info = rg.probe_video(self.tmp / "a.mp4")
        self.assertAlmostEqual(info["seconds"], 9.976)
        self.assertEqual((info["width"], info["height"]), (1280, 720))
        self.assertAlmostEqual(info["fps"], 29.97, places=2)

    def test_probe_reports_a_failed_ffprobe(self):
        with self.fake_run("", returncode=1, stderr="Invalid data found"):
            with self.assertRaises(rg.RequestError) as cm:
                rg.probe_video(self.tmp / "a.mp4")
        self.assertIn("Invalid data", str(cm.exception))

    def test_probe_rejects_a_file_with_no_video_stream(self):
        with self.fake_run(json.dumps({"streams": [], "format": {"duration": "3"}})):
            with self.assertRaises(rg.RequestError):
                rg.probe_video(self.tmp / "a.mp4")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg and ffprobe")
    def test_probe_reads_a_real_clip(self):
        clip = self.tmp / "real.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:duration=2",
                        "-pix_fmt", "yuv420p", str(clip)], check=True)
        info = rg.probe_video(clip)
        self.assertAlmostEqual(info["seconds"], 2.0, delta=0.1)
        self.assertEqual((info["width"], info["height"]), (320, 240))
        self.assertAlmostEqual(info["fps"], 24.0, places=1)


class UploadTests(RunwayTestCase):
    def mock_slot(self, upload_status=204):
        self.api.on("POST", rg.BASE + "/uploads", {
            "uploadUrl": UPLOAD_URL, "fields": {"key": "k1", "policy": "p1"}, "runwayUri": "runway://upload/abc"})
        self.api.on("POST", UPLOAD_URL, b"" if upload_status == 204 else upload_status)

    def clip(self, name="clip.mp4", size=2048):
        f = self.tmp / name
        f.write_bytes(b"\x00\x01" * (size // 2))
        return f

    def test_upload_returns_the_runway_uri(self):
        self.mock_slot()
        self.assertEqual(rg.upload_file(self.clip()), "runway://upload/abc")

    def test_upload_requests_an_ephemeral_slot_for_the_file_name(self):
        self.mock_slot()
        rg.upload_file(self.clip("my clip!.mp4"))
        body = json.loads(self.api.to("POST", rg.BASE + "/uploads")[0][3])
        self.assertEqual(body, {"filename": "my_clip_.mp4", "type": "ephemeral"})

    def test_multipart_has_fields_first_then_the_file_last(self):
        self.mock_slot()
        f = self.clip(size=2048)
        rg.upload_file(f)
        _, _, headers, data = self.api.to("POST", UPLOAD_URL)[0]
        self.assertTrue(headers["Content-type"].startswith("multipart/form-data; boundary="))
        self.assertLess(data.index(b'name="key"'), data.index(b'name="policy"'))
        self.assertLess(data.index(b'name="policy"'), data.index(b'name="file"'))
        self.assertIn(f.read_bytes(), data)
        self.assertTrue(data.rstrip().endswith(b"--"))

    def test_the_third_party_upload_carries_no_credentials(self):
        self.mock_slot()
        rg.upload_file(self.clip())
        self.assertNotIn("Authorization", self.api.to("POST", UPLOAD_URL)[0][2])
        self.assertIn("Authorization", self.api.to("POST", rg.BASE + "/uploads")[0][2])

    def test_a_failed_upload_is_not_retried(self):
        self.mock_slot(upload_status=403)
        with self.assertRaises(rg.ApiError):
            rg.upload_file(self.clip())
        self.assertEqual(len(self.api.to("POST", UPLOAD_URL)), 1)
        self.assertEqual(len(self.api.to("POST", rg.BASE + "/uploads")), 1)

    def test_error_text_never_contains_the_signed_fields(self):
        self.mock_slot(upload_status=403)
        with self.assertRaises(rg.ApiError) as cm:
            rg.upload_file(self.clip())
        self.assertNotIn("p1", str(cm.exception))

    def test_size_limits_are_checked_before_any_call(self):
        with self.assertRaises(rg.RequestError):
            rg.upload_file(self.clip(size=100))                      # under 512 bytes
        big = self.clip(size=2048)
        with mock.patch.object(rg, "_file_size", return_value=201 * 1024 * 1024):
            with self.assertRaises(rg.RequestError):
                rg.upload_file(big)                                  # over 200 MB
        self.assertEqual(self.api.calls, [])

    def test_unsupported_extensions_are_refused(self):
        for name in ("pic.gif", "notes.txt"):
            with self.assertRaises(rg.RequestError):
                rg.upload_file(self.clip(name))
        self.assertEqual(self.api.calls, [])

    def test_upload_subcommand_prints_the_uri_and_needs_no_yes(self):
        self.mock_slot()
        code, out, _ = self.run_cli("upload", str(self.clip()))
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "runway://upload/abc")


class ResolverTests(RunwayTestCase):
    def setUp(self):
        super().setUp()
        self.uploads = []
        self.resolve = rg.make_resolver(self.tmp, self.fake_upload)

    def fake_upload(self, path):
        self.uploads.append(pathlib.Path(path).name)
        return "runway://upload/" + pathlib.Path(path).name

    def make(self, name, size):
        f = self.tmp / name
        f.write_bytes(bytes(size))
        return f

    def test_data_uri_cap_is_measured_on_the_encoded_size(self):
        # The API caps the ENCODED data URI at 5 MB; base64 grows a file by a third.
        self.assertLessEqual(rg.MAX_REF_BYTES * 4 // 3 + 64, 5_000_000)

    def test_local_video_is_always_uploaded(self):
        self.make("shot.mp4", 2048)
        self.assertEqual(self.resolve("video", "shot.mp4"), "runway://upload/shot.mp4")
        self.assertEqual(self.uploads, ["shot.mp4"])

    def test_small_local_image_becomes_a_data_uri(self):
        self.make("kf.png", 2048)
        uri = self.resolve("image", "kf.png")
        self.assertTrue(uri.startswith("data:image/png;base64,"))
        self.assertEqual(self.uploads, [])

    def test_large_local_image_is_uploaded_instead(self):
        self.make("big.jpg", rg.MAX_REF_BYTES + 1)
        self.assertEqual(self.resolve("image", "big.jpg"), "runway://upload/big.jpg")

    def test_remote_forms_pass_through_untouched(self):
        for uri in ("https://example.test/a.mp4", "runway://upload/xyz", "data:image/png;base64,AAAA"):
            self.assertEqual(self.resolve("video", uri), uri)
        self.assertEqual(self.uploads, [])

    def test_plain_http_is_refused(self):
        with self.assertRaises(rg.RequestError) as cm:
            self.resolve("video", "http://example.test/a.mp4")
        self.assertIn("https", str(cm.exception))

    def test_missing_file_and_wrong_types_are_refused(self):
        self.make("pic.gif", 2048)
        self.make("clip.txt", 2048)
        with self.assertRaises(rg.RequestError):
            self.resolve("video", "nope.mp4")
        with self.assertRaises(rg.RequestError):
            self.resolve("image", "pic.gif")
        with self.assertRaises(rg.RequestError):
            self.resolve("video", "clip.txt")

    def test_relative_paths_resolve_against_the_base_folder(self):
        (self.tmp / "sub").mkdir()
        self.make("sub/shot.mp4", 2048)
        self.assertEqual(self.resolve("video", "sub/shot.mp4"), "runway://upload/shot.mp4")

    def test_dry_run_resolver_uploads_nothing_and_still_validates(self):
        dry = rg.make_resolver(self.tmp, None)
        self.make("shot.mp4", 2048)
        self.assertEqual(dry("video", "shot.mp4"), "dry-run://upload/shot.mp4")
        with self.assertRaises(rg.RequestError):
            dry("video", "missing.mp4")
        self.assertEqual(self.api.calls, [])


BASE_REQ = {
    "schema": "p47-render/1",
    "model": "seedance2_5",
    "prompt": "Redraw the water as ink; keep everything else.",
    "seed": 7,
    "inputs": {"video": "https://example.test/take.mp4",
               "video_info": {"seconds": 10, "width": 1280, "height": 720, "fps": 24}},
    "options": {"mode": "edit"},
    "meta": {"take": "t03", "material": "ink", "purpose": "probe"},
}


def make_req(model="seedance2_5", inputs=None, options=None, **top):
    """A valid request dict, with `inputs`/`options` merged over the base and `top` keys overriding."""
    req = copy.deepcopy(BASE_REQ)
    req["model"] = model
    req["inputs"].update(inputs or {})
    if options is not None:
        req["options"] = options
    req.update(top)
    return req


class RequestFileTests(RunwayTestCase):
    def write(self, req, name="req.json"):
        f = self.tmp / name
        f.write_text(req if isinstance(req, str) else json.dumps(req))
        return f

    def test_a_valid_request_loads_with_defaults_filled_and_a_hash(self):
        req, sha = rg.load_request(self.write(make_req()))
        self.assertEqual(req["inputs"]["keyframes"], [])
        self.assertEqual(req["inputs"]["references"], [])
        self.assertEqual(req["options"], {"mode": "edit"})
        self.assertEqual(sha, rg.sha256_json(make_req()))

    def test_the_hash_ignores_key_order_in_the_file(self):
        a = rg.load_request(self.write(make_req(), "a.json"))[1]
        shuffled = dict(reversed(list(make_req().items())))
        b = rg.load_request(self.write(shuffled, "b.json"))[1]
        self.assertEqual(a, b)

    def test_every_supported_model_has_an_adapter_row(self):
        self.assertEqual(set(rg.V2V_MODELS), {"aleph2", "kling_4", "seedance2_5", "gemini_omni_flash_1.1"})

    def test_bad_requests_are_refused_with_a_reason(self):
        bad = {
            "wrong schema": make_req(schema="p47-render/2"),
            "unknown model": make_req(model="gen4_aleph"),
            "typo in a top-level key": {**make_req(), "prompts": "x"},
            "empty prompt": make_req(prompt="  "),
            "unknown option": make_req(options={"mode": "edit", "ratioo": "16:9"}),
            "unknown input key": make_req(inputs={"vidoe": "x"}),
            "path and uri together": make_req(inputs={"references": [{"path": "a.png", "uri": "https://e.test/a.png"}]}),
            "neither path nor uri": make_req(inputs={"references": [{}]}),
            "video missing": make_req(inputs={"video": ""}),
            "video_info without seconds": make_req(inputs={"video_info": {"width": 1}}),
        }
        for why, req in bad.items():
            with self.subTest(why):
                with self.assertRaises(rg.RequestError):
                    rg.load_request(self.write(req))

    def test_unreadable_or_non_json_files_are_refused(self):
        with self.assertRaises(rg.RequestError):
            rg.load_request(self.tmp / "missing.json")
        with self.assertRaises(rg.RequestError):
            rg.load_request(self.write("{not json"))

    def test_video_info_probes_a_local_file(self):
        (self.tmp / "take.mp4").write_bytes(bytes(2048))
        req, _ = rg.load_request(self.write(make_req(inputs={"video": "take.mp4"})))
        fake = {"seconds": 9.9, "width": 640, "height": 360, "fps": 24.0}
        with mock.patch.object(rg, "probe_video", return_value=fake) as probe:
            self.assertEqual(rg.video_info(req, self.tmp), fake)
        self.assertEqual(probe.call_args[0][0], self.tmp / "take.mp4")

    def test_video_info_comes_from_the_file_for_a_remote_video(self):
        req, _ = rg.load_request(self.write(make_req()))
        info = rg.video_info(req, self.tmp)
        self.assertEqual((info["seconds"], info["width"], info["height"]), (10.0, 1280, 720))

    def test_a_remote_video_without_video_info_is_refused(self):
        req = make_req()
        del req["inputs"]["video_info"]
        loaded, _ = rg.load_request(self.write(req))
        with self.assertRaises(rg.RequestError) as cm:
            rg.video_info(loaded, self.tmp)
        self.assertIn("video_info", str(cm.exception))


INFO_720 = {"seconds": 10.0, "width": 1280, "height": 720, "fps": 24.0}


def fake_resolve(kind, target):
    return f"uri:{kind}:{target}"


class AdapterTests(RunwayTestCase):
    def build(self, model, info=INFO_720, **kw):
        req = make_req(model, **kw)
        for key in ("keyframes", "references"):
            req["inputs"].setdefault(key, [])
        req.setdefault("meta", {})
        return rg.build_v2v(req, fake_resolve, info)

    # --- aleph2 ---
    def test_aleph2_maps_prompt_keyframes_and_seed(self):
        r = self.build("aleph2", options={}, inputs={"video": "take.mp4", "keyframes": [
            {"path": "kf.png", "seconds": 3.5},
            {"uri": "https://e.test/k.png", "at": 0.8, "range": {"start_seconds": 4, "end_seconds": 6}}]})
        self.assertEqual(r["body"], {
            "model": "aleph2", "videoUri": "uri:video:take.mp4",
            "promptText": BASE_REQ["prompt"], "seed": 7,
            "keyframes": [{"uri": "uri:image:kf.png", "seconds": 3.5},
                          {"uri": "uri:image:https://e.test/k.png", "at": 0.8,
                           "range": {"start_seconds": 4, "end_seconds": 6}}]})
        self.assertEqual((r["out_seconds"], r["tier"], r["n_refs"], r["seed"]), (10.0, "any", 0, 7))

    def test_aleph2_refuses_what_it_cannot_do(self):
        refusals = {
            "references": dict(inputs={"references": [{"path": "r.png"}]}),
            "input too short": dict(info={**INFO_720, "seconds": 1.5}),
            "input too long": dict(info={**INFO_720, "seconds": 31}),
            "over 30 fps": dict(info={**INFO_720, "fps": 60.0}),
            "six keyframes": dict(inputs={"keyframes": [{"path": f"k{i}.png", "at": 0.1} for i in range(6)]}),
            "seconds and at": dict(inputs={"keyframes": [{"path": "k.png", "seconds": 1, "at": 0.5}]}),
            "keyframe with neither": dict(inputs={"keyframes": [{"path": "k.png"}]}),
            "prompt over 1000": dict(prompt="x" * 1001),
            "seed out of range": dict(seed=2**32),
        }
        for why, kwargs in refusals.items():
            with self.subTest(why), self.assertRaises(rg.RequestError):
                self.build("aleph2", **kwargs)

    # --- kling_4 ---
    def test_kling_defaults_to_720_and_drops_the_seed_with_a_warning(self):
        r = self.build("kling_4", options={}, inputs={"video": "t.mp4", "references": [{"path": "c.png"}]})
        self.assertEqual(r["body"], {"model": "kling_4", "videoUri": "uri:video:t.mp4",
                                     "promptText": BASE_REQ["prompt"], "ratio": "auto_720p",
                                     "references": [{"uri": "uri:image:c.png"}]})
        self.assertEqual((r["tier"], r["n_refs"], r["seed"]), ("720p", 1, "first output"))
        self.assertTrue(any("seed" in w for w in r["warnings"]))

    def test_kling_1080_and_limits(self):
        self.assertEqual(self.build("kling_4", options={"ratio": "auto_1080p"})["tier"], "1080p")
        for why, kwargs in {
            "bad ratio": dict(options={"ratio": "16:9"}),
            "keyframes": dict(options={}, inputs={"keyframes": [{"path": "k.png", "at": 0.5}]}),
            "eleven references": dict(options={}, inputs={"references": [{"path": f"r{i}.png"} for i in range(11)]}),
            "prompt over 26000": dict(options={}, prompt="x" * 26001),
        }.items():
            with self.subTest(why), self.assertRaises(rg.RequestError):
                self.build("kling_4", **kwargs)
        with self.assertRaises(rg.RequestError):
            self.build("kling_4", info={**INFO_720, "seconds": 2.0}, options={})

    def test_kling_warns_that_audio_cannot_be_turned_off(self):
        r = self.build("kling_4", options={"audio": False})
        self.assertTrue(any("audio" in w for w in r["warnings"]))

    # --- seedance2_5 ---
    def test_seedance_edit_sends_auto_duration_no_audio_and_a_seed(self):
        r = self.build("seedance2_5", options={"mode": "edit", "audio": False},
                       inputs={"video": "t.mp4", "references": [{"path": "c.png"}]})
        self.assertEqual(r["body"], {
            "model": "seedance2_5", "promptVideo": "uri:video:t.mp4", "promptText": BASE_REQ["prompt"],
            "mode": "edit", "duration": "auto", "audio": False, "seed": 7,
            "references": [{"uri": "uri:image:c.png"}]})
        self.assertEqual((r["out_seconds"], r["tier"], r["n_refs"], r["seed"]), (10.0, "720p", 1, 7))

    def test_seedance_audio_defaults_to_false_here_although_the_api_defaults_to_true(self):
        self.assertIs(self.build("seedance2_5", options={})["body"]["audio"], False)
        self.assertIs(self.build("seedance2_5", options={"audio": True})["body"]["audio"], True)

    def test_seedance_edit_renders_1080p_only_above_720p_input(self):
        big = {**INFO_720, "width": 1920, "height": 1080}
        portrait = {**INFO_720, "width": 720, "height": 1280}
        self.assertEqual(self.build("seedance2_5", info=big, options={})["tier"], "1080p")
        self.assertEqual(self.build("seedance2_5", info=portrait, options={})["tier"], "720p")
        unknown = self.build("seedance2_5", info={"seconds": 10.0, "width": None, "height": None, "fps": None},
                             options={})
        self.assertEqual(unknown["tier"], "1080p")     # unknown size: price it high
        self.assertTrue(any("size" in w for w in unknown["warnings"]))

    def test_seedance_draft_is_a_480p_preview(self):
        r = self.build("seedance2_5", options={"draft": True})
        self.assertIs(r["body"]["draft"], True)
        self.assertEqual(r["tier"], "480p")

    def test_seedance_reference_mode_needs_a_ratio_and_takes_a_duration(self):
        r = self.build("seedance2_5", options={"mode": "reference", "ratio": "1920:1080", "duration": 6})
        self.assertEqual((r["body"]["ratio"], r["body"]["duration"], r["tier"], r["out_seconds"]), ("1920:1080", 6, "1080p", 6))
        with self.assertRaises(rg.RequestError):
            self.build("seedance2_5", options={"mode": "reference"})
        with self.assertRaises(rg.RequestError):
            self.build("seedance2_5", options={"mode": "reference", "ratio": "16:9"})

    def test_seedance_extend_needs_an_integer_duration_and_no_ratio(self):
        r = self.build("seedance2_5", options={"mode": "extend", "duration": 5})
        self.assertEqual((r["body"]["mode"], r["body"]["duration"], r["out_seconds"]), ("extend", 5, 5))
        for opts in ({"mode": "extend"}, {"mode": "extend", "duration": 5, "ratio": "1280:720"}):
            with self.subTest(opts), self.assertRaises(rg.RequestError):
                self.build("seedance2_5", options=opts)

    def test_seedance_refusals(self):
        for why, kwargs in {
            "ratio in edit": dict(options={"mode": "edit", "ratio": "1280:720"}),
            "duration in edit": dict(options={"mode": "edit", "duration": 5}),
            "unknown mode": dict(options={"mode": "remix"}),
            "keyframes": dict(options={}, inputs={"keyframes": [{"path": "k.png", "at": 0.5}]}),
            "31 references": dict(options={}, inputs={"references": [{"path": f"r{i}.png"} for i in range(31)]}),
            "prompt over 15000": dict(options={}, prompt="x" * 15001),
        }.items():
            with self.subTest(why), self.assertRaises(rg.RequestError):
                self.build("seedance2_5", **kwargs)
        with self.assertRaises(rg.RequestError):
            self.build("seedance2_5", info={**INFO_720, "seconds": 3.0}, options={})   # shorter than 4 s

    # --- gemini_omni_flash_1.1 ---
    def test_gemini_edit_needs_an_explicit_ratio_and_drops_the_seed(self):
        with self.assertRaises(rg.RequestError) as cm:
            self.build("gemini_omni_flash_1.1", options={"mode": "edit"})
        self.assertIn("ratio", str(cm.exception))
        r = self.build("gemini_omni_flash_1.1", options={"ratio": "640:360"},
                       inputs={"video": "t.mp4", "references": [{"path": "c.png"}]})
        self.assertEqual(r["body"], {"model": "gemini_omni_flash_1.1", "videoUri": "uri:video:t.mp4",
                                     "promptText": BASE_REQ["prompt"], "mode": "edit", "ratio": "640:360",
                                     "references": [{"uri": "uri:image:c.png"}]})
        self.assertEqual((r["tier"], r["out_seconds"], r["n_refs"], r["seed"]), ("360p", 10.0, 1, "first output"))
        self.assertTrue(any("seed" in w for w in r["warnings"]))

    def test_gemini_tiers_follow_the_ratio(self):
        for ratio, tier in (("640:360", "360p"), ("720:1280", "720p"), ("1920:1080", "1080p"), ("2160:3840", "4K")):
            self.assertEqual(self.build("gemini_omni_flash_1.1", options={"ratio": ratio})["tier"], tier)

    def test_gemini_reference_and_extend_need_a_duration_and_edit_is_capped_at_10_s(self):
        r = self.build("gemini_omni_flash_1.1", options={"mode": "reference", "ratio": "1280:720", "duration": 8})
        self.assertEqual((r["body"]["duration"], r["out_seconds"]), (8, 8))
        with self.assertRaises(rg.RequestError):
            self.build("gemini_omni_flash_1.1", options={"mode": "extend", "ratio": "1280:720"})
        long_clip = {**INFO_720, "seconds": 25.0}
        self.build("gemini_omni_flash_1.1", info=long_clip, options={"mode": "extend", "ratio": "1280:720", "duration": 5})
        with self.assertRaises(rg.RequestError):
            self.build("gemini_omni_flash_1.1", info=long_clip, options={"mode": "edit", "ratio": "1280:720"})

    def test_gemini_refusals(self):
        for why, kwargs in {
            "bad ratio": dict(options={"ratio": "16:9"}),
            "six references": dict(options={"ratio": "640:360"}, inputs={"references": [{"path": f"r{i}.png"} for i in range(6)]}),
            "keyframes": dict(options={"ratio": "640:360"}, inputs={"keyframes": [{"path": "k.png", "at": 0.5}]}),
            "prompt over 4000": dict(options={"ratio": "640:360"}, prompt="x" * 4001),
        }.items():
            with self.subTest(why), self.assertRaises(rg.RequestError):
                self.build("gemini_omni_flash_1.1", **kwargs)

    def test_options_a_model_does_not_use_are_ignored_with_a_warning(self):
        r = self.build("aleph2", options={"ratio": "16:9", "audio": False})
        self.assertTrue(any("ratio" in w for w in r["warnings"]))
        self.assertNotIn("ratio", r["body"])


class EstimateCommandTests(RunwayTestCase):
    def setUp(self):
        super().setUp()
        today = mock.patch.object(rg, "_today", return_value=date(2026, 11, 1))
        today.start()
        self.addCleanup(today.stop)

    def write(self, req, name="req.json"):
        f = self.tmp / name
        f.write_text(json.dumps(req))
        return f

    def estimate(self, req):
        code, out, err = self.run_cli("estimate", str(self.write(req)))
        return code, (json.loads(out) if out.strip() else None), err

    def test_estimate_reports_credits_and_makes_no_http_call(self):
        code, data, _ = self.estimate(make_req())
        self.assertEqual(code, 0)
        self.assertEqual(data["estimate_credits"], 450)
        self.assertEqual((data["model"], data["tier"], data["input_seconds"], data["output_seconds"]),
                         ("seedance2_5", "720p", 10.0, 10.0))
        self.assertEqual(data["request_sha256"], rg.sha256_json(make_req()))
        self.assertEqual(data["usd"], "4.50")
        self.assertEqual(self.api.calls, [])

    def test_estimate_for_each_model(self):
        cases = {
            "aleph2": (make_req("aleph2", options={}), 280),
            "kling_4": (make_req("kling_4", options={}), 151),     # list 188 -> promo 150.4 -> 151
            "gemini_omni_flash_1.1": (make_req("gemini_omni_flash_1.1", options={"ratio": "640:360"}), 44),
        }
        for model, (req, credits) in cases.items():
            with self.subTest(model):
                code, data, _ = self.estimate(req)
                self.assertEqual((code, data["estimate_credits"]), (0, credits))
        self.assertEqual(self.api.calls, [])

    def test_local_inputs_are_probed_and_checked_but_never_uploaded(self):
        (self.tmp / "take.mp4").write_bytes(bytes(2048))
        (self.tmp / "kf.png").write_bytes(bytes(2048))
        req = make_req("aleph2", options={}, inputs={"video": "take.mp4", "keyframes": [{"path": "kf.png", "at": 0.5}]})
        del req["inputs"]["video_info"]
        info = {"seconds": 12.0, "width": 1280, "height": 720, "fps": 24.0}
        with mock.patch.object(rg, "probe_video", return_value=info):
            code, data, _ = self.estimate(req)
        self.assertEqual((code, data["estimate_credits"]), (0, 336))     # 12 s * 28
        self.assertEqual(self.api.calls, [])

    def test_a_missing_local_input_fails_the_estimate(self):
        req = make_req("aleph2", options={}, inputs={"video": "gone.mp4"})
        del req["inputs"]["video_info"]
        code, data, err = self.estimate(req)
        self.assertEqual(code, 1)
        self.assertIn("gone.mp4", err)

    def test_warnings_go_to_stderr(self):
        _, _, err = self.estimate(make_req("kling_4", options={"audio": False}))
        self.assertIn("audio", err)


TID = "11111111-1111-4111-8111-111111111111"


class PaidCallTests(RunwayTestCase):
    def setUp(self):
        super().setUp()
        self.log = self.tmp / "logs" / "spend.jsonl"
        self.out = self.tmp / "out" / "clip.mp4"

    def route_create(self, est=450):
        self.api.on("POST", rg.BASE + "/video_to_video", {"id": TID, "estimatedCost": {"credits": est}})

    def route_task(self, *states):
        self.api.on("GET", rg.BASE + f"/tasks/{TID}", *states)

    def done(self, urls=(CDN + "/a.mp4",), cost=440):
        return {"id": TID, "status": "SUCCEEDED", "output": list(urls), "cost": {"credits": cost}}

    def call(self, **over):
        kw = dict(log=self.log, path="/video_to_video", body={"model": "seedance2_5"}, label="v2v:seedance2_5",
                  model="seedance2_5", est=450, input_seconds=10.0, request_sha="abc123", input_sha="def456",
                  seed=7, meta={"take": "t03"}, out=str(self.out), timeout=60)
        kw.update(over)
        return rg.paid_call(**kw)

    def rows(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_success_logs_three_rows_and_downloads_the_output(self):
        self.route_create()
        self.route_task({"id": TID, "status": "RUNNING", "progress": 0.4}, self.done())
        self.api.on("GET", CDN + "/a.mp4", b"MP4DATA")
        r = self.call()
        self.assertEqual(self.out.read_bytes(), b"MP4DATA")
        self.assertEqual((r["task_id"], r["paths"], r["cost_credits"]), (TID, [str(self.out)], 440))
        pre, created, final = self.rows()
        self.assertEqual([x["event"] for x in (pre, created, final)], ["pre", "created", "final"])
        self.assertEqual(len({x["call_id"] for x in (pre, created, final)}), 1)
        self.assertEqual((pre["model"], pre["input_seconds"], pre["request_sha256"], pre["our_estimate"], pre["seed"]),
                         ("seedance2_5", 10.0, "abc123", 450, 7))
        self.assertEqual(pre["meta"], {"take": "t03"})
        self.assertEqual((created["task_id"], created["estimated_cost_credits"]), (TID, 450))
        self.assertEqual((final["status"], final["cost_credits"], final["output_path"]), ("SUCCEEDED", 440, str(self.out)))

    def test_the_pre_row_is_on_disk_before_the_request_is_sent(self):
        seen = {}

        def at_submit(req):
            seen["log"] = self.log.read_text()
            return {"id": TID, "estimatedCost": {"credits": 450}}

        self.api.on("POST", rg.BASE + "/video_to_video", at_submit)
        self.route_task(self.done())
        self.api.on("GET", CDN + "/a.mp4", b"x")
        self.call()
        self.assertEqual([json.loads(line)["event"] for line in seen["log"].splitlines()], ["pre"])

    def test_a_crash_mid_poll_still_leaves_the_pre_and_created_rows(self):
        self.route_create()
        self.route_task(RuntimeError("disk on fire"))
        with self.assertRaises(RuntimeError):
            self.call()
        self.assertEqual([x["event"] for x in self.rows()], ["pre", "created"])
        self.assertEqual(self.rows()[1]["task_id"], TID)

    def test_ctrl_c_prints_the_task_id_and_how_to_fetch_it(self):
        def interrupt(req):
            raise KeyboardInterrupt

        self.route_create()
        self.route_task(interrupt)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(KeyboardInterrupt):
            self.call()
        self.assertIn(TID, err.getvalue())
        self.assertIn("fetch --task", err.getvalue())

    def test_a_timeout_never_cancels_and_prints_the_id(self):
        self.route_create()
        self.route_task({"id": TID, "status": "RUNNING"})
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            self.call(timeout=12)
        self.assertEqual(cm.exception.code, rg.EXIT_PENDING)
        self.assertIn(TID, err.getvalue())
        self.assertIn("NOT cancelled", err.getvalue())
        self.assertEqual([c for c in self.api.calls if c[0] == "DELETE"], [])
        self.assertEqual([x["event"] for x in self.rows()], ["pre", "created", "timeout"])

    def test_polling_slows_down_after_the_first_minute(self):
        self.route_create()
        self.route_task({"id": TID, "status": "RUNNING"})
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.call(timeout=90)
        delays = [c.args[0] for c in self.sleep.call_args_list]
        self.assertEqual(delays[:12], [rg.POLL_SECONDS] * 12)
        self.assertTrue(all(d == rg.POLL_SLOW_SECONDS for d in delays[12:]))

    def test_throttled_and_pending_are_not_failures(self):
        self.route_create()
        self.route_task({"id": TID, "status": "PENDING"}, {"id": TID, "status": "THROTTLED"}, self.done())
        self.api.on("GET", CDN + "/a.mp4", b"x")
        self.assertEqual(self.call()["task_id"], TID)

    def test_a_failed_task_logs_the_failure_code_and_exits_1(self):
        self.route_create()
        self.route_task({"id": TID, "status": "FAILED", "failure": "Input rejected", "failureCode": "SAFETY.INPUT.TEXT"})
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            self.call()
        self.assertEqual(cm.exception.code, rg.EXIT_FAILED)
        final = self.rows()[-1]
        self.assertEqual((final["event"], final["status"], final["failure_code"]), ("final", "FAILED", "SAFETY.INPUT.TEXT"))
        self.assertIsNone(final["cost_credits"])
        self.assertIn("not refunded", err.getvalue())

    def test_a_failed_download_still_writes_the_final_row_and_points_at_fetch(self):
        self.route_create()
        self.route_task(self.done())
        self.api.on("GET", CDN + "/a.mp4", 403)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            self.call()
        final = self.rows()[-1]
        self.assertEqual((final["status"], final["cost_credits"], final["output_path"]), ("SUCCEEDED", 440, None))
        self.assertIn("download_error", final)
        self.assertIn("fetch --task " + TID, err.getvalue())

    def test_a_submit_error_is_logged_and_re_raised(self):
        self.api.on("POST", rg.BASE + "/video_to_video", 400)
        with self.assertRaises(rg.ApiError):
            self.call()
        events = [x["event"] for x in self.rows()]
        self.assertEqual(events, ["pre", "submit_error"])

    def test_a_cap_far_above_our_estimate_is_called_out(self):
        self.route_create(est=900)
        self.route_task(self.done())
        self.api.on("GET", CDN + "/a.mp4", b"x")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.call()
        self.assertIn("estimatedCost", err.getvalue())
        self.assertIn("900", err.getvalue())

    def test_extra_outputs_get_numbered_names(self):
        self.route_create()
        self.route_task(self.done(urls=(CDN + "/a.mp4", CDN + "/b.mp4")))
        self.api.on("GET", CDN + "/a.mp4", b"A")
        self.api.on("GET", CDN + "/b.mp4", b"B")
        r = self.call()
        self.assertEqual(r["paths"], [str(self.out), str(self.out.with_name("clip-2.mp4"))])
        self.assertEqual(self.out.with_name("clip-2.mp4").read_bytes(), b"B")

    def test_no_row_and_no_message_contains_the_api_key(self):
        self.route_create()
        self.route_task(self.done())
        self.api.on("GET", CDN + "/a.mp4", b"x")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.call()
        self.assertNotIn(TEST_KEY, self.log.read_text())
        self.assertNotIn(TEST_KEY, err.getvalue())

    def test_a_missing_estimate_is_logged_as_null(self):
        self.route_create()
        self.route_task(self.done())
        self.api.on("GET", CDN + "/a.mp4", b"x")
        self.call(est=None)
        self.assertIsNone(self.rows()[0]["our_estimate"])


class CliTests(RunwayTestCase):
    def setUp(self):
        super().setUp()
        self.log = self.tmp / "spend.jsonl"
        default = mock.patch.object(rg, "DEFAULT_LOG", self.tmp / "default-spend.jsonl")   # never touch the real log
        default.start()
        self.addCleanup(default.stop)
        eval_root = mock.patch.object(rg, "EVAL_OUT_ROOT", self.tmp / "eval-root")         # nor the real out/ folder
        eval_root.start()
        self.addCleanup(eval_root.stop)

    def write_req(self, req):
        f = self.tmp / "req.json"
        f.write_text(json.dumps(req))
        return str(f)

    def rows(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def route_task(self, create_path, tid, urls, cost):
        self.api.on("POST", rg.BASE + create_path, {"id": tid, "estimatedCost": {"credits": cost}})
        self.api.on("GET", rg.BASE + f"/tasks/{tid}",
                    {"id": tid, "status": "SUCCEEDED", "output": urls, "cost": {"credits": cost}})

    # --- the guard ---
    def test_every_paid_command_refuses_without_yes_and_sends_nothing(self):
        (self.tmp / "take.mp4").write_bytes(bytes(2048))
        local = make_req("aleph2", options={}, inputs={"video": "take.mp4"})
        del local["inputs"]["video_info"]
        info = {"seconds": 10.0, "width": 1280, "height": 720, "fps": 24.0}
        commands = {
            "eval": ["eval"],
            "image": ["image", "--prompt", "a cat", "--out", str(self.tmp / "o.png")],
            "video": ["video", "--image", "https://e.test/a.png", "--prompt", "p", "--out", str(self.tmp / "o.mp4")],
            "v2v remote": ["v2v", self.write_req(make_req()), "--out", str(self.tmp / "o.mp4")],
            "v2v local": ["v2v", self.write_req(local), "--out", str(self.tmp / "o.mp4")],
        }
        for name, argv in commands.items():
            with self.subTest(name), mock.patch.object(rg, "probe_video", return_value=info):
                code, _, err = self.run_cli(*argv, "--log", str(self.log))
                self.assertEqual(code, rg.EXIT_REFUSED)
                self.assertIn("--yes", err)
                self.assertRegex(err, r"estimate")
        self.assertEqual(self.api.calls, [])
        self.assertFalse(self.log.exists())

    def test_the_refusal_shows_the_number(self):
        _, _, err = self.run_cli("v2v", self.write_req(make_req()), "--out", str(self.tmp / "o.mp4"))
        self.assertIn("450", err)
        _, _, err = self.run_cli("video", "--image", "https://e.test/a.png", "--duration", "10", "--out", str(self.tmp / "o.mp4"))
        self.assertIn("50", err)

    def test_an_unknown_model_cost_is_unknown_but_still_needs_yes(self):
        code, _, err = self.run_cli("image", "--model", "no_such_model", "--prompt", "x", "--out", str(self.tmp / "o.png"))
        self.assertEqual(code, rg.EXIT_REFUSED)
        self.assertIn("unknown", err)

    def test_max_credits_refuses_even_with_yes(self):
        code, _, err = self.run_cli("v2v", self.write_req(make_req()), "--out", str(self.tmp / "o.mp4"),
                                    "--yes", "--max-credits", "100", "--log", str(self.log))
        self.assertEqual(code, rg.EXIT_REFUSED)
        self.assertIn("max-credits", err)
        self.assertEqual(self.api.calls, [])

    # --- v2v end to end ---
    def test_v2v_uploads_submits_waits_downloads_and_logs(self):
        (self.tmp / "take.mp4").write_bytes(b"VIDEOBYTES" * 100)
        (self.tmp / "kf.png").write_bytes(bytes(2048))
        req = make_req("aleph2", options={}, inputs={
            "video": "take.mp4", "keyframes": [{"path": "kf.png", "seconds": 3.5}]})
        del req["inputs"]["video_info"]
        self.api.on("POST", rg.BASE + "/uploads", {"uploadUrl": UPLOAD_URL, "fields": {"key": "k"},
                                                   "runwayUri": "runway://upload/abc"})
        self.api.on("POST", UPLOAD_URL, b"")
        self.route_task("/video_to_video", TID, [CDN + "/out.mp4"], 280)
        self.api.on("GET", CDN + "/out.mp4", b"RESULT")
        out = self.tmp / "renders" / "t03.mp4"
        info = {"seconds": 10.0, "width": 1280, "height": 720, "fps": 24.0}
        with mock.patch.object(rg, "probe_video", return_value=info):
            code, stdout, _ = self.run_cli("v2v", self.write_req(req), "--out", str(out), "--yes", "--log", str(self.log))
        self.assertEqual(code, 0)
        self.assertEqual(out.read_bytes(), b"RESULT")
        sent = json.loads(self.api.to("POST", rg.BASE + "/video_to_video")[0][3])
        self.assertEqual(sent["videoUri"], "runway://upload/abc")
        self.assertTrue(sent["keyframes"][0]["uri"].startswith("data:image/png;base64,"))
        self.assertEqual(sent["seed"], 7)
        order = [c[1] for c in self.api.calls]
        self.assertLess(order.index(rg.BASE + "/uploads"), order.index(rg.BASE + "/video_to_video"))
        result = json.loads(stdout)
        self.assertEqual((result["task_id"], result["cost_credits"], result["paths"]), (TID, 280, [str(out)]))
        pre, created, final = self.rows()
        self.assertEqual(pre["our_estimate"], 280)
        self.assertEqual(pre["input_sha256"], hashlib.sha256(b"VIDEOBYTES" * 100).hexdigest())
        self.assertEqual(pre["request_sha256"], rg.sha256_json(req))
        self.assertEqual(pre["meta"], {"take": "t03", "material": "ink", "purpose": "probe"})
        self.assertEqual((created["estimated_cost_credits"], final["cost_credits"]), (280, 280))

    def test_v2v_logs_first_output_when_no_seed_is_sent(self):
        req = make_req("kling_4", options={}, seed=None)
        del req["seed"]
        self.route_task("/video_to_video", TID, [CDN + "/out.mp4"], 100)
        self.api.on("GET", CDN + "/out.mp4", b"R")
        code, _, _ = self.run_cli("v2v", self.write_req(req), "--out", str(self.tmp / "o.mp4"), "--yes", "--log", str(self.log))
        self.assertEqual(code, 0)
        self.assertEqual(self.rows()[0]["seed"], "first output")

    # --- legacy commands, now guarded and logged ---
    def test_image_with_yes_logs_the_seed_and_saves_the_file(self):
        self.route_task("/text_to_image", TID, [CDN + "/s.png"], 5)
        self.api.on("GET", CDN + "/s.png", b"PNG")
        out = self.tmp / "s.png"
        code, stdout, _ = self.run_cli("image", "--prompt", "a cat", "--seed", "5", "--out", str(out), "--yes", "--log", str(self.log))
        self.assertEqual(code, 0)
        self.assertEqual(out.read_bytes(), b"PNG")
        self.assertEqual(json.loads(stdout), [CDN + "/s.png"])
        pre = self.rows()[0]
        self.assertEqual((pre["model"], pre["our_estimate"], pre["seed"]), ("gemini_2.5_flash", 5, 5))

    def test_video_with_yes_prices_by_the_second(self):
        self.route_task("/image_to_video", TID, [CDN + "/v.mp4"], 25)
        self.api.on("GET", CDN + "/v.mp4", b"V")
        code, _, _ = self.run_cli("video", "--image", "https://e.test/a.png", "--prompt", "p",
                                  "--out", str(self.tmp / "v.mp4"), "--yes", "--log", str(self.log))
        self.assertEqual(code, 0)
        self.assertEqual(self.rows()[0]["our_estimate"], 25)

    # --- video --seed (sub-plan B, task B1) ---
    def test_video_seed_is_sent_and_logged_in_the_pre_row(self):
        self.route_task("/image_to_video", TID, [CDN + "/v.mp4"], 60)
        self.api.on("GET", CDN + "/v.mp4", b"V")
        code, _, _ = self.run_cli("video", "--model", "gen4.5", "--image", "https://e.test/a.png", "--prompt", "p",
                                  "--duration", "5", "--seed", "123456", "--out", str(self.tmp / "v.mp4"), "--yes",
                                  "--log", str(self.log))
        self.assertEqual(code, 0)
        sent = json.loads(self.api.to("POST", rg.BASE + "/image_to_video")[0][3])
        self.assertEqual((sent["seed"], sent["model"], sent["duration"]), (123456, "gen4.5", 5))
        self.assertEqual(self.rows()[0]["seed"], 123456)

    def test_video_without_a_seed_sends_none_and_logs_first_output(self):
        self.route_task("/image_to_video", TID, [CDN + "/v.mp4"], 25)
        self.api.on("GET", CDN + "/v.mp4", b"V")
        code, _, _ = self.run_cli("video", "--image", "https://e.test/a.png", "--prompt", "p",
                                  "--out", str(self.tmp / "v.mp4"), "--yes", "--log", str(self.log))
        self.assertEqual(code, 0)
        sent = json.loads(self.api.to("POST", rg.BASE + "/image_to_video")[0][3])
        self.assertNotIn("seed", sent)
        self.assertEqual(self.rows()[0]["seed"], "first output")

    def test_video_seed_zero_is_a_seed(self):
        self.route_task("/image_to_video", TID, [CDN + "/v.mp4"], 60)
        self.api.on("GET", CDN + "/v.mp4", b"V")
        code, _, _ = self.run_cli("video", "--model", "gen4.5", "--image", "https://e.test/a.png", "--seed", "0",
                                  "--out", str(self.tmp / "v.mp4"), "--yes", "--log", str(self.log))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.api.to("POST", rg.BASE + "/image_to_video")[0][3])["seed"], 0)

    def test_video_seed_out_of_range_or_on_a_model_without_one_is_refused_before_anything_is_sent(self):
        for argv in (["--model", "gen4.5", "--seed", "4294967296"], ["--model", "gen4.5", "--seed", "-1"],
                     ["--model", "wan3", "--seed", "5"]):
            with self.subTest(argv):
                code, _, err = self.run_cli("video", "--image", "https://e.test/a.png", *argv,
                                            "--out", str(self.tmp / "v.mp4"), "--yes", "--log", str(self.log))
                self.assertEqual(code, 1)
                self.assertIn("seed", err)
        self.assertEqual(self.api.calls, [])
        self.assertFalse(self.log.exists())

    def test_eval_with_yes_runs_a_still_then_a_clip_and_logs_both(self):
        self.api.on("POST", rg.BASE + "/text_to_image", {"id": "img1", "estimatedCost": {"credits": 4}})
        self.api.on("GET", rg.BASE + "/tasks/img1", {"id": "img1", "status": "SUCCEEDED", "output": [CDN + "/e.png"], "cost": {"credits": 4}})
        self.api.on("POST", rg.BASE + "/image_to_video", {"id": "vid1", "estimatedCost": {"credits": 25}})
        self.api.on("GET", rg.BASE + "/tasks/vid1", {"id": "vid1", "status": "SUCCEEDED", "output": [CDN + "/e.mp4"], "cost": {"credits": 25}})
        self.api.on("GET", CDN + "/e.png", b"STILL")
        self.api.on("GET", CDN + "/e.mp4", b"CLIP")
        out_dir = self.tmp / "eval-out"
        code, _, _ = self.run_cli("eval", "--yes", "--log", str(self.log), "--out-dir", str(out_dir))
        self.assertEqual(code, 0)
        self.assertEqual((out_dir / "still.png").read_bytes(), b"STILL")
        self.assertEqual((out_dir / "clip.mp4").read_bytes(), b"CLIP")
        pres = [r for r in self.rows() if r["event"] == "pre"]
        self.assertEqual([(r["label"], r["our_estimate"]) for r in pres], [("eval-image", 5), ("eval-video", 25)])
        sent = json.loads(self.api.to("POST", rg.BASE + "/image_to_video")[0][3])
        self.assertEqual(sent["promptImage"], CDN + "/e.png")

    def test_eval_is_priced_as_both_calls_together(self):
        _, _, err = self.run_cli("eval")
        self.assertIn("~30 credits", err)     # 5 (gemini_2.5_flash, docs 3 Nov 2026) + 25; it was 29 at 4 + 25

    # --- fetch ---
    def test_fetch_downloads_logs_and_needs_no_yes(self):
        self.api.on("GET", rg.BASE + f"/tasks/{TID}", {"id": TID, "status": "SUCCEEDED", "output": [CDN + "/o.mp4"], "cost": {"credits": 280}})
        self.api.on("GET", CDN + "/o.mp4", b"LATE")
        out = self.tmp / "late.mp4"
        code, stdout, _ = self.run_cli("fetch", "--task", TID, "--out", str(out), "--log", str(self.log))
        self.assertEqual(code, 0)
        self.assertEqual(out.read_bytes(), b"LATE")
        row = self.rows()[0]
        self.assertEqual((row["event"], row["task_id"], row["cost_credits"], row["output_path"]), ("fetch", TID, 280, str(out)))
        self.assertEqual(json.loads(stdout)["paths"], [str(out)])

    def test_fetch_of_a_running_task_exits_4_and_of_a_failed_task_exits_1(self):
        self.api.on("GET", rg.BASE + f"/tasks/{TID}", {"id": TID, "status": "RUNNING"})
        code, _, _ = self.run_cli("fetch", "--task", TID, "--out", str(self.tmp / "x.mp4"), "--log", str(self.log))
        self.assertEqual(code, rg.EXIT_PENDING)
        self.api.on("GET", rg.BASE + f"/tasks/{TID}", {"id": TID, "status": "FAILED", "failure": "nope", "failureCode": "INTERNAL"})
        code, _, _ = self.run_cli("fetch", "--task", TID, "--out", str(self.tmp / "x.mp4"), "--log", str(self.log))
        self.assertEqual(code, rg.EXIT_FAILED)

    def test_the_old_submit_helper_is_gone(self):
        self.assertFalse(hasattr(rg, "_submit_and_wait"))


class RobustnessTests(RunwayTestCase):
    """Gaps found in review: polling errors, upload network errors, upload error echo, --max-credits with no estimate."""

    # --- 1. ApiError / RequestError while polling ---
    def paid(self, log):
        return rg.paid_call(log=log, path="/video_to_video", body={"model": "seedance2_5"}, label="v2v:seedance2_5",
                            model="seedance2_5", est=450, out=str(self.tmp / "o.mp4"), timeout=60)

    def test_an_api_error_while_polling_keeps_the_task_recoverable(self):
        log = self.tmp / "spend.jsonl"
        self.api.on("POST", rg.BASE + "/video_to_video", {"id": TID, "estimatedCost": {"credits": 450}})
        self.api.on("GET", rg.BASE + f"/tasks/{TID}", 401)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            self.paid(log)
        self.assertNotEqual(cm.exception.code, 0)
        self.assertIn(TID, err.getvalue())
        self.assertIn("fetch --task " + TID, err.getvalue())
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual([r["event"] for r in rows], ["pre", "created", "poll_error"])
        self.assertEqual((rows[-1]["task_id"], rows[-1]["status"]), (TID, 401))
        self.assertIn("401", rows[-1]["error"])

    def test_a_request_error_while_polling_is_recoverable_too(self):
        log = self.tmp / "spend.jsonl"
        self.api.on("POST", rg.BASE + "/video_to_video", {"id": TID, "estimatedCost": {"credits": 450}})
        self.api.on("GET", rg.BASE + f"/tasks/{TID}", rg.RequestError("bad thing"))
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            self.paid(log)
        self.assertNotEqual(cm.exception.code, 0)
        self.assertIn("fetch --task " + TID, err.getvalue())
        self.assertEqual(json.loads(log.read_text().splitlines()[-1])["event"], "poll_error")

    # --- 2. upload network failures ---
    def slot(self):
        self.api.on("POST", rg.BASE + "/uploads", {"uploadUrl": UPLOAD_URL, "fields": {"key": "k1", "policy": "p1"},
                                                   "runwayUri": "runway://upload/abc"})

    def clip(self):
        f = self.tmp / "clip.mp4"
        f.write_bytes(bytes(2048))
        return f

    def test_upload_network_failures_exit_cleanly_without_retry(self):
        for exc in (urllib.error.URLError("reset"), TimeoutError("timed out"), ConnectionResetError("reset")):
            with self.subTest(type(exc).__name__):
                self.api.calls.clear()
                self.slot()
                self.api.on("POST", UPLOAD_URL, exc)
                code, _, err = self.run_cli("upload", str(self.clip()))
                self.assertEqual(code, 1)
                self.assertEqual(len(self.api.to("POST", UPLOAD_URL)), 1)
                self.assertEqual(len(err.strip().splitlines()), 1)
                self.assertNotIn("p1", err)
                self.assertNotIn(UPLOAD_URL, err)
                self.assertNotIn("Traceback", err)

    # --- 3. upload error echo ---
    def upload_error_text(self, body):
        import email.message
        err = urllib.error.HTTPError(UPLOAD_URL, 403, "Forbidden", email.message.Message(), io.BytesIO(body))
        self.slot()
        self.api.on("POST", UPLOAD_URL, err)
        with self.assertRaises(rg.ApiError) as cm:
            rg.upload_file(self.clip())
        return str(cm.exception)

    def test_upload_error_prints_the_status_and_only_the_xml_code(self):
        xml = (b'<?xml version="1.0"?><Error><Code>AccessDenied</Code><Message>nope</Message>'
               b'<AWSAccessKeyId>AKIAEXAMPLEKEY123456</AWSAccessKeyId><RequestId>r1</RequestId></Error>')
        text = self.upload_error_text(xml)
        self.assertIn("403", text)
        self.assertIn("AccessDenied", text)
        for leaked in ("AKIAEXAMPLEKEY123456", "nope", "r1", "AWSAccessKeyId"):
            self.assertNotIn(leaked, text)

    def test_upload_error_without_a_code_echoes_nothing_from_the_body(self):
        text = self.upload_error_text(b"secret-looking body AKIAEXAMPLEKEY123456")
        self.assertIn("403", text)
        self.assertNotIn("AKIAEXAMPLEKEY123456", text)
        self.assertNotIn("secret-looking", text)

    # --- 4. --max-credits with an unknown estimate ---
    def test_max_credits_with_an_unknown_estimate_refuses_even_with_yes(self):
        code, _, err = self.run_cli("image", "--model", "no_such_model", "--prompt", "x", "--yes", "--out", str(self.tmp / "o.png"),
                                    "--max-credits", "100", "--log", str(self.tmp / "spend.jsonl"))
        self.assertEqual(code, rg.EXIT_REFUSED)
        self.assertIn("max-credits", err)
        self.assertEqual(self.api.calls, [])
        self.assertFalse((self.tmp / "spend.jsonl").exists())


class ResponseHandlingTests(RunwayTestCase):
    """Quality-review fixes: malformed responses, fetch download failures, Ctrl-C traces, mandatory downloads."""

    def setUp(self):
        super().setUp()
        default = mock.patch.object(rg, "DEFAULT_LOG", self.tmp / "default-spend.jsonl")   # never touch the real log
        default.start()
        self.addCleanup(default.stop)

    def paid(self, log, **over):
        kw = dict(log=log, path="/video_to_video", body={"model": "seedance2_5"}, label="v2v:seedance2_5",
                  model="seedance2_5", est=450, out=str(self.tmp / "o.mp4"), timeout=60)
        kw.update(over)
        return rg.paid_call(**kw)

    def events(self, log):
        return [json.loads(line) for line in pathlib.Path(log).read_text().splitlines()]

    # --- 1. malformed responses ---
    def test_a_malformed_200_becomes_an_apierror(self):
        for body in (b"<html>gateway</html>", b"[1, 2]", b"\xff\xfe"):
            with self.subTest(body):
                self.api.on("GET", rg.BASE + "/tasks/t1", body)
                with self.assertRaises(rg.ApiError) as cm:
                    rg._req("GET", "/tasks/t1")
                self.assertIn("invalid JSON", str(cm.exception))

    def test_a_truncated_body_is_a_network_error_retried_on_get_but_not_post(self):
        import http.client
        self.api.on("GET", rg.BASE + "/tasks/t1", http.client.IncompleteRead(b"par"), {"ok": 1})
        self.assertEqual(rg._req("GET", "/tasks/t1"), {"ok": 1})
        self.api.calls.clear()
        self.api.on("POST", rg.BASE + "/video_to_video", http.client.IncompleteRead(b"par"))
        with self.assertRaises(rg.ApiError) as cm:
            rg._req("POST", "/video_to_video", {})
        self.assertEqual((cm.exception.status, len(self.api.calls)), (0, 1))

    def test_an_unparseable_submit_response_logs_submit_unparsed_and_warns(self):
        log = self.tmp / "spend.jsonl"
        self.api.on("POST", rg.BASE + "/video_to_video", b"<html>oops</html>")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            self.paid(log)
        self.assertNotEqual(cm.exception.code, 0)
        self.assertEqual([r["event"] for r in self.events(log)], ["pre", "submit_unparsed"])
        self.assertIn("dashboard", err.getvalue())
        self.assertIn("may exist", err.getvalue())

    def test_a_submit_response_without_a_task_id_is_also_submit_unparsed(self):
        log = self.tmp / "spend.jsonl"
        self.api.on("POST", rg.BASE + "/video_to_video", {"unexpected": True})
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.paid(log)
        self.assertEqual([r["event"] for r in self.events(log)], ["pre", "submit_unparsed"])

    def test_malformed_json_while_polling_still_leaves_a_poll_error_and_the_hint(self):
        log = self.tmp / "spend.jsonl"
        self.api.on("POST", rg.BASE + "/video_to_video", {"id": TID, "estimatedCost": {"credits": 450}})
        self.api.on("GET", rg.BASE + f"/tasks/{TID}", b"not json")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            self.paid(log)
        self.assertEqual([r["event"] for r in self.events(log)], ["pre", "created", "poll_error"])
        self.assertIn("fetch --task " + TID, err.getvalue())

    # --- 2. fetch: expired output URLs ---
    def test_fetch_with_an_expired_output_url_logs_the_failure_and_exits_1(self):
        log = self.tmp / "spend.jsonl"
        for status in (403, 410):
            with self.subTest(status):
                log.unlink(missing_ok=True)
                self.api.on("GET", rg.BASE + f"/tasks/{TID}",
                            {"id": TID, "status": "SUCCEEDED", "output": [CDN + "/o.mp4"], "cost": {"credits": 280}})
                self.api.on("GET", CDN + "/o.mp4", status)
                code, stdout, err = self.run_cli("fetch", "--task", TID, "--out", str(self.tmp / "x.mp4"), "--log", str(log))
                self.assertEqual(code, rg.EXIT_FAILED)
                self.assertEqual(stdout, "")
                self.assertEqual(len(err.strip().splitlines()), 1)
                self.assertIn("expired", err)
                row = self.events(log)[0]
                self.assertEqual((row["event"], row["output_path"]), ("fetch", None))
                self.assertIn(str(status), row["download_error"])

    # --- 3. Ctrl-C leaves a trace ---
    def test_ctrl_c_while_polling_logs_interrupted_with_the_task_id(self):
        log = self.tmp / "spend.jsonl"

        def interrupt(req):
            raise KeyboardInterrupt

        self.api.on("POST", rg.BASE + "/video_to_video", {"id": TID, "estimatedCost": {"credits": 450}})
        self.api.on("GET", rg.BASE + f"/tasks/{TID}", interrupt)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(KeyboardInterrupt):
            self.paid(log)
        rows = self.events(log)
        self.assertEqual([r["event"] for r in rows], ["pre", "created", "interrupted"])
        self.assertEqual(rows[-1]["task_id"], TID)
        self.assertEqual(rows[-1]["call_id"], rows[0]["call_id"])

    def test_ctrl_c_during_the_submit_logs_submit_interrupted_and_warns(self):
        log = self.tmp / "spend.jsonl"

        def interrupt(req):
            raise KeyboardInterrupt

        self.api.on("POST", rg.BASE + "/video_to_video", interrupt)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(KeyboardInterrupt):
            self.paid(log)
        self.assertEqual([r["event"] for r in self.events(log)], ["pre", "submit_interrupted"])
        self.assertIn("may exist", err.getvalue())
        self.assertIn("dashboard", err.getvalue())

    # --- 4. paid outputs are always downloaded ---
    def test_image_and_video_require_out(self):
        for argv in (["image", "--prompt", "a cat"], ["video", "--image", "https://e.test/a.png"]):
            with self.subTest(argv[0]):
                code, _, err = self.run_cli(*argv, "--yes")
                self.assertEqual(code, 2)
                self.assertIn("--out", err)
        self.assertEqual(self.api.calls, [])

    def test_eval_refusal_creates_no_directory_but_a_yes_run_uses_the_default_one(self):
        root = self.tmp / "eval-root"
        with mock.patch.object(rg, "EVAL_OUT_ROOT", root):
            code, _, _ = self.run_cli("eval", "--log", str(self.tmp / "s.jsonl"))
            self.assertEqual(code, rg.EXIT_REFUSED)
            self.assertFalse(root.exists())
            self.api.on("POST", rg.BASE + "/text_to_image", {"id": "img1", "estimatedCost": {"credits": 4}})
            self.api.on("GET", rg.BASE + "/tasks/img1", {"id": "img1", "status": "SUCCEEDED", "output": [CDN + "/e.png"], "cost": {"credits": 4}})
            self.api.on("POST", rg.BASE + "/image_to_video", {"id": "vid1", "estimatedCost": {"credits": 25}})
            self.api.on("GET", rg.BASE + "/tasks/vid1", {"id": "vid1", "status": "SUCCEEDED", "output": [CDN + "/e.mp4"], "cost": {"credits": 25}})
            self.api.on("GET", CDN + "/e.png", b"S")
            self.api.on("GET", CDN + "/e.mp4", b"C")
            code, _, _ = self.run_cli("eval", "--yes", "--log", str(self.tmp / "s.jsonl"))
        self.assertEqual(code, 0)
        (folder,) = list(root.iterdir())
        self.assertRegex(folder.name, r"^eval-\d{8}-\d{6}$")
        self.assertEqual((folder / "still.png").read_bytes(), b"S")
        self.assertEqual((folder / "clip.mp4").read_bytes(), b"C")

    # --- minor ---
    def test_image_without_a_prompt_is_a_clean_request_error(self):
        out = str(self.tmp / "o.png")
        for argv in (["image", "--out", out], ["image", "--prompt-file", "pack.md", "--out", out]):
            with self.subTest(argv):
                code, _, err = self.run_cli(*argv)
                self.assertEqual(code, 1)
                self.assertIn("--prompt", err)
                self.assertNotIn("Traceback", err)
        self.assertEqual(self.api.calls, [])

    def test_the_seed_field_helper_is_inlined(self):
        self.assertFalse(hasattr(rg, "_seed_field"))


def png_bytes(w, h):
    """A PNG that is just a signature and an IHDR chunk: enough for the client to read its size."""
    import struct
    import zlib
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))


def jpeg_bytes(w, h, sof=0xC0):
    """A JPEG that is only markers: SOI, APP0 (JFIF), a DQT to skip, then the SOF (0xC0 baseline, 0xC2 progressive)."""
    import struct
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    dqt = b"\xff\xdb" + struct.pack(">H", 67) + bytes(65)
    sof_seg = bytes([0xFF, sof]) + struct.pack(">HBHHB", 17, 8, h, w, 3) + bytes(9)
    return b"\xff\xd8" + app0 + dqt + sof_seg + b"\xff\xd9"


class NanoBananaEstimateTests(RunwayTestCase):
    """nano_banana_2.1 and image_upscale, read from docs.dev.runwayml.com on 3 Nov 2026 (live call pending)."""

    def test_nano_banana_prices_by_resolution_tier(self):
        self.assertEqual(rg.estimate_simple("nano_banana_2.1", resolution="1K"), 4)
        self.assertEqual(rg.estimate_simple("nano_banana_2.1", resolution="2K"), 6)
        self.assertEqual(rg.estimate_simple("nano_banana_2.1", resolution="4K"), 12)

    def test_nano_banana_without_a_resolution_estimates_the_dearest_tier(self):
        self.assertEqual(rg.estimate_simple("nano_banana_2.1"), 12)

    def test_an_unknown_resolution_is_refused(self):
        with self.assertRaises(ValueError):
            rg.estimate_simple("nano_banana_2.1", resolution="8K")

    def test_other_models_ignore_resolution_and_existing_calls_still_work(self):
        self.assertEqual(rg.estimate_simple("gemini_2.5_flash", resolution="2K"), 5)
        self.assertEqual(rg.estimate_simple("gen4_turbo", 5), 25)

    def test_nano_banana_pro_is_gone(self):
        self.assertNotIn("nano_banana_pro", rg.COST)    # no longer listed by the docs (3 Nov 2026)

    def test_upscale_is_25_credits_until_the_output_passes_4096_px_either_way_we_read_it(self):
        # The docs say "150 credits when output exceeds 4096px" and do not say edge or pixels, so we price 150 when the
        # longest output edge is over 4096 OR the output area is over 4096 x 2160 (8,847,360 px). Unconfirmed until a live call.
        self.assertEqual(rg.estimate_upscale(1000, 1000, 2), 25)      # 2000x2000 = 4.0 MP
        self.assertEqual(rg.estimate_upscale(2048, 1000, 2), 25)      # 4096 is not "over 4096": 4096x2000 = 8.19 MP
        self.assertEqual(rg.estimate_upscale(1400, 1500, 2), 25)      # 2800x3000 = 8.4 MP
        self.assertEqual(rg.estimate_upscale(2049, 1000, 2), 150)     # longest edge 4098
        self.assertEqual(rg.estimate_upscale(1500, 1500, 2), 150)     # edges fine, 3000x3000 = 9 MP is over the area
        self.assertEqual(rg.estimate_upscale(1000, 1000, 4), 150)     # 4000x4000 = 16 MP
        self.assertEqual(rg.estimate_upscale(2048, 1500, 2), 150)     # 4096x3000 = 12.3 MP
        self.assertEqual(rg.estimate_upscale(1100, 1000, 4), 150)

    def test_upscale_refuses_another_model_rather_than_misprice_it(self):
        with self.assertRaisesRegex(rg.RequestError, rg.UPSCALE_MODEL):
            rg.estimate_upscale(1000, 1000, 2, model="some_other_upscaler")

    def test_upscale_with_an_unknown_input_size_assumes_the_dearer_price(self):
        self.assertEqual(rg.estimate_upscale(None, None, 2), 150)

    def test_upscale_refuses_inputs_the_docs_refuse(self):
        for w, h, scale in ((299, 1000, 2), (1000, 8001, 2), (6000, 5000, 2)):    # <300 px, >8000 px, output > 25.3 MP
            with self.subTest((w, h, scale)), self.assertRaises(rg.RequestError):
                rg.estimate_upscale(w, h, scale)


class ImageSizeTests(RunwayTestCase):
    def size(self, data):
        f = self.tmp / "x.bin"
        f.write_bytes(data)
        return rg.image_size(f)

    def test_png(self):
        self.assertEqual(self.size(png_bytes(1234, 567)), (1234, 567))

    def test_baseline_jpeg_skips_app0_and_dqt_to_reach_sof0(self):
        self.assertEqual(self.size(jpeg_bytes(1234, 567, 0xC0)), (1234, 567))

    def test_progressive_jpeg_sof2(self):
        self.assertEqual(self.size(jpeg_bytes(4000, 3000, 0xC2)), (4000, 3000))

    def test_something_else_or_a_truncated_jpeg_is_none(self):
        self.assertIsNone(self.size(b"GIF89a" + bytes(30)))
        self.assertIsNone(self.size(jpeg_bytes(10, 10)[:25]))


class NanoBananaRequestTests(RunwayTestCase):
    def test_a_reference_count_over_the_models_limit_is_refused(self):
        refs = lambda n: [{"uri": "https://e.test/a.png", "tag": f"ref{i:02d}"} for i in range(n)]
        rg.check_image_request("nano_banana_2.1", "1584:672", refs(14), None)
        with self.assertRaisesRegex(rg.RequestError, "nano_banana_2.1 takes at most 14 reference images; 15 given"):
            rg.check_image_request("nano_banana_2.1", "1584:672", refs(15), None)
        rg.check_image_request("gen4_image", "1920:1080", refs(3), None)
        with self.assertRaisesRegex(rg.RequestError, "gen4_image takes at most 3 reference images; 4 given"):
            rg.check_image_request("gen4_image", "1920:1080", refs(4), None)
        with self.assertRaises(rg.RequestError):
            rg.check_image_request("gemini_2.5_flash", "1344:768", refs(4), None)

    def test_a_ratio_outside_the_models_list_is_refused(self):
        with self.assertRaisesRegex(rg.RequestError, "1344:768"):
            rg.check_image_request("nano_banana_2.1", "1344:768", [], None)

    def test_nano_banana_has_no_seed(self):
        with self.assertRaisesRegex(rg.RequestError, "seed"):
            rg.check_image_request("nano_banana_2.1", "1584:672", [], 5)

    def test_nano_banana_tags_must_be_lowercase_and_start_with_a_letter(self):
        for tag in ("Ref01", "1ref", "re-f"):
            with self.subTest(tag), self.assertRaisesRegex(rg.RequestError, "tag"):
                rg.check_image_request("nano_banana_2.1", "1584:672", [{"uri": "https://e.test/a.png", "tag": tag}], None)

    def test_every_tier_lists_the_same_fourteen_aspects(self):
        tiers = rg.NANO_BANANA_RATIOS
        self.assertEqual(set(tiers), {"1K", "2K", "4K"})
        self.assertEqual({len(v) for v in tiers.values()}, {14})
        scaled = lambda ratio, k: ":".join(str(int(n) * k) for n in ratio.split(":"))
        for i, one_k in enumerate(tiers["1K"]):
            self.assertEqual(tiers["2K"][i], scaled(one_k, 2), one_k)      # same aspect, every edge doubled
            self.assertEqual(tiers["4K"][i], scaled(one_k, 4), one_k)      # ... and quadrupled
        self.assertEqual(tiers["1K"][9], "1584:672")      # the widest common panorama, about 2.36:1
        self.assertEqual(tiers["2K"][9], "3168:1344")
        self.assertEqual(tiers["4K"][9], "6336:2688")

    def test_resolution_moves_a_ratio_to_the_same_aspect_in_another_tier(self):
        self.assertEqual(rg.resolve_nano_ratio("1584:672", "2K"), ("3168:1344", "2K"))
        self.assertEqual(rg.resolve_nano_ratio("3168:1344", "4K"), ("6336:2688", "4K"))
        self.assertEqual(rg.resolve_nano_ratio("3168:1344", None), ("3168:1344", "2K"))
        self.assertEqual(rg.resolve_nano_ratio(None, "4K"), ("6336:2688", "4K"))
        self.assertEqual(rg.resolve_nano_ratio(None, None), ("1584:672", "1K"))
        with self.assertRaises(rg.RequestError):
            rg.resolve_nano_ratio("1344:768", "2K")


class NanoBananaTagTests(RunwayTestCase):
    def test_a_bare_reference_gets_a_lowercase_tag_the_api_accepts_for_nano_banana(self):
        refs = rg._parse_refs(["https://e.test/Octopus_MASTER.jpeg", "https://e.test/01 Panel-A.png"], nano=True)
        self.assertEqual([r["tag"] for r in refs], ["octopus_master", "ref_01_panel_a"])
        for r in refs:
            rg.check_image_request("nano_banana_2.1", "1584:672", [r], None)

    def test_the_inferred_tag_for_the_other_models_is_unchanged(self):
        refs = rg._parse_refs(["https://e.test/Octopus_MASTER.jpeg"])
        self.assertEqual(refs[0]["tag"], "OctopusMASTER")


class NanoBananaCliTests(RunwayTestCase):
    def setUp(self):
        super().setUp()
        self.log = self.tmp / "spend.jsonl"
        default = mock.patch.object(rg, "DEFAULT_LOG", self.tmp / "default-spend.jsonl")   # never touch the real log
        default.start()
        self.addCleanup(default.stop)

    def rows(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def route_task(self, create_path, tid, urls, cost):
        self.api.on("POST", rg.BASE + create_path, {"id": tid, "estimatedCost": {"credits": cost}})
        self.api.on("GET", rg.BASE + f"/tasks/{tid}",
                    {"id": tid, "status": "SUCCEEDED", "output": urls, "cost": {"credits": cost}})

    def test_nano_banana_refuses_without_yes_and_shows_the_tier_price(self):
        code, _, err = self.run_cli("image", "--model", "nano_banana_2.1", "--resolution", "2K", "--prompt", "x",
                                    "--out", str(self.tmp / "o.png"))
        self.assertEqual(code, rg.EXIT_REFUSED)
        self.assertIn("~6 credits", err)
        self.assertEqual(self.api.calls, [])

    def test_nano_banana_sends_the_tier_ratio_references_and_no_seed(self):
        self.route_task("/text_to_image", TID, [CDN + "/s.png"], 6)
        self.api.on("GET", CDN + "/s.png", b"PNG")
        code, _, _ = self.run_cli("image", "--model", "nano_banana_2.1", "--ratio", "1584:672", "--resolution", "2K",
                                  "--reference", "hero=https://e.test/a.png", "--prompt", "@hero in a field",
                                  "--out", str(self.tmp / "s.png"), "--yes", "--log", str(self.log))
        self.assertEqual(code, 0)
        sent = json.loads(self.api.to("POST", rg.BASE + "/text_to_image")[0][3])
        self.assertEqual((sent["model"], sent["ratio"]), ("nano_banana_2.1", "3168:1344"))
        self.assertEqual(sent["referenceImages"], [{"uri": "https://e.test/a.png", "tag": "hero"}])
        self.assertNotIn("seed", sent)
        pre = self.rows()[0]
        self.assertEqual((pre["our_estimate"], pre["meta"]["resolution"]), (6, "2K"))

    def test_nano_banana_with_no_ratio_or_resolution_is_the_1k_panorama(self):
        self.route_task("/text_to_image", TID, [CDN + "/s.png"], 4)
        self.api.on("GET", CDN + "/s.png", b"PNG")
        code, _, _ = self.run_cli("image", "--model", "nano_banana_2.1", "--prompt", "x", "--out", str(self.tmp / "s.png"),
                                  "--yes", "--log", str(self.log))
        self.assertEqual(code, 0)
        sent = json.loads(self.api.to("POST", rg.BASE + "/text_to_image")[0][3])
        self.assertEqual(sent["ratio"], "1584:672")
        self.assertEqual(self.rows()[0]["our_estimate"], 4)

    def test_other_models_keep_their_default_ratio(self):
        self.route_task("/text_to_image", TID, [CDN + "/s.png"], 5)
        self.api.on("GET", CDN + "/s.png", b"PNG")
        self.run_cli("image", "--prompt", "x", "--out", str(self.tmp / "s.png"), "--yes", "--log", str(self.log))
        self.assertEqual(json.loads(self.api.to("POST", rg.BASE + "/text_to_image")[0][3])["ratio"], "1344:768")

    def test_fifteen_references_to_nano_banana_are_refused_before_anything_is_sent(self):
        argv = ["image", "--model", "nano_banana_2.1", "--prompt", "x", "--out", str(self.tmp / "s.png"), "--yes",
                "--log", str(self.log)]
        for i in range(15):
            argv += ["--reference", f"ref{i:02d}=https://e.test/{i}.png"]
        code, _, err = self.run_cli(*argv)
        self.assertEqual(code, 1)
        self.assertIn("14", err)
        self.assertEqual(self.api.calls, [])

    def test_four_references_to_gen4_image_are_refused(self):
        argv = ["image", "--model", "gen4_image", "--ratio", "1920:1080", "--prompt", "x", "--out", str(self.tmp / "s.png"), "--yes"]
        for i in range(4):
            argv += ["--reference", f"ref{i:02d}=https://e.test/{i}.png"]
        code, _, err = self.run_cli(*argv)
        self.assertEqual(code, 1)
        self.assertIn("gen4_image takes at most 3 reference images; 4 given", err)
        self.assertEqual(self.api.calls, [])

    # --- upscale ---
    def test_upscale_refuses_without_yes_and_shows_the_price(self):
        src = self.tmp / "in.png"
        src.write_bytes(png_bytes(1000, 1000))
        code, _, err = self.run_cli("upscale", str(src), "--out", str(self.tmp / "o.png"))
        self.assertEqual(code, rg.EXIT_REFUSED)
        self.assertIn("~25 credits", err)
        self.assertEqual(self.api.calls, [])
        self.assertFalse(self.log.exists())

    def test_upscale_sends_the_documented_body_and_logs_it(self):
        src = self.tmp / "in.png"
        src.write_bytes(png_bytes(1000, 1000))
        self.route_task("/image_upscale", TID, [CDN + "/up.png"], 25)
        self.api.on("GET", CDN + "/up.png", b"BIG")
        out = self.tmp / "up.png"
        code, _, _ = self.run_cli("upscale", str(src), "--scale", "4", "--flavor", "sublime", "--sharpen", "20",
                                  "--smart-grain", "10", "--ultra-detail", "30", "--out", str(out), "--yes", "--log", str(self.log))
        self.assertEqual(code, 0)
        self.assertEqual(out.read_bytes(), b"BIG")
        sent = json.loads(self.api.to("POST", rg.BASE + "/image_upscale")[0][3])
        self.assertEqual(sent["model"], "magnific_precision_upscaler_v2")
        self.assertTrue(sent["imageUri"].startswith("data:image/png;base64,"))
        self.assertEqual((sent["scaleFactor"], sent["flavor"], sent["sharpen"], sent["smartGrain"], sent["ultraDetail"]),
                         (4, "sublime", 20, 10, 30))
        pre = self.rows()[0]
        self.assertEqual((pre["model"], pre["endpoint"], pre["our_estimate"]), ("magnific_precision_upscaler_v2", "/image_upscale", 150))   # 1000x1000 x4 = 16 MP: over the area reading

    def test_upscale_of_a_url_needs_size_for_an_exact_estimate(self):
        _, _, err = self.run_cli("upscale", "https://e.test/a.png", "--out", str(self.tmp / "o.png"))
        self.assertIn("~150 credits", err)
        _, _, err = self.run_cli("upscale", "https://e.test/a.png", "--size", "1000x1000", "--out", str(self.tmp / "o.png"))
        self.assertIn("~25 credits", err)
        self.assertEqual(self.api.calls, [])

    def test_upscale_refuses_a_too_small_input(self):
        src = self.tmp / "in.png"
        src.write_bytes(png_bytes(200, 200))
        code, _, err = self.run_cli("upscale", str(src), "--out", str(self.tmp / "o.png"), "--yes")
        self.assertEqual(code, 1)
        self.assertIn("300", err)
        self.assertEqual(self.api.calls, [])

    def test_a_bare_reference_to_nano_banana_is_sent_with_a_lowercase_tag(self):
        self.route_task("/text_to_image", TID, [CDN + "/s.png"], 4)
        self.api.on("GET", CDN + "/s.png", b"PNG")
        code, _, _ = self.run_cli("image", "--model", "nano_banana_2.1", "--reference", "https://e.test/Octopus_MASTER.jpeg",
                                  "--prompt", "@octopus_master", "--out", str(self.tmp / "s.png"), "--yes", "--log", str(self.log))
        self.assertEqual(code, 0)
        sent = json.loads(self.api.to("POST", rg.BASE + "/text_to_image")[0][3])
        self.assertEqual(sent["referenceImages"][0]["tag"], "octopus_master")

    def test_a_large_local_file_is_not_uploaded_before_yes(self):
        src = self.tmp / "big.png"
        src.write_bytes(png_bytes(1000, 1000) + bytes(1000))
        with mock.patch.object(rg, "MAX_REF_BYTES", 600):
            code, _, err = self.run_cli("upscale", str(src), "--out", str(self.tmp / "o.png"))
        self.assertEqual(code, rg.EXIT_REFUSED)
        self.assertIn("~25 credits", err)
        self.assertEqual(self.api.calls, [])           # no /uploads, no /image_upscale

    def test_a_large_local_file_is_uploaded_after_yes_and_sent_as_a_runway_uri(self):
        src = self.tmp / "big.png"
        src.write_bytes(png_bytes(1000, 1000) + bytes(1000))
        self.api.on("POST", rg.BASE + "/uploads", {"uploadUrl": UPLOAD_URL, "fields": {"key": "k"},
                                                   "runwayUri": "runway://upload/abc"})
        self.api.on("POST", UPLOAD_URL, b"")
        self.route_task("/image_upscale", TID, [CDN + "/up.png"], 25)
        self.api.on("GET", CDN + "/up.png", b"BIG")
        with mock.patch.object(rg, "MAX_REF_BYTES", 600):
            code, _, _ = self.run_cli("upscale", str(src), "--out", str(self.tmp / "up.png"), "--yes", "--log", str(self.log))
        self.assertEqual(code, 0)
        order = [c[1] for c in self.api.calls]
        self.assertLess(order.index(rg.BASE + "/uploads"), order.index(rg.BASE + "/image_upscale"))
        sent = json.loads(self.api.to("POST", rg.BASE + "/image_upscale")[0][3])
        self.assertEqual(sent["imageUri"], "runway://upload/abc")
        self.assertEqual(self.rows()[0]["input_sha256"], rg.file_sha256(src))

    def test_upscale_effects_outside_0_100_are_refused_by_the_parser(self):
        src = self.tmp / "in.png"
        src.write_bytes(png_bytes(1000, 1000))
        for flag in ("--sharpen", "--smart-grain", "--ultra-detail"):
            for bad in ("101", "-1"):
                with self.subTest(flag, bad=bad):
                    code, _, err = self.run_cli("upscale", str(src), "--out", str(self.tmp / "o.png"), flag, bad, "--yes")
                    self.assertEqual(code, 2)
                    self.assertIn("0-100", err)
        self.assertEqual(self.api.calls, [])

    def test_upscale_refuses_another_model_before_sending(self):
        src = self.tmp / "in.png"
        src.write_bytes(png_bytes(1000, 1000))
        code, _, err = self.run_cli("upscale", str(src), "--model", "some_other_upscaler", "--out", str(self.tmp / "o.png"), "--yes")
        self.assertEqual(code, 1)
        self.assertIn(rg.UPSCALE_MODEL, err)
        self.assertEqual(self.api.calls, [])

    def test_upscale_max_credits_applies_to_the_estimate(self):
        src = self.tmp / "in.png"
        src.write_bytes(png_bytes(1000, 1000))
        code, _, err = self.run_cli("upscale", str(src), "--scale", "4", "--max-credits", "20", "--out", str(self.tmp / "o.png"), "--yes")
        self.assertEqual(code, rg.EXIT_REFUSED)
        self.assertIn("max-credits", err)
        self.assertEqual(self.api.calls, [])

    def test_upscale_help_parses(self):
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(io.StringIO()) as out:
            rg.main(["upscale", "--help"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("--scale", out.getvalue())
