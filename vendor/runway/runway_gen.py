#!/usr/bin/env python3
"""Minimal Runway Developer API client (studio copy of TFF scripts/runway_gen.py, 2026-10-27).

Stdlib only (urllib) — no pip installs. Reads RUNWAY_API_KEY from the
environment; ALWAYS run it wrapped so the key is injected at runtime and
never written to disk:

    tools/runway/runway.sh <cmd> ...

Commands (every one that spends credits needs --yes; without it the command prints its
estimate and exits 3. Paid calls append to --log, default tools/runway/spend-log.jsonl):
    eval   --yes                 one cheap still + one 5s clip. RUN THIS FIRST.   (spends)
    image  --prompt/... --out FILE --yes [--resolution 1K|2K|4K]                  (spends)
    upscale IMAGE --out FILE --yes [--scale 2|4|8|16] [--size WxH]                (spends)
    video  --image URL --prompt ... --out FILE --yes                              (spends)
    v2v    REQUEST.json --out FILE --yes [--max-credits N] [--timeout S]          (spends)
    estimate REQUEST.json        price a p47-render/1 request; sends nothing.     (free)
    upload FILE                  ephemeral upload; prints the runway:// URI.      (free)
    fetch  --task ID --out FILE  re-download a task's outputs (they expire 24-48 h). (free)
Exit codes: 0 ok, 1 failed, 3 refused (no --yes / over --max-credits), 4 task still running.

✅ VALIDATED LIVE 2026-07-25: image generation works end-to-end (gemini_2.5_flash
   produced an on-style 2D-anime still, headless via the op-resolved key).
   Video (image_to_video) not yet run live — verify on first use.
   API notes captured in the constants below and in art/runway-guide.md.

Docs: https://docs.dev.runwayml.com  (auth: Bearer + X-Runway-Version header)
"""
from __future__ import annotations
import argparse, base64, hashlib, http.client, io, json, math, mimetypes, os, random, re, secrets, shutil, subprocess, sys, time, urllib.request, urllib.error, uuid, pathlib
from datetime import date, datetime, timezone
from decimal import Decimal as D

BASE = "https://api.dev.runwayml.com/v1"
API_VERSION = "2024-11-06"          # X-Runway-Version — confirm current value on setup
POLL_SECONDS = 5
POLL_TIMEOUT = 300                  # image tasks: 5 min
VIDEO_TIMEOUT = 1800                # video and v2v tasks: 30 min (--timeout overrides); a timeout never cancels
POLL_SLOW_SECONDS = 10              # poll interval after the first minute (docs: no more often than every 5 s)
MAX_RETRIES = 4                     # for 429 (any method) and 502/503/504 + network errors (GET only)
RETRY_STATUS = (429, 502, 503, 504)
EXIT_FAILED, EXIT_REFUSED, EXIT_PENDING = 1, 3, 4   # task failed / spend refused / task still running

# Verified live 2026-07-25:
#  - /text_to_image requires referenceImages>=1 for gen4_image / gen4_image_turbo;
#    OPTIONAL for gemini_2.5_flash / seedream / flux (use these for text-only bootstrap).
#  - `ratio` is model-specific. Image models (gemini_2.5_flash) accept e.g.
#    1344:768, 768:1344, 1024:1024, 1184:864, 1536:672 (NOT 1280:720).
#  - Confirmed working model id: gemini_2.5_flash (produced on-style 2D anime).
IMG_RATIOS = ("1344:768", "768:1344", "1024:1024", "1184:864", "864:1184", "1536:672")
# Credits per unit for the running-cost print. $0.01/credit. Confirm exact rates on the dashboard.
# Image rows below: docs.dev.runwayml.com/guides/pricing.md, read 3 Nov 2026 (live call pending).
COST = {
    "gemini_2.5_flash": ("image", 5),   # text-to-image bootstrap/draft; 5 any resolution (was 4 before 3 Nov 2026), <= 3 refs
    "gen4_image_turbo": ("image", 2),   # 1-3 references REQUIRED; 2 any resolution
    "gen4_image": ("image", 8),         # <= 3 references; 720p = 5, 1080p = 8: we price the 8 (ratio sets the tier; not read per ratio)
    "seedream5": ("image", 9),          # not in the 3 Nov 2026 docs (they list seedream5_pro/_lite/_flash); stale, unverified
    # nano_banana_pro was removed 3 Nov 2026: neither api.md, openapi.json nor pricing.md lists it any more.
    # nano_banana_2.1: 4 / 6 / 12 credits at 1K / 2K / 4K. There is no resolution parameter: the tier is the `ratio`
    # you send (pixel sizes, see NANO_BANANA_RATIOS), so --resolution on `image` picks the ratio.
    "nano_banana_2.1": ("image_tiered", {"1K": 4, "2K": 6, "4K": 12}),
    # image_upscale (POST /v1/image_upscale): the only model is magnific_precision_upscaler_v2; 25 credits per image,
    # 150 when the output "exceeds 4096px". The docs do not say edge or area, so estimate_upscale() prices 150 if EITHER
    # the longest output edge is over 4096 OR the output area is over 4096 x 2160. UNCONFIRMED until a live call
    # compares the API's estimatedCost with ours.
    "magnific_precision_upscaler_v2": ("upscale", {"base": 25, "large": 150, "large_over_px": 4096,
                                                   "large_over_area": 4096 * 2160}),
    "gen4_turbo": ("video_per_s", 5),   # draft video
    "gen4.5": ("video_per_s", 12),      # hero/world finals
    "seedance2": ("video_per_s", 60),   # face-match only; 36-150 by res
    # Video-to-video (guides/pricing.md, read 30 Oct 2026). per_s[tier] = (credits per OUTPUT second,
    # credits per INPUT second); "ref" = credits per reference image; "min" = per-generation minimum.
    "aleph2": ("v2v", {"per_s": {"any": (D(28), D(0))}, "min": 56, "ref": 0}),
    "kling_4": ("v2v", {                       # LIST prices; the 20 % promo ends 30 Nov 2026 UTC
        "per_s": {"720p": (D("9.4"), D("9.4")), "1080p": (D("14.1"), D("14.1"))},
        "min": 0, "ref": 0, "in_basis": "max_in_out",   # input is billed at max(input s, output s)
        "promo": {"until": date(2026, 11, 30), "factor": D("0.8")}}),
    "seedance2_5": ("v2v", {"per_s": {"480p": (D(20), D(10)), "720p": (D(30), D(15)), "1080p": (D(68), D(34))},
                            "min": 80, "ref": 0}),
    "gemini_omni_flash_1.1": ("v2v", {"per_s": {"360p": (D("3.4"), D(1)), "720p": (D(10), D(1)),
                                                "1080p": (D(15), D(1)), "4K": (D(30), D(1))},
                                      "min": 0, "ref": 1}),
}


def _key() -> str:
    k = os.environ.get("RUNWAY_API_KEY", "").strip()
    if not k:
        sys.exit("RUNWAY_API_KEY not set. Run via: tools/runway/runway.sh ...")
    return k


class ApiError(Exception):
    """An HTTP error from Runway (status 0 = network failure before any response)."""

    def __init__(self, status: int, method: str, path: str, detail: str):
        self.status, self.method, self.path, self.detail = status, method, path, detail
        super().__init__(f"API {status} on {method} {path}: {detail}")


class UnparsedResponse(ApiError):
    """Runway answered 200 but the body was not usable JSON. On a POST the task may exist."""


class RequestError(Exception):
    """A problem with our own input (bad request file, missing file, limit exceeded). Nothing was sent."""


_urlopen = urllib.request.urlopen   # the ONLY network entry point; tests replace it


def _backoff(attempt: int) -> float:
    return min(60, 2 ** attempt * 2) * (1 + random.random() * 0.5)    # exponential + up to 50 % jitter


def _req(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {_key()}")
        req.add_header("X-Runway-Version", API_VERSION)
        req.add_header("Content-Type", "application/json")
        try:
            with _urlopen(req, timeout=60) as r:
                raw = r.read()
            try:
                text = raw.decode()
                result = json.loads(text) if text.strip() else {}
            except ValueError:
                raise UnparsedResponse(200, method, path, "invalid JSON in response") from None
            if not isinstance(result, dict):
                raise UnparsedResponse(200, method, path, "invalid JSON in response (not an object)")
            return result
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            # 429 = refused, safe to resend. 5xx on a POST may have created a task: never resend.
            retry = e.code == 429 or (method == "GET" and e.code in RETRY_STATUS)
            if retry and attempt < MAX_RETRIES:
                wait = _backoff(attempt)
                print(f"   (HTTP {e.code} on {method} {path}; retry {attempt + 1}/{MAX_RETRIES} in {wait:.0f}s)", file=sys.stderr)
                time.sleep(wait)
                continue
            raise ApiError(e.code, method, path, detail) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as e:
            if method == "GET" and attempt < MAX_RETRIES:
                time.sleep(_backoff(attempt))
                continue
            raise ApiError(0, method, path, f"network error: {type(e).__name__}: {e}") from None


def _download(url: str, out: str) -> None:
    """Fetch an output URL to `out` (written as out.part, then renamed). No credentials are sent to the CDN."""
    dest = pathlib.Path(out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    try:
        with _urlopen(urllib.request.Request(url), timeout=300) as r, open(part, "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(part, dest)
    finally:
        part.unlink(missing_ok=True)
    print(f"✓ saved {out}", file=sys.stderr)


def estimate_simple(model: str, seconds: int | None = None, resolution: str | None = None):
    """Credits for an image or image-to-video call, or None if the model is not in COST (or needs sizes: upscale).

    `resolution` ("1K" | "2K" | "4K") only matters for tiered image models; left out, the dearest tier is priced
    (a spend guard should over-estimate). An unknown tier raises ValueError.
    """
    kind, cr = COST.get(model, (None, None))
    if kind == "image":
        return cr
    if kind == "image_tiered":
        if resolution is None:
            return max(cr.values())
        if resolution not in cr:
            raise ValueError(f"{model}: unknown resolution {resolution!r}; use one of {sorted(cr)}")
        return cr[resolution]
    if kind == "video_per_s":
        return cr * (seconds or 5)
    return None


# --- nano_banana_2.1: ratio list and reference limits (api.md / openapi.json, read 3 Nov 2026) -----------------
# `ratio` is the output size in pixels; the model has no separate resolution field. The enum holds 42 sizes: three
# tiers of fourteen aspects, in the same order, about 1 MP (1K), 4 MP (2K) and 16 MP (4K). The tier-to-price mapping is
# inferred from those pixel counts (the docs price "per 1K / 2K / 4K image" and describe `ratio` only as "the
# resolution of the output image"): the first live call should confirm that estimatedCost matches.
NANO_BANANA = "nano_banana_2.1"
NANO_BANANA_RATIOS = {
    "1K": ("1024:1024", "848:1264", "1264:848", "896:1200", "1200:896", "928:1152", "1152:928", "768:1376", "1376:768",
           "1584:672", "512:2064", "2064:512", "352:2928", "2928:352"),
    "2K": ("2048:2048", "1696:2528", "2528:1696", "1792:2400", "2400:1792", "1856:2304", "2304:1856", "1536:2752",
           "2752:1536", "3168:1344", "1024:4128", "4128:1024", "704:5856", "5856:704"),
    "4K": ("4096:4096", "3392:5056", "5056:3392", "3584:4800", "4800:3584", "3712:4608", "4608:3712", "3072:5504",
           "5504:3072", "6336:2688", "2048:8256", "8256:2048", "1408:11712", "11712:1408"),
}
NANO_BANANA_DEFAULT_ASPECT = 9      # index of 1584:672 / 3168:1344 / 6336:2688, the widest common panorama (~2.36:1)
# Reference tags: the openapi gives ^[a-z][a-z0-9_]+$, 3-16 characters, for nano_banana_2.1, gen4_image, gen4_image_turbo
# and gemini_2.5_flash alike (read 3 Nov 2026). Only _parse_refs' older rule ([A-Za-z0-9]) is looser than that.
NANO_BANANA_TAG = re.compile(r"[a-z][a-z0-9_]{2,15}")
# Maximum referenceImages per text_to_image model (api.md, 3 Nov 2026). gen4_image_turbo also needs at least one.
MAX_REFS = {NANO_BANANA: 14, "gen4_image": 3, "gen4_image_turbo": 3, "gemini_2.5_flash": 3}


def resolve_nano_ratio(ratio: str | None, resolution: str | None) -> tuple[str, str]:
    """(ratio to send, tier) for nano_banana_2.1.

    A ratio alone fixes its own tier. A resolution moves the ratio to the same aspect in that tier
    (1584:672 + 2K -> 3168:1344). Neither: the widest panorama at 1K, or at the asked tier. A ratio outside the
    docs' list raises RequestError."""
    if resolution is not None and resolution not in NANO_BANANA_RATIOS:
        raise RequestError(f"{NANO_BANANA}: unknown resolution {resolution!r}; use one of {sorted(NANO_BANANA_RATIOS)}")
    if ratio is None:
        tier = resolution or "1K"
        return NANO_BANANA_RATIOS[tier][NANO_BANANA_DEFAULT_ASPECT], tier
    for tier, sizes in NANO_BANANA_RATIOS.items():
        if ratio in sizes:
            if resolution is None or resolution == tier:
                return ratio, tier
            return NANO_BANANA_RATIOS[resolution][sizes.index(ratio)], resolution
    raise RequestError(f"{NANO_BANANA}: ratio {ratio!r} is not one of the model's sizes: "
                       + ", ".join(", ".join(v) for v in NANO_BANANA_RATIOS.values()))


def check_image_request(model: str, ratio: str, refs: list[dict], seed) -> None:
    """Refuse, before anything is sent, a text_to_image request the docs say will be rejected."""
    cap = MAX_REFS.get(model)
    if cap is not None and len(refs) > cap:
        raise RequestError(f"{model} takes at most {cap} reference images; {len(refs)} given")
    if model == NANO_BANANA:
        if all(ratio not in sizes for sizes in NANO_BANANA_RATIOS.values()):
            raise RequestError(f"{model}: ratio {ratio!r} is not one of the model's sizes (see NANO_BANANA_RATIOS)")
        if seed is not None:
            raise RequestError(f"{model} has no seed parameter; drop --seed")
        for r in refs:
            if not NANO_BANANA_TAG.fullmatch(r.get("tag", "")):
                raise RequestError(f"{model}: reference tag {r.get('tag')!r} must be 3-16 characters, lowercase letters, "
                                   f"digits or underscores, starting with a letter")


# --- image_upscale (POST /v1/image_upscale, api.md and pricing.md read 3 Nov 2026) ------------------------------
UPSCALE_MODEL = "magnific_precision_upscaler_v2"
UPSCALE_MIN_EDGE, UPSCALE_MAX_EDGE = 300, 8000          # each INPUT dimension, px
UPSCALE_MAX_OUTPUT_PIXELS = 25_300_000                  # width x height of the OUTPUT


def estimate_upscale(width: int | None, height: int | None, scale: int = 2, model: str = UPSCALE_MODEL) -> int:
    """Credits for one image_upscale call. Input size unknown (a URL, no --size): the dearer price is assumed.

    "Output exceeds 4096px" is ambiguous, so 150 is charged if the longest output edge is over 4096 or the output area
    is over 4096 x 2160 (unconfirmed until a live call checks estimatedCost). A model other than the Magnific upscaler,
    or a size the docs refuse (an input edge outside 300-8000 px, an output over 25.3 MP), raises RequestError."""
    if model != UPSCALE_MODEL:
        raise RequestError(f"upscale: only {UPSCALE_MODEL} is priced here, not {model!r}")
    spec = COST[UPSCALE_MODEL][1]
    if width is None or height is None:
        return spec["large"]
    if not (UPSCALE_MIN_EDGE <= width <= UPSCALE_MAX_EDGE and UPSCALE_MIN_EDGE <= height <= UPSCALE_MAX_EDGE):
        raise RequestError(f"upscale input is {width}x{height}; each side must be {UPSCALE_MIN_EDGE}-{UPSCALE_MAX_EDGE} px")
    if width * scale * height * scale > UPSCALE_MAX_OUTPUT_PIXELS:
        raise RequestError(f"upscale output would be {width * scale}x{height * scale}; the limit is "
                           f"{UPSCALE_MAX_OUTPUT_PIXELS:,} pixels. Use a smaller --scale")
    out_w, out_h = width * scale, height * scale
    return spec["large"] if max(out_w, out_h) > spec["large_over_px"] or out_w * out_h > spec["large_over_area"] else spec["base"]


def image_size(path) -> tuple[int, int] | None:
    """(width, height) of a local PNG or JPEG from its header (stdlib only); None if it is neither."""
    with open(path, "rb") as f:
        head = f.read(26)
        if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
            return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
        if head[:2] == b"\xff\xd8":
            f.seek(2)
            while True:
                marker = f.read(4)
                if len(marker) < 4 or marker[0] != 0xFF:
                    return None
                if marker[1] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    dims = f.read(5)
                    return int.from_bytes(dims[3:5], "big"), int.from_bytes(dims[1:3], "big")
                f.seek(int.from_bytes(marker[2:4], "big") - 2, 1)
    return None


def _whole_seconds(x: float) -> int:
    """Billable whole seconds: round up, but forgive up to 0.05 s of container slack (10.008 -> 10)."""
    return max(0, math.ceil(x - 0.05))


def _today() -> date:
    return datetime.now(timezone.utc).date()


def estimate_v2v(model: str, *, in_seconds, out_seconds, tier: str, n_refs: int = 0, today: date | None = None) -> int:
    """Our credit estimate for one video-to-video call, rounded UP. The API's own cap is estimatedCost."""
    kind, spec = COST.get(model, (None, None))
    if kind != "v2v":
        raise ValueError(f"{model} is not a video-to-video model in COST")
    rates = spec["per_s"].get(tier) or spec["per_s"].get("any")
    if rates is None:
        raise ValueError(f"no {tier} rate for {model}; known tiers: {sorted(spec['per_s'])}")
    out_rate, in_rate = rates
    billed_in = max(in_seconds, out_seconds) if spec.get("in_basis") == "max_in_out" else in_seconds
    total = D(str(out_seconds)) * out_rate + D(str(billed_in)) * in_rate + n_refs * spec["ref"]
    credits = math.ceil(total)
    promo = spec.get("promo")
    if promo and (today or _today()) <= promo["until"]:
        credits = math.ceil(credits * promo["factor"])     # list rounded up, discounted, rounded up again
    return max(spec["min"], credits)


def _cost_note(model: str, seconds: int | None = None) -> str:
    est = estimate_simple(model, seconds)
    if est is None:
        return "(cost: unknown model — check dashboard)"
    return f"(cost: ~{est} cr ≈ ${est*0.01:.2f})"


# --- spend log and hashes ---------------------------------------------------
DEFAULT_LOG = pathlib.Path(__file__).resolve().with_name("spend-log.jsonl")
EVAL_OUT_ROOT = pathlib.Path(__file__).resolve().with_name("out")     # eval-<timestamp>/ folders go here


def sha256_json(obj) -> str:
    """SHA-256 of the canonical JSON form (sorted keys, no spaces): same request, same hash."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def log_row(log, row: dict) -> None:
    """Append one JSON line to the spend log, flushed and fsynced so a crash cannot lose it."""
    path = pathlib.Path(log)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    line = json.dumps({"time": stamp, **row}, ensure_ascii=False, sort_keys=False)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def probe_video(path) -> dict:
    """{'seconds', 'width', 'height', 'fps'} of a local video, from ffprobe."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(path)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        raise RequestError("ffprobe is not on PATH (brew install ffmpeg)") from None
    if r.returncode != 0:
        raise RequestError(f"ffprobe failed on {path}: {r.stderr.strip()[:200]}")
    data = json.loads(r.stdout or "{}")
    if not data.get("streams"):
        raise RequestError(f"{path} has no video stream")
    st = data["streams"][0]
    num, _, den = st.get("r_frame_rate", "0/1").partition("/")
    fps = float(num) / float(den) if float(den or 0) else None
    return {"seconds": float(data["format"]["duration"]), "width": int(st["width"]),
            "height": int(st["height"]), "fps": fps}


# --- ephemeral uploads (docs: assets/uploads.md) ------------------------------
UPLOAD_MIN, UPLOAD_MAX = 512, 200 * 1024 * 1024      # bytes
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".3gp", ".ogv"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}       # GIF is not supported
UPLOAD_EXT = VIDEO_EXT | IMAGE_EXT | {".mp3", ".wav", ".flac", ".m4a", ".aac"}


def _file_size(p: pathlib.Path) -> int:
    return p.stat().st_size


def _safe_name(name: str) -> str:
    stem, dot, ext = name.rpartition(".")
    return (re.sub(r"[^A-Za-z0-9._-]", "_", stem) + dot + re.sub(r"[^A-Za-z0-9]", "", ext))[-255:]


def _multipart(fields: dict, filename: str, content: bytes, mime: str) -> tuple[bytes, str]:
    boundary = "----runwaygen" + secrets.token_hex(12)
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
             for k, v in fields.items()]
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                 f'Content-Type: {mime}\r\n\r\n'.encode())
    parts += [content, f"\r\n--{boundary}--\r\n".encode()]
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def upload_file(path) -> str:
    """Upload a local file as an ephemeral asset (24 h) and return its runway:// URI. Never retries."""
    p = pathlib.Path(path)
    if not p.is_file():
        raise RequestError(f"upload: no such file: {p}")
    if p.suffix.lower() not in UPLOAD_EXT:
        raise RequestError(f"upload: {p.name}: unsupported type {p.suffix or '(none)'}; use {sorted(UPLOAD_EXT)}")
    size = _file_size(p)
    if not UPLOAD_MIN <= size <= UPLOAD_MAX:
        raise RequestError(f"upload: {p.name} is {size} bytes; Runway accepts {UPLOAD_MIN} B to 200 MB")
    name = _safe_name(p.name)
    slot = _req("POST", "/uploads", {"filename": name, "type": "ephemeral"})
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    body, ctype = _multipart(slot["fields"], name, p.read_bytes(), mime)
    # The upload URL is a signed third-party URL: send NO Authorization header to it.
    req = urllib.request.Request(slot["uploadUrl"], data=body, method="POST")
    req.add_header("Content-Type", ctype)
    try:
        with _urlopen(req, timeout=600) as r:
            r.read()
    except urllib.error.HTTPError as e:
        # Never echo the response body: S3 error XML can carry an access-key id. Status + <Code> only.
        m = re.search(r"<Code>([A-Za-z0-9_.-]{1,64})</Code>", e.read(4096).decode(errors="replace"))
        raise ApiError(e.code, "POST", "upload (signed URL)",
                       "upload failed; do not retry, start over with a new upload"
                       + (f" [{m.group(1)}]" if m else "")) from None
    except OSError as e:      # URLError, timeouts, resets; no retry (docs: start over)
        raise ApiError(0, "POST", "upload (signed URL)",
                       f"upload network error ({type(e).__name__}); do not retry, start over with a new upload") from None
    print(f"✓ uploaded {p.name} ({size} B) → {slot['runwayUri']} (valid 24 h)", file=sys.stderr)
    return slot["runwayUri"]


def cmd_upload(a):
    print(upload_file(a.file))


# --- resolving request inputs -------------------------------------------------
REMOTE_PREFIXES = ("https://", "runway://", "data:")
IMAGE_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def classify_target(target: str, base: pathlib.Path):
    """('remote', uri) for https/runway/data, ('local', Path) for a file that exists."""
    if target.startswith(REMOTE_PREFIXES):
        return "remote", target
    if target.startswith("http://"):
        raise RequestError(f"{target}: Runway needs https:// (plain http:// is refused)")
    p = pathlib.Path(target)
    p = p if p.is_absolute() else base / p
    if not p.is_file():
        raise RequestError(f"input file not found: {p}")
    return "local", p


def make_resolver(base: pathlib.Path, upload):
    """resolve(kind, target) -> URI, kind in {'video', 'image'}.

    Local videos are uploaded; local images are inlined if small, else uploaded. With upload=None
    (dry run: estimates) nothing is uploaded and the URI is a 'dry-run://' placeholder, but every
    file is still checked, so a missing input fails the estimate too.
    """
    def put(p: pathlib.Path) -> str:
        return upload(p) if upload else f"dry-run://upload/{p.name}"

    def resolve(kind: str, target: str) -> str:
        where, v = classify_target(target, base)
        if where == "remote":
            return v
        ext = v.suffix.lower()
        if kind == "video":
            if ext not in VIDEO_EXT:
                raise RequestError(f"{v.name}: not a video type Runway accepts ({sorted(VIDEO_EXT)})")
            return put(v)
        if ext not in IMAGE_MIME:
            raise RequestError(f"{v.name}: Runway accepts .jpg, .png and .webp images, not {ext or 'no extension'}")
        if _file_size(v) <= MAX_REF_BYTES:
            return f"data:{IMAGE_MIME[ext]};base64," + base64.b64encode(v.read_bytes()).decode()
        return put(v)

    return resolve


# --- the p47-render/1 request file --------------------------------------------
REQUEST_SCHEMA = "p47-render/1"
V2V_MODELS = ("aleph2", "kling_4", "seedance2_5", "gemini_omni_flash_1.1")
TOP_KEYS = {"schema", "model", "prompt", "seed", "inputs", "options", "meta"}
INPUT_KEYS = {"video", "video_info", "keyframes", "references"}
OPTION_KEYS = {"ratio", "mode", "audio", "duration", "draft"}


def item_target(item: dict) -> str:
    return item.get("path") or item["uri"]


def load_request(path):
    """Read and validate a p47-render/1 file. Returns (request with defaults filled, sha256 of the file's JSON)."""
    p = pathlib.Path(path)

    def bad(msg):
        raise RequestError(f"{p.name}: {msg}")

    try:
        req = json.loads(p.read_text())
    except FileNotFoundError:
        raise RequestError(f"request file not found: {p}") from None
    except json.JSONDecodeError as e:
        raise RequestError(f"{p.name}: not valid JSON ({e})") from None
    if not isinstance(req, dict):
        bad("must be a JSON object")
    sha = sha256_json(req)
    if req.get("schema") != REQUEST_SCHEMA:
        bad(f'"schema" must be "{REQUEST_SCHEMA}"')
    if set(req) - TOP_KEYS:
        bad(f"unknown key(s) {sorted(set(req) - TOP_KEYS)}; allowed: {sorted(TOP_KEYS)}")
    if req.get("model") not in V2V_MODELS:
        bad(f"model must be one of {list(V2V_MODELS)}")
    if not isinstance(req.get("prompt"), str) or not req["prompt"].strip():
        bad('"prompt" must be a non-empty string')
    inputs = req.get("inputs")
    if not isinstance(inputs, dict) or set(inputs) - INPUT_KEYS:
        bad(f'"inputs" must be an object with keys from {sorted(INPUT_KEYS)}')
    if not isinstance(inputs.get("video"), str) or not inputs["video"].strip():
        bad('"inputs.video" must be a path or URI string')
    vinfo = inputs.get("video_info")
    if vinfo is not None and (not isinstance(vinfo, dict) or "seconds" not in vinfo):
        bad('"inputs.video_info" needs at least "seconds"')
    for key in ("keyframes", "references"):
        items = inputs.setdefault(key, [])
        if not isinstance(items, list):
            bad(f'"inputs.{key}" must be a list')
        for it in items:
            if not isinstance(it, dict) or ("path" in it) == ("uri" in it):
                bad(f'every "inputs.{key}" item needs exactly one of "path" or "uri"')
    options = req.setdefault("options", {})
    if not isinstance(options, dict) or set(options) - OPTION_KEYS:
        bad(f'"options" may only contain {sorted(OPTION_KEYS)}')
    req.setdefault("meta", {})
    return req, sha


def video_info(req: dict, base: pathlib.Path) -> dict:
    """{'seconds', 'width', 'height', 'fps'} for the request's input video: ffprobe if local, else inputs.video_info."""
    where, v = classify_target(req["inputs"]["video"], base)
    if where == "local":
        return probe_video(v)
    info = req["inputs"].get("video_info")
    if not info or "seconds" not in info:
        raise RequestError("inputs.video is not a local file, so inputs.video_info.seconds is required "
                           "(width, height, fps optional)")
    return {"seconds": float(info["seconds"]), "width": info.get("width"),
            "height": info.get("height"), "fps": info.get("fps")}


# --- video-to-video adapters (docs: api.md, guides/models.md, read 30 Oct 2026) -----------------
# Documented INPUT-video limits in seconds, per model and mode. kling_4's 3-30 s is the documented
# output length, which "follows the source video's length". A 400 is not billed, so a wrong limit here
# costs only a refusal: loosen it if the API proves it wrong.
INPUT_SECONDS = {
    "aleph2": {"*": (2, 30)},
    "kling_4": {"*": (3, 30)},
    "seedance2_5": {"*": (4, 30)},
    "gemini_omni_flash_1.1": {"reference": (0, 10), "edit": (0, 10), "extend": (0, 30)},
}
# Seedance 2.5 `ratio` values come in three groups of six: 480p, 720p, 1080p.
SEEDANCE_TIER = {**dict.fromkeys(("992:432", "854:480", "752:560", "640:640", "560:752", "480:854"), "480p"),
                 **dict.fromkeys(("1470:630", "1280:720", "1112:834", "960:960", "834:1112", "720:1280"), "720p"),
                 **dict.fromkeys(("2206:946", "1920:1080", "1664:1248", "1440:1440", "1248:1664", "1080:1920"), "1080p")}
GEMINI_TIER = {"640:360": "360p", "360:640": "360p", "1280:720": "720p", "720:1280": "720p",
               "1920:1080": "1080p", "1080:1920": "1080p", "3840:2160": "4K", "2160:3840": "4K"}


def _u16len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2          # the API measures prompts in UTF-16 code units


def _prompt(req: dict, limit: int) -> str:
    text = req["prompt"].strip()
    if _u16len(text) > limit:
        raise RequestError(f"{req['model']}: prompt is {_u16len(text)} characters; the limit is {limit}")
    return text


def _seed(req: dict, supported: bool, warns: list):
    seed = req.get("seed")
    if seed is None:
        return None
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**32 - 1:
        raise RequestError(f"seed must be an integer 0-4294967295, got {seed!r}")
    if not supported:
        warns.append(f"{req['model']} has no seed field: seed {seed} not sent (the log says 'first output')")
        return None
    return seed


def _check_seconds(model: str, mode: str, info: dict) -> None:
    table = INPUT_SECONDS[model]
    lo, hi = table.get(mode) or table["*"]
    if not lo - 0.05 <= info["seconds"] <= hi + 0.05:
        raise RequestError(f"{model} ({mode}): input video is {info['seconds']:.1f} s; the limit is {lo}-{hi} s")


def _ignored(req: dict, used: set, warns: list) -> None:
    for key in req["options"]:
        if key not in used:
            warns.append(f"{req['model']} ignores options.{key}")


def _refs(model: str, uris: dict, limit: int) -> list:
    if len(uris["references"]) > limit:
        raise RequestError(f"{model}: {len(uris['references'])} reference images; the limit is {limit}")
    return [{"uri": u} for u in uris["references"]]


def _no_keyframes(model: str, uris: dict) -> None:
    if uris["keyframes"]:
        raise RequestError(f"{model} has no keyframe field (only aleph2 does); pass the images as references")


def _result(body, out_seconds, tier, uris, seed, warns) -> dict:
    return {"body": body, "out_seconds": out_seconds, "tier": tier, "n_refs": len(uris["references"]),
            "seed": seed if seed is not None else "first output", "warnings": warns}


def _adapt_aleph2(req, uris, info):
    warns, o = [], req["options"]
    _check_seconds("aleph2", "*", info)
    if info.get("fps") and info["fps"] > 30.01:
        raise RequestError(f"aleph2: input is {info['fps']:.1f} fps; the limit is 30")
    if uris["references"]:
        raise RequestError("aleph2 takes keyframes but no reference images")
    body = {"model": "aleph2", "videoUri": uris["video"], "promptText": _prompt(req, 1000)}
    if uris["keyframes"]:
        if len(uris["keyframes"]) > 5:
            raise RequestError("aleph2: at most 5 keyframes")
        body["keyframes"] = [_aleph_keyframe(kf, uri) for kf, uri in uris["keyframes"]]
    seed = _seed(req, True, warns)
    if seed is not None:
        body["seed"] = seed
    _ignored(req, set(), warns)
    return _result(body, info["seconds"], "any", uris, seed, warns)


def _aleph_keyframe(kf: dict, uri: str) -> dict:
    if ("seconds" in kf) == ("at" in kf):
        raise RequestError("aleph2 keyframe: give exactly one of 'seconds' (0-30) or 'at' (0-1)")
    out = {"uri": uri}
    if "seconds" in kf:
        if not 0 <= kf["seconds"] <= 30:
            raise RequestError("aleph2 keyframe: 'seconds' must be 0-30")
        out["seconds"] = kf["seconds"]
    else:
        if not 0 <= kf["at"] <= 1:
            raise RequestError("aleph2 keyframe: 'at' must be 0-1")
        out["at"] = kf["at"]
    if "range" in kf:
        out["range"] = {"start_seconds": int(kf["range"]["start_seconds"]), "end_seconds": int(kf["range"]["end_seconds"])}
    return out


def _adapt_kling_4(req, uris, info):
    warns, o = [], req["options"]
    _check_seconds("kling_4", "*", info)
    _no_keyframes("kling_4", uris)
    ratio = o.get("ratio", "auto_720p")
    if ratio not in ("auto_720p", "auto_1080p"):
        raise RequestError("kling_4 video-to-video: options.ratio must be auto_720p or auto_1080p")
    body = {"model": "kling_4", "videoUri": uris["video"], "promptText": _prompt(req, 26000), "ratio": ratio}
    refs = _refs("kling_4", uris, 10)
    if refs:
        body["references"] = refs
    seed = _seed(req, False, warns)
    if o.get("audio") is False:
        warns.append("kling_4 always generates audio and has no switch; options.audio=false is ignored")
    _ignored(req, {"ratio", "audio"}, warns)
    return _result(body, info["seconds"], ratio[5:], uris, seed, warns)


def _seedance_edit_tier(info: dict, warns: list) -> str:
    w, h = info.get("width"), info.get("height")
    if not w or not h:
        warns.append("seedance2_5: input size unknown, so the estimate assumes 1080p (edit renders 1080p above 720p)")
        return "1080p"
    return "1080p" if min(w, h) > 720 else "720p"


def _adapt_seedance2_5(req, uris, info):
    warns, o = [], req["options"]
    mode = o.get("mode", "edit")      # the docs' default is "reference"; P47 edits, so "edit" is ours
    if mode not in ("reference", "extend", "edit"):
        raise RequestError("seedance2_5: options.mode must be reference, extend or edit")
    _check_seconds("seedance2_5", "*", info)
    _no_keyframes("seedance2_5", uris)
    body = {"model": "seedance2_5", "promptVideo": uris["video"], "promptText": _prompt(req, 15000),
            "mode": mode, "audio": bool(o.get("audio", False))}      # the API defaults audio to true; P47 sends false
    refs = _refs("seedance2_5", uris, 30)
    if refs:
        body["references"] = refs
    if mode == "edit":
        if "ratio" in o or "duration" in o:
            raise RequestError("seedance2_5 edit mode takes no ratio or duration (the client sends duration 'auto')")
        body["duration"], out_seconds, tier = "auto", info["seconds"], _seedance_edit_tier(info, warns)
    elif mode == "extend":
        dur = o.get("duration")
        if "ratio" in o or isinstance(dur, bool) or not isinstance(dur, int) or dur < 1:
            raise RequestError("seedance2_5 extend mode needs an integer options.duration and takes no ratio")
        body["duration"], out_seconds, tier = dur, dur, _seedance_edit_tier(info, warns)
    else:
        ratio, dur = o.get("ratio"), o.get("duration", 5)
        if ratio not in SEEDANCE_TIER:
            raise RequestError(f"seedance2_5 reference mode needs options.ratio, one of {sorted(SEEDANCE_TIER)}")
        if isinstance(dur, bool) or not isinstance(dur, int) or not 4 <= dur <= 30:
            raise RequestError("seedance2_5: options.duration must be an integer 4-30")
        body["ratio"], body["duration"], out_seconds, tier = ratio, dur, dur, SEEDANCE_TIER[ratio]
    if o.get("draft"):
        body["draft"], tier = True, "480p"       # a 480p preview, billed at the 480p rate
    seed = _seed(req, True, warns)
    if seed is not None:
        body["seed"] = seed
    _ignored(req, {"mode", "audio", "ratio", "duration", "draft"}, warns)
    return _result(body, out_seconds, tier, uris, seed, warns)


def _adapt_gemini(req, uris, info):
    warns, o = [], req["options"]
    mode = o.get("mode", "edit")
    if mode not in ("reference", "extend", "edit"):
        raise RequestError("gemini_omni_flash_1.1: options.mode must be reference, extend or edit")
    ratio = o.get("ratio")
    if ratio not in GEMINI_TIER:       # the docs give no default ratio, so we never guess one
        raise RequestError(f"gemini_omni_flash_1.1 needs options.ratio, one of {sorted(GEMINI_TIER)}")
    _check_seconds("gemini_omni_flash_1.1", mode, info)
    _no_keyframes("gemini_omni_flash_1.1", uris)
    body = {"model": "gemini_omni_flash_1.1", "videoUri": uris["video"],
            "promptText": _prompt(req, 4000), "mode": mode, "ratio": ratio}
    refs = _refs("gemini_omni_flash_1.1", uris, 5)
    if refs:
        body["references"] = refs
    if mode == "edit":
        out_seconds = info["seconds"]
        if "duration" in o:
            warns.append("gemini_omni_flash_1.1 edit mode ignores options.duration")
    else:
        dur = o.get("duration")
        if isinstance(dur, bool) or not isinstance(dur, int) or dur < 1:
            raise RequestError(f"gemini_omni_flash_1.1 {mode} mode needs an integer options.duration")
        body["duration"], out_seconds = dur, dur
    seed = _seed(req, False, warns)
    _ignored(req, {"mode", "ratio", "duration"}, warns)
    return _result(body, out_seconds, GEMINI_TIER[ratio], uris, seed, warns)


ADAPTERS = {"aleph2": _adapt_aleph2, "kling_4": _adapt_kling_4,
            "seedance2_5": _adapt_seedance2_5, "gemini_omni_flash_1.1": _adapt_gemini}


def build_v2v(req: dict, resolve, info: dict) -> dict:
    """Resolve the request's inputs and map it to one model's API body.

    Returns {'body', 'out_seconds', 'tier', 'n_refs', 'seed' (int or 'first output'), 'warnings'}.
    """
    inp = req["inputs"]
    uris = {"video": resolve("video", inp["video"]),
            "keyframes": [(kf, resolve("image", item_target(kf))) for kf in inp["keyframes"]],
            "references": [resolve("image", item_target(r)) for r in inp["references"]]}
    return ADAPTERS[req["model"]](req, uris, info)


def prepare_v2v(req: dict, resolve, info: dict) -> dict:
    """build_v2v plus our estimate: {'body', 'model', 'tier', 'in_seconds', 'out_seconds', 'estimate', 'seed', 'warnings', ...}."""
    ad = build_v2v(req, resolve, info)
    est = estimate_v2v(req["model"], in_seconds=_whole_seconds(info["seconds"]),
                       out_seconds=_whole_seconds(ad["out_seconds"]), tier=ad["tier"], n_refs=ad["n_refs"])
    return {**ad, "model": req["model"], "estimate": est, "in_seconds": info["seconds"]}


def request_context(path):
    """(request, request sha256, folder, input-video info) for a p47-render/1 file."""
    req, sha = load_request(path)
    base = pathlib.Path(path).resolve().parent
    return req, sha, base, video_info(req, base)


def cmd_estimate(a):
    req, sha, base, info = request_context(a.request)
    prep = prepare_v2v(req, make_resolver(base, None), info)    # dry run: nothing is uploaded or sent
    for w in prep["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    est = prep["estimate"]
    print(f"{prep['model']} {prep['tier']}: {prep['in_seconds']:.1f} s in, {prep['out_seconds']} s out, "
          f"~{est} credits (≈ ${est*0.01:.2f}). This is our estimate; the API's estimatedCost is its cap.", file=sys.stderr)
    print(json.dumps({"model": prep["model"], "tier": prep["tier"], "input_seconds": prep["in_seconds"],
                      "output_seconds": prep["out_seconds"], "estimate_credits": est,
                      "usd": f"{est*0.01:.2f}", "request_sha256": sha, "warnings": prep["warnings"]}))


# --- the paid-call runner -------------------------------------------------------
TERMINAL = ("SUCCEEDED", "FAILED", "CANCELLED")


class PollTimeout(Exception):
    def __init__(self, task_id: str, waited: int):
        self.task_id, self.waited = task_id, waited
        super().__init__(f"task {task_id} still running after {waited}s")


def wait_for_task(tid: str, timeout: int) -> dict:
    """Poll GET /tasks/{id} until SUCCEEDED, FAILED or CANCELLED. Raises PollTimeout; never cancels."""
    waited = 0
    while True:
        step = POLL_SECONDS if waited < 60 else POLL_SLOW_SECONDS      # docs: no more often than every 5 s
        time.sleep(step)
        waited += step
        task = _req("GET", f"/tasks/{tid}")
        status = (task.get("status") or "").upper()
        pct = f" {task['progress'] * 100:.0f}%" if isinstance(task.get("progress"), (int, float)) else ""
        print(f"   … {status}{pct} ({waited}s)", file=sys.stderr)
        if status in TERMINAL:
            return task
        if waited >= timeout:
            raise PollTimeout(tid, waited)


def _out_paths(out: str, n: int) -> list[str]:
    p = pathlib.Path(out)
    return [str(p)] + [str(p.with_name(f"{p.stem}-{i}{p.suffix}")) for i in range(2, n + 1)]


def _fetch_hint(tid: str) -> str:
    return f"fetch it later (outputs live 24-48 h): tools/runway/runway.sh fetch --task {tid} --out <file>"


def _download_all(urls, out):
    """Download every output URL to `out` (extra ones numbered). Returns (paths saved, error text or None)."""
    paths: list[str] = []
    try:
        for url, dest in zip(urls, _out_paths(out, len(urls))):
            _download(url, dest)
            paths.append(dest)
    except Exception as e:      # an expired or dropped URL is expected on the recovery path
        return paths, str(e)[:300]
    return paths, None


def _submit_unparsed(log, call_id, status, detail):
    log_row(log, {"event": "submit_unparsed", "call_id": call_id, "status": status, "error": detail})
    print(f"The submit answered but the response was unusable ({detail}). The task may exist and be billed: "
          f"check the Runway dashboard before sending it again.", file=sys.stderr)
    raise SystemExit(EXIT_FAILED)


def paid_call(*, log, path: str, body: dict, label: str, model: str, est, input_seconds=None,
              request_sha=None, input_sha=None, seed="first output", meta=None, out=None,
              timeout: int = POLL_TIMEOUT) -> dict:
    """Submit one paid task, wait for it, download its output at once, and log every step to `log`."""
    call_id = uuid.uuid4().hex[:12]
    print(f"→ submit {label} ({path}); our estimate: {est if est is not None else 'unknown'} credits", file=sys.stderr)
    log_row(log, {"event": "pre", "call_id": call_id, "label": label, "model": model, "endpoint": path,
                  "input_seconds": input_seconds, "request_sha256": request_sha, "input_sha256": input_sha,
                  "our_estimate": est, "seed": seed, "meta": meta or {}, "out": out})
    try:
        task = _req("POST", path, body)
    except KeyboardInterrupt:
        log_row(log, {"event": "submit_interrupted", "call_id": call_id})
        print("\ninterrupted while submitting; the task may exist: check the Runway dashboard before "
              "sending it again.", file=sys.stderr)
        raise
    except UnparsedResponse as e:
        _submit_unparsed(log, call_id, e.status, str(e)[:500])
    except ApiError as e:
        log_row(log, {"event": "submit_error", "call_id": call_id, "status": e.status, "error": str(e)[:500]})
        if e.status == 0:
            print("The request may have reached Runway: check the dashboard before sending it again.", file=sys.stderr)
        raise
    tid = task.get("id") or task.get("taskId")
    if not tid:
        _submit_unparsed(log, call_id, 200, "no task id in response")
    cap = (task.get("estimatedCost") or {}).get("credits")
    log_row(log, {"event": "created", "call_id": call_id, "task_id": tid, "estimated_cost_credits": cap})
    if cap is not None and est is not None and cap > est * 1.5:
        print(f"note: the API's estimatedCost is {cap} credits, well above our {est}. It is a cap "
              f"(e.g. duration 'auto' is billed at the maximum up front and the unused part refunded); "
              f"the final cost.credits is what counts.", file=sys.stderr)
    try:
        task = wait_for_task(tid, timeout)
    except PollTimeout as e:
        log_row(log, {"event": "timeout", "call_id": call_id, "task_id": tid, "waited_seconds": e.waited})
        print(f"task {tid} still running after {e.waited}s; NOT cancelled. {_fetch_hint(tid)}", file=sys.stderr)
        raise SystemExit(EXIT_PENDING) from None
    except KeyboardInterrupt:
        log_row(log, {"event": "interrupted", "call_id": call_id, "task_id": tid})
        print(f"\ninterrupted; task {tid} is still running and NOT cancelled. {_fetch_hint(tid)}", file=sys.stderr)
        raise
    except (ApiError, RequestError) as e:     # the task exists and is paid for: always leave a way back to it
        log_row(log, {"event": "poll_error", "call_id": call_id, "task_id": tid,
                      "status": getattr(e, "status", None), "error": str(e)[:500]})
        print(f"polling task {tid} failed ({str(e)[:200]}); the task is NOT cancelled and may still be running. "
              f"{_fetch_hint(tid)}", file=sys.stderr)
        raise SystemExit(EXIT_PENDING) from None
    status = (task.get("status") or "").upper()
    row = {"event": "final", "call_id": call_id, "task_id": tid, "status": status,
           "cost_credits": (task.get("cost") or {}).get("credits"),
           "failure": task.get("failure"), "failure_code": task.get("failureCode"),
           "output_path": None, "output_paths": []}
    if status != "SUCCEEDED":
        log_row(log, row)
        print(f"task {tid} {status}: {task.get('failure')} [{task.get('failureCode')}]. Moderation failures are "
              f"billed; credits are not refunded for SAFETY.INPUT.* failures.", file=sys.stderr)
        raise SystemExit(EXIT_FAILED)
    urls = task.get("output") or []
    paths, failure = _download_all(urls, out) if out and urls else ([], None)
    row.update(output_path=paths[0] if paths else None, output_paths=paths)
    if failure:      # the task is paid for: keep the row and the id, then stop loudly
        row["download_error"] = failure
        log_row(log, row)
        print(f"task {tid} succeeded but the download failed ({failure}); {_fetch_hint(tid)}", file=sys.stderr)
        raise SystemExit(EXIT_FAILED)
    log_row(log, row)
    return {"task_id": tid, "task": task, "urls": urls, "paths": paths,
            "cost_credits": row["cost_credits"], "call_id": call_id}


def _prompt_from_file(path: str, shot: str) -> str:
    """Pull the block-quoted prompt following a `**<shot> —` heading line in a pack file.

    The heading is matched to END OF LINE, so trailing text after the bold close
    (e.g. `**X1 — The tank** *(canon's best scene)*`) can't make the match run on
    into the next shot's block — which it silently did before 2026-07-29.
    """
    txt = pathlib.Path(path).read_text()
    m = re.search(rf"^\*\*{re.escape(shot)}\b[^\n]*\n+>[ \t]*(.+?)(?=\n[ \t]*\n|\n\*\*|\Z)",
                  txt, re.S | re.M)
    if not m:
        sys.exit(f"shot {shot} not found in {path}")
    return " ".join(line.lstrip("> \t").strip() for line in m.group(1).splitlines()).strip()


# --- reference images -------------------------------------------------------
# Runway takes referenceImages as [{"uri": <https or data URI>, "tag": <name>}].
# Tags are alphanumeric and are addressed inside promptText as @tag. Local files
# are inlined as data URIs so the 2000 sketches in art/refs/ can drive generation
# directly — text alone will never reproduce a bespoke silhouette.
MAX_REF_BYTES = 3_300_000     # RAW bytes. The API caps the ENCODED data URI at 5 MB and base64 adds a third (docs: ~3.3 MB)
REF_LONG_EDGE = 1024          # downscale target when a local ref is oversized


def _data_uri(path: pathlib.Path) -> str:
    raw = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    if len(raw) > MAX_REF_BYTES:
        try:
            from PIL import Image      # optional; only needed for oversized refs
            import io
            im = Image.open(io.BytesIO(raw))
            s = REF_LONG_EDGE / max(im.size)
            if s < 1:
                im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=88)
            raw, mime = buf.getvalue(), "image/jpeg"
            print(f"   (downscaled {path.name} to {im.size} for upload)", file=sys.stderr)
        except ImportError:
            sys.exit(f"{path} is {len(raw)//1000}kB — too big to inline and Pillow is unavailable to resize it.")
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


def _nano_tag(stem: str) -> str:
    """A tag nano_banana_2.1 accepts (^[a-z][a-z0-9_]{2,15}$) from a file stem: Octopus_MASTER -> octopus_master."""
    tag = re.sub(r"[^a-z0-9_]", "_", stem.lower()).strip("_")
    if not tag or not tag[0].isalpha():
        tag = "ref_" + tag
    return tag[:16].ljust(3, "x")


def _parse_refs(specs: list[str], nano: bool = False) -> list[dict]:
    """Each spec is `tag=path_or_url`, or a bare path/url (tag inferred from the filename).

    nano=True (nano_banana_2.1): a bare path gets a lowercase tag that keeps underscores, and an explicit tag may
    contain them; check_image_request then enforces the model's tag rule. Without it nothing changes."""
    out = []
    for spec in specs or []:
        tag, _, target = spec.partition("=")
        if not target:                       # bare path/url
            target, tag = tag, ""
        if not tag:
            stem = pathlib.Path(target.split("?")[0]).stem
            tag = _nano_tag(stem) if nano else re.sub(r"[^A-Za-z0-9]", "", stem)[:16] or "ref"
        if not re.fullmatch(r"[A-Za-z0-9_]{3,16}" if nano else r"[A-Za-z0-9]{3,16}", tag):
            sys.exit(f"bad reference tag {tag!r}: must be 3-16 alphanumeric characters")
        uri = target if target.startswith(("http://", "https://", "data:")) else _data_uri(pathlib.Path(target))
        out.append({"uri": uri, "tag": tag})
    return out


def require_yes(a, est, what: str) -> None:
    """The spend guard: show the estimate; exit 3 unless --yes was given (and the estimate is under --max-credits)."""
    shown = f"~{est} credits (≈ ${est*0.01:.2f})" if est is not None else "unknown cost (model not in COST; check the dashboard)"
    print(f"{what}: estimate {shown}", file=sys.stderr)
    if a.max_credits is not None and est is None:
        print(f"Refusing: --max-credits {a.max_credits:g} is set but the cost is unknown, so the ceiling cannot be checked.", file=sys.stderr)
        sys.exit(EXIT_REFUSED)
    if a.max_credits is not None and est > a.max_credits:
        print(f"Refusing: the estimate is over --max-credits {a.max_credits:g}.", file=sys.stderr)
        sys.exit(EXIT_REFUSED)
    if not a.yes:
        print("Refusing to spend without --yes. Show Aaron the estimate; re-run with --yes after his go.", file=sys.stderr)
        sys.exit(EXIT_REFUSED)


def cmd_image(a):
    if a.prompt:
        prompt = a.prompt
    elif a.prompt_file and a.shot:
        prompt = _prompt_from_file(a.prompt_file, a.shot)
    else:
        raise RequestError("image needs --prompt, or --prompt-file together with --shot")
    ratio, tier = a.ratio, None
    if a.model == NANO_BANANA:
        ratio, tier = resolve_nano_ratio(a.ratio, a.resolution)      # the model's size is its ratio: --resolution picks it
    elif a.resolution:
        raise RequestError(f"--resolution only applies to {NANO_BANANA}; give {a.model} a --ratio")
    body = {"model": a.model, "promptText": prompt, "ratio": ratio or "1344:768"}
    if a.seed is not None:
        body["seed"] = a.seed
    # referenceImages: REQUIRED (>=1) for gen4_image / gen4_image_turbo; OPTIONAL for
    # gemini_2.5_flash / seedream / flux (which can bootstrap from text alone).
    refs = _parse_refs(a.reference, nano=a.model == NANO_BANANA)
    if refs:
        body["referenceImages"] = refs
        print(f"   refs: {', '.join('@' + r['tag'] for r in refs)}", file=sys.stderr)
    check_image_request(a.model, body["ratio"], refs, a.seed)
    est = estimate_simple(a.model, resolution=tier)
    require_yes(a, est, f"image {a.model}" + (f" {tier} ({body['ratio']})" if tier else ""))
    r = paid_call(log=a.log, path="/text_to_image", body=body, label=f"image:{a.model}", model=a.model, est=est,
                  request_sha=sha256_json(body), seed="first output" if a.seed is None else a.seed, out=a.out, timeout=a.timeout or POLL_TIMEOUT,
                  meta={"resolution": tier, "ratio": body["ratio"]} if tier else None)
    print(f"cost: {r['cost_credits']} cr", file=sys.stderr)
    print(json.dumps(r["urls"]))


def _pct(text: str) -> int:
    try:
        n = int(text)
    except ValueError:
        n = -1
    if not 0 <= n <= 100:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number in the range 0-100")
    return n


def cmd_upscale(a):
    """image_upscale: Magnific precision upscaler. A local image under ~3.3 MB is inlined as-is (NOT downscaled, unlike
    --reference); a bigger one is uploaded as an ephemeral asset, but only after the spend guard has passed."""
    target, scale = a.image, a.scale
    local = None
    if target.startswith("http://"):
        raise RequestError(f"{target}: Runway needs https:// (plain http:// is refused)")
    if not target.startswith(("https://", "runway://", "data:")):
        local = pathlib.Path(target)
        if not local.is_file():
            raise RequestError(f"input file not found: {local}")
        if local.suffix.lower() not in IMAGE_EXT:
            raise RequestError(f"{local.name}: upscale takes {sorted(IMAGE_EXT)}")
    size = None
    if a.size:
        m = re.fullmatch(r"(\d+)[xX:](\d+)", a.size)
        if not m:
            raise RequestError(f"--size must look like 1024x768, not {a.size!r}")
        size = (int(m.group(1)), int(m.group(2)))
    elif local:
        size = image_size(local)
    est = estimate_upscale(*(size or (None, None)), scale, model=a.model)
    body = {"model": a.model, "imageUri": target, "scaleFactor": scale}
    for flag, key in (("sharpen", "sharpen"), ("smart_grain", "smartGrain"), ("ultra_detail", "ultraDetail"), ("flavor", "flavor")):
        if getattr(a, flag) is not None:
            body[key] = getattr(a, flag)
    shown = f"{size[0]}x{size[1]} x{scale}" if size else f"unknown size x{scale} (no --size: the dearer price is assumed)"
    require_yes(a, est, f"upscale {a.model}, {shown}")
    if local:
        if local.stat().st_size <= MAX_REF_BYTES:
            body["imageUri"] = f"data:{IMAGE_MIME[local.suffix.lower()]};base64," + base64.b64encode(local.read_bytes()).decode()
        else:
            body["imageUri"] = upload_file(local)
    meta = {"source": target if not local else local.name, "scale": scale, "size": list(size) if size else None}
    r = paid_call(log=a.log, path="/image_upscale", body=body, label=f"upscale:{a.model}", model=a.model, est=est,
                  request_sha=sha256_json({**body, "imageUri": hashlib.sha256(body["imageUri"].encode()).hexdigest()}),
                  input_sha=file_sha256(local) if local else None, seed="n/a", meta=meta, out=a.out, timeout=a.timeout or POLL_TIMEOUT)
    print(f"cost: {r['cost_credits']} cr", file=sys.stderr)
    print(json.dumps(r["urls"]))


# image_to_video models whose reference lists `seed` AND that this client prices (read 3 Nov 2026). The reference also lists
# it for veo3.1, veo3.1_fast, seedance2_fast, seedance2_mini and seedance2_5; the client has no price for those, so --seed is
# refused there. The list is deliberately the stricter one.
VIDEO_SEED_MODELS = ("gen4.5", "gen4_turbo", "seedance2")


def cmd_video(a):
    body = {"model": a.model, "promptText": a.prompt or "", "ratio": a.ratio, "duration": a.duration}
    if a.seed is not None:
        if isinstance(a.seed, bool) or not 0 <= a.seed <= 2**32 - 1:
            raise RequestError(f"--seed must be an integer 0-4294967295, got {a.seed!r}")
        if a.model not in VIDEO_SEED_MODELS:
            raise RequestError(f"--seed: {a.model} has no seed field on image_to_video (models with one: "
                               f"{', '.join(VIDEO_SEED_MODELS)})")
        body["seed"] = a.seed
    if a.image:
        p = pathlib.Path(a.image)
        body["promptImage"] = _data_uri(p) if p.exists() else a.image
    est = estimate_simple(a.model, a.duration)
    require_yes(a, est, f"video {a.model} {a.duration}s")
    r = paid_call(log=a.log, path="/image_to_video", body=body, label=f"video:{a.model}", model=a.model, est=est,
                  request_sha=sha256_json(body), seed="first output" if a.seed is None else a.seed,
                  out=a.out, timeout=a.timeout or VIDEO_TIMEOUT)
    print(f"cost: {r['cost_credits']} cr", file=sys.stderr)
    print(json.dumps(r["urls"]))


def cmd_eval(a):
    print("== Runway eval: one cheap still + one 5s clip ==", file=sys.stderr)
    style = "2D hand-drawn cel anime, bold linework, kinetic action, NOT photorealistic, NOT 3D"
    img_body = {"model": "gemini_2.5_flash",
                "promptText": f"A lone hooded swordsman on a cracked industrial floor at dusk. {style}",
                "ratio": "1344:768"}
    est_img, est_vid = estimate_simple("gemini_2.5_flash"), estimate_simple("gen4_turbo", 5)
    require_yes(a, est_img + est_vid, "eval (one still + one 5s clip)")
    out_dir = pathlib.Path(a.out_dir) if a.out_dir else EVAL_OUT_ROOT / datetime.now(timezone.utc).strftime("eval-%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)      # paid outputs expire in 24-48 h, so they are always saved
    print(f"   outputs go to {out_dir}", file=sys.stderr)
    img = paid_call(log=a.log, path="/text_to_image", body=img_body, label="eval-image", model="gemini_2.5_flash",
                    est=est_img, request_sha=sha256_json(img_body), out=str(out_dir / "still.png"),
                    timeout=a.timeout or POLL_TIMEOUT)
    print("still:", img["urls"], f"cost: {img['cost_credits']} cr")
    if img["urls"]:
        vid_body = {"model": "gen4_turbo", "promptImage": img["urls"][0],
                    "promptText": "slow push in, subtle motion", "ratio": "1280:720", "duration": 5}
        vid = paid_call(log=a.log, path="/image_to_video", body=vid_body, label="eval-video", model="gen4_turbo",
                        est=est_vid, request_sha=sha256_json(vid_body), out=str(out_dir / "clip.mp4"),
                        timeout=a.timeout or VIDEO_TIMEOUT)
        print("clip:", vid["urls"], f"cost: {vid['cost_credits']} cr")
    print("\nIf both printed URLs, the wrapper + key + model IDs work. Log the costs in the card STATUS.md (prototypes/<slug>/STATUS.md).", file=sys.stderr)


def cmd_v2v(a):
    req, sha, base, info = request_context(a.request)
    plan = prepare_v2v(req, make_resolver(base, None), info)        # dry run: validates and prices, uploads nothing
    for w in plan["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    require_yes(a, plan["estimate"], f"v2v {req['model']} ({plan['tier']}, {plan['out_seconds']} s out)")
    real = prepare_v2v(req, make_resolver(base, upload_file), info)  # now uploads local inputs
    where, video = classify_target(req["inputs"]["video"], base)
    r = paid_call(log=a.log, path="/video_to_video", body=real["body"], label=f"v2v:{req['model']}",
                  model=req["model"], est=plan["estimate"], input_seconds=info["seconds"], request_sha=sha,
                  input_sha=file_sha256(video) if where == "local" else None, seed=real["seed"],
                  meta=req["meta"], out=a.out, timeout=a.timeout or VIDEO_TIMEOUT)
    print(f"cost: {r['cost_credits']} cr (our estimate {plan['estimate']})", file=sys.stderr)
    print(json.dumps({"task_id": r["task_id"], "cost_credits": r["cost_credits"], "estimate": plan["estimate"],
                      "paths": r["paths"], "request_sha256": sha}))


def cmd_fetch(a):
    task = _req("GET", f"/tasks/{a.task}")
    status = (task.get("status") or "").upper()
    row = {"event": "fetch", "task_id": a.task, "status": status,
           "cost_credits": (task.get("cost") or {}).get("credits"), "output_path": None, "output_paths": []}
    if status != "SUCCEEDED":
        log_row(a.log, row)
        if status in ("PENDING", "THROTTLED", "RUNNING"):
            print(f"task {a.task} is {status}; try again later (it is not cancelled).", file=sys.stderr)
            sys.exit(EXIT_PENDING)
        print(f"task {a.task} {status}: {task.get('failure')} [{task.get('failureCode')}]", file=sys.stderr)
        sys.exit(EXIT_FAILED)
    urls = task.get("output") or []
    paths, failure = _download_all(urls, a.out)
    row.update(output_path=paths[0] if paths else None, output_paths=paths)
    if failure:
        row["download_error"] = failure
        log_row(a.log, row)
        print(f"task {a.task} succeeded but the download failed ({failure}); its output URL has probably "
              f"expired (outputs live 24-48 h).", file=sys.stderr)
        sys.exit(EXIT_FAILED)
    log_row(a.log, row)
    print(json.dumps({"task_id": a.task, "cost_credits": row["cost_credits"], "paths": paths}))


def main(argv=None):
    p = argparse.ArgumentParser(description="Runway dev-API client (studio). Spending commands need --yes.")
    sub = p.add_subparsers(dest="cmd", required=True)

    logp = argparse.ArgumentParser(add_help=False)
    logp.add_argument("--log", default=str(DEFAULT_LOG), metavar="PATH",
                      help="append-only JSONL spend log (default: tools/runway/spend-log.jsonl)")
    paid = argparse.ArgumentParser(add_help=False, parents=[logp])
    paid.add_argument("--yes", action="store_true", help="authorise spending credits; without it the estimate is printed and the exit code is 3")
    paid.add_argument("--max-credits", type=float, metavar="N", help="refuse any call whose estimate is above N, even with --yes")
    paid.add_argument("--timeout", type=int, metavar="SECONDS",
                      help=f"how long to wait for the task (default {POLL_TIMEOUT} for images, {VIDEO_TIMEOUT} for video); a timeout never cancels")

    pu = sub.add_parser("upload", help="upload a local file; prints its runway:// URI (free)")
    pu.add_argument("file"); pu.set_defaults(fn=cmd_upload)

    pg = sub.add_parser("estimate", help="price a p47-render/1 request file; spends nothing, sends nothing")
    pg.add_argument("request"); pg.set_defaults(fn=cmd_estimate)

    pf = sub.add_parser("fetch", parents=[logp], help="re-download a task's outputs (free)")
    pf.add_argument("--task", required=True); pf.add_argument("--out", required=True)
    pf.set_defaults(fn=cmd_fetch)

    pe = sub.add_parser("eval", parents=[paid]); pe.set_defaults(fn=cmd_eval)
    pe.add_argument("--out-dir", help="where to save the still and the clip (default: tools/runway/out/eval-<timestamp>/)")

    pi = sub.add_parser("image", parents=[paid]); pi.set_defaults(fn=cmd_image)
    pi.add_argument("--model", default="gemini_2.5_flash")
    pi.add_argument("--ratio", help="model-specific size, e.g. 1344:768 (default for most models); nano_banana_2.1 takes "
                                    "pixel sizes such as 1584:672, 3168:1344, 6336:2688 (default: the 1K panorama)")
    pi.add_argument("--resolution", choices=sorted(NANO_BANANA_RATIOS),
                    help=f"{NANO_BANANA} only: 1K / 2K / 4K = 4 / 6 / 12 credits. There is no such API field: the tier is "
                         "the --ratio, so this moves --ratio to the same aspect in that tier (1584:672 + 2K -> 3168:1344)")
    pi.add_argument("--prompt")
    pi.add_argument("--prompt-file"); pi.add_argument("--shot")
    pi.add_argument("--reference", action="append", metavar="TAG=PATH_OR_URL",
                    help="reference image; repeatable. Local paths are inlined as data URIs. "
                         "Address it in the prompt as @TAG.")
    pi.add_argument("--seed", type=int, help="lock a seed so a winning frame can be reproduced")
    pi.add_argument("--out", required=True, help="where to save the image (required: outputs expire in 24-48 h)")

    pn = sub.add_parser("upscale", parents=[paid], help="upscale an image with Magnific precision (spends: 25 credits, "
                                                        "150 when the output is over 4096 px)")
    pn.set_defaults(fn=cmd_upscale)
    pn.add_argument("image", help="local PNG/JPEG/WebP (inlined if <= 3.3 MB, else uploaded) or an https:// URL")
    pn.add_argument("--model", default=UPSCALE_MODEL)
    pn.add_argument("--scale", type=int, choices=(2, 4, 8, 16), default=2, help="multiplies each side (default 2)")
    pn.add_argument("--size", metavar="WxH", help="input size in px; read from a local PNG/JPEG header, but needed for a URL "
                                                  "(without it the 150-credit price is assumed). Input sides must be 300-8000 px")
    pn.add_argument("--flavor", choices=("sublime", "photo", "photo_denoiser"),
                    help="sublime = illustration, photo = photographic, photo_denoiser = noisy photos")
    pn.add_argument("--sharpen", type=_pct, metavar="0-100")
    pn.add_argument("--smart-grain", type=_pct, metavar="0-100", dest="smart_grain")
    pn.add_argument("--ultra-detail", type=_pct, metavar="0-100", dest="ultra_detail")
    pn.add_argument("--out", required=True, help="where to save the result (required: outputs expire in 24-48 h)")

    pv = sub.add_parser("video", parents=[paid]); pv.set_defaults(fn=cmd_video)
    pv.add_argument("--model", default="gen4_turbo")
    pv.add_argument("--ratio", default="1280:720")
    pv.add_argument("--duration", type=int, default=5)
    pv.add_argument("--image", help="URI/dataURI of the source still")
    pv.add_argument("--prompt")
    pv.add_argument("--seed", type=int, help="fix the seed (gen4.5, gen4_turbo, seedance2); logged in the pre row. "
                    "Same seed and request gives a similar result, not an identical one")
    pv.add_argument("--out", required=True, help="where to save the clip (required: outputs expire in 24-48 h)")

    px = sub.add_parser("v2v", parents=[paid], help="video-to-video from a p47-render/1 request file (spends)")
    px.add_argument("request"); px.add_argument("--out", required=True)
    px.set_defaults(fn=cmd_v2v)

    a = p.parse_args(argv)
    try:
        a.fn(a)
    except (ApiError, RequestError) as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
