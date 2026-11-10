# Sub-plan C: measurement, controls and analysis (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development for every task (red, then green, then commit). Steps use checkbox (`- [ ]`) syntax. Executed inline by the sub-plan C agent on 31 Oct 2026, one commit per task.

**Goal:** the code that measures a render against its take (alignment gate, masked line drift, seam cells, nulls, controls, invariants) and the two registered analysis scripts, all written and tested on synthetic fixtures before any take or render exists, so that registration (Gate R) can freeze them.

**Architecture:** pure-numpy modules in `seam/` that run in the prototype's uv venv (align, regions, pairs, cells, drawn, controls, hands, ocr) plus one job, `seam/lines_job.py`, that runs only in `~/tools/ComfyUI/.venv/bin/python` with the public StillDrawn checkout on `PYTHONPATH`, importing the frozen `metrics.inkstab` line extractor, `_chamfer` and `_tol_iou`. The two venvs meet through npz files (`seam/pairs.py`). `analysis/h_contact.py` and `analysis/ratings.py` read JSON/CSV and write deterministic JSON to `analysis/out/`.

**Tech stack:** Python 3.12; numpy, scipy, scikit-image, OpenCV (ORB, RANSAC, warps), PyAV and ffmpeg (decode by timestamp, codec-null re-encodes), MediaPipe Tasks (hand landmarks), pyobjc Vision (OCR), unittest (ComfyUI venv) and pytest (repo venv).

**Source of truth:** master plan `~/projects/studio/docs/p47/plan-2026-10-30.md` R0.3 and R0.4, Interfaces (`p47-measure/1`); P46 plan `docs/p46/plan-2026-10-31.md` A9.4 and `docs/p46/a9-must-state.md` (the mirror term). Where this plan makes a reading the master plan is silent on, it is listed under "Readings" and appended to `docs/p47-calls.md`.

**Out of scope here (other sub-plans or later phases):** masks and SAM tracks, cue detectors, laws, compiler (sub-plan B); running the nulls and controls on real takes (Phase 3.4); the assembly of a `p47-measure/1` file from align + lines + contact for real renders (Phase 8, uses the functions here); the web export (Phase 10).

---

## Conventions (all tasks)

- **Grid and rate.** Analysis frames are RGB uint8 `(720, 1280, 3)`; masks are bool `(720, 1280)`; analysis rate 15 fps; analysis time `t_i = i / 15`.
- **Direction.** In every drift and cell call `a` is the render (or the null/re-encode, or the composite) and `b` is the take. "Lines vanish from R" = take lines in R with no render line in R.
- **Seeds.** OpenCV RANSAC: `cv2.setRNGSeed(20261031)` before each fit. H test: `numpy.random.default_rng(20261101)`.
- **No sealed content.** Fixtures use fictional objects and words (`HELLO`, `cup`, `lamp`); never a law, a law word or the note word.
- **Commits.** Stage by explicit path only; retry on `.git/index.lock`. Never touch sub-plan B's files (`seam/masks.py`, `seam/cues/`, `seam/laws.py`, `seam/compile.py`, their tests, MediaPipe files in `models/`).

## File map

| File | Responsibility | Venv |
|---|---|---|
| `seam/video.py` | decode with timestamps, resize to 1280×720, resample to 15 fps by timestamp; codec-null re-encodes (720p, 1080p) | repo |
| `seam/align.py` | motion energy, lag check, per-frame similarity fit, ρ from the round trip, gate, warp | repo |
| `seam/maskrule.py` | the A9.4 frame rule | both |
| `seam/regions.py` | A(t), R(t), contact c(t) | both |
| `seam/cells.py` | seam cells (32 px, τ = 2) and the 2-bit seam file | both |
| `seam/drawn.py` | moment alignment, line density | both |
| `seam/controls.py` | paste and shift controls, κ from IoUs | both |
| `seam/pairs.py` | npz contract between the venvs | both |
| `seam/lines_job.py` | line maps (frozen inkstab), D, D0, cells, homes, stays drawn, controls CLI | ComfyUI only |
| `seam/hands.py` | MediaPipe keypoints and drift | repo |
| `seam/ocr.py` | Apple Vision OCR, CER | repo |
| `analysis/h_contact.py` | R0.4 test and secondaries | repo |
| `analysis/ratings.py` | per-law hit rates, Wilson, Fleiss' κ | repo |
| `tests/test_*.py` | pytest, repo venv | repo |
| `tests/comfy/test_lines_job.py` | unittest; detector tests skip outside the ComfyUI venv | ComfyUI |
| `models/MODELS.md` | add the netG.pth row (SHA-256, size, path) | — |

## Readings (where the master plan is silent; each goes in the calls file)

1. **Frame rule cases beyond the plan text.** A9.4's literal text leaves `a∩R ≠ ∅, b∩R = ∅` and `a∩R = b∩R = ∅` undefined (a mean over an empty set). `maskrule.frame_rule` follows `metrics/masked.py` in StillDrawn's private working repo and `docs/p46/a9-must-state.md`: the mirror one-sided term `EDT(~b)[a∩R].mean()` and None. The equality test against masked.py pins this.
2. **Fit residual.** Residual = RMS reprojection error of the RANSAC inliers (threshold 3 px, 2,000 iterations, confidence 0.999, 10 refine iterations). ORB 4,000 features, Hamming brute-force with cross-check. A fit with fewer than 20 matches or 20 inliers fails (the frame scores None).
3. **Exclusion.** ORB keypoints are found on both images under the same mask `~dilate(page, 64)` on the take grid, dilation computed as `EDT(~page) > 64` complemented.
4. **Lag.** Motion energy e(t) = mean |grey_t − grey_{t−1}| (grey 0–255) inside the take's union mask of hands and props at t; best lag maximises Pearson r over lags −5…+5 analysis frames (overlap ≥ 3); ties → smaller |lag|, then the negative one. Positive lag = render late. Pass iff |lag| ≤ 1. The same take masks are used for the render's energy (on the warped render).
5. **Timestamp mapping.** Each stream is decoded with its own pts; analysis time t_i takes the source frame of nearest pts (a tie goes to the earlier frame); t_i runs over i = 0…floor(15·last_pts).
6. **Codec null encode.** `ffmpeg -vf scale=-2:<h>:flags=lanczos -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -an`, at h = 720 and h = 1080, then decoded onto the analysis grid (INTER_AREA). D0 is the frame rule of the re-encode against the take under the render's R(t).
7. **Cells.** 40 × 23 cells (the bottom row is 16 px tall). A cell is *creature* if any of its pixels is outside R(t). Line counts are on the undilated maps inside the cell. Tolerant IoU dilates both full frames by `disk(2)` (as `_tol_iou`) and counts inside the cell. Frames that fail the gate have all cells none. Seam file: row-major cells, 4 per byte, `c0 | c1<<2 | c2<<4 | c3<<6`, each frame padded to a whole byte; 0 none, 1 kept, 2 redrawn, 3 creature; no header (cols and rows travel in `p47-measure/1`).
8. **κ.** `kappa_keep = np.percentile(ious, 1)` (linear) over room cells (fully in R, ≥ 20 line px in either map) of all aligned frames.
9. **Paste control.** The scan crop is alpha-composited onto the take (not re-encoded), so the control isolates leakage of creature lines across the margin. The pass fraction is over frames with D not None; threshold = P95 (linear) of D0 under the same m, over its non-None frames. m ∈ (32, 48, 64), smallest passing; else "not testable".
10. **Shift control.** Patch 64 × 64 at a cell-aligned origin, content moved by (dx, dy) = (3, 3) px (diagonal; amended 31 Oct by the controller, call 57, from (3, 0), which leaves horizontal strokes kept); a frame passes if all four patch cells are redrawn; pass iff ≥ 90 % of the frames pass (none counts as failure). `choose_shift_patch` picks the cell-aligned 2 × 2 block fully inside R in every frame with ≥ 20 line px per cell in every frame, the most line pixels, first in row-major order on a tie.
11. **Stays drawn.** Density = render line px inside the creature mask / mask area. Chamfer to the scan: the render lines inside the creature mask are moment-aligned onto the scan's line map (centroid translation and isotropic scale by radius of gyration; no rotation, so a turned pose stays drift), then `inkstab._chamfer`.
12. **Hands.** One hand (the first MediaPipe returns), 21 points in pixels; drift = mean point distance / diagonal of the take hand's landmark bounding box; None when either side has no hand.
13. **OCR.** `VNRecognizeTextRequest`, accurate level, language correction off (it would invent words), lines sorted top-to-bottom then left-to-right and joined by a space. CER = Levenshtein(take text, render text) / len(take text) after upper-casing and collapsing whitespace; None when the take text is empty.
14. **H details.** r undefined (render not testable) when the non-contact mean is 0. Circular shifts k ∈ {0…n−1} (identity included). Draws: for each testable render in sorted render-id order, `rng.integers(0, n_i, size=10_000)`, one generator for the primary test. Each secondary runs the same procedure with its own `default_rng(20261101)`; secondaries print p but carry no verdict. Tercile secondary: per render, cut points at the 1/3 and 2/3 quantiles of motion energy over its eligible frames; minimum per side 3 instead of 8. Outputs rounded to 12 significant digits.
15. **Ratings.** One export per rater (`--rater R1=path/ratings.csv`); an export with more than one visitor is refused. Hits compare the `option` label with the key label. "Clip minus baseline" = clip Q2 hit rate − baseline Q2b hit rate (the Q1 difference is printed beside it). Fleiss' κ uses the per-item-n generalisation (equal to Fleiss with equal n), categories = option labels, None when P_e = 1.

---

### Task 1: `seam/maskrule.py`, the A9.4 frame rule

**Files:** create `seam/maskrule.py`, `tests/test_maskrule.py`.

API:
```python
def frame_rule(a, b, R) -> float | None          # a = render map, b = take map, R = measured region
def frame_rule_dt(a, b, da, db, R) -> float | None  # da = EDT(~b), db = EDT(~a), shared across regions
```
Body (to the A9.4 text plus Reading 1):
```python
if not a.any() or not b.any(): return None
aR, bR = a & R, b & R
if aR.any() and bR.any(): return float(0.5 * (da[aR].mean() + db[bR].mean()))
if bR.any(): return float(db[bR].mean())     # lines vanished from R
if aR.any(): return float(da[aR].mean())     # lines appeared in R (mirror)
return None
```
- [ ] Tests (write first, see them fail with ImportError):
  - `R` all-true equals `inkstab._chamfer` bit for bit (`==` on floats) on 20 random sparse maps; skip if `/Users/aaron/projects/stilldrawn/metrics/inkstab.py` is missing.
  - None if `a` empty or `b` empty, whatever R.
  - Vanishing: b has a line inside R, a has lines only outside R → equals `EDT(~a)[b&R].mean()`, and is > 0.
  - Mirror and both-empty cases.
  - A 3 px horizontal shift of vertical lines spaced 40 px gives 3.0 under R all-true.
  - Equality with `masked.masked_chamfer` on 50 random (a, b, R) triples covering all branches, for each of `/Users/aaron/projects/stilldrawn/metrics/masked.py` and `metrics/masked.py` in StillDrawn's private working repo that exists (read-only import by file path; skip when neither exists).
- [ ] Implement; `uv run pytest tests/test_maskrule.py -v` green.
- [ ] Commit `seam/maskrule.py tests/test_maskrule.py`.

### Task 2: `seam/video.py`, timestamps and codec-null re-encodes

**Files:** create `seam/video.py`, `tests/test_video.py`.

API:
```python
SIZE = (1280, 720); FPS = 15
def read_video(path, size=SIZE) -> tuple[np.ndarray (N,H,W,3) uint8, np.ndarray pts_seconds]
def analysis_times(last_pts, fps=FPS) -> np.ndarray      # i/fps, i = 0..floor(fps*last_pts + 1e-9)
def nearest_indices(pts, times) -> np.ndarray            # nearest pts, tie -> earlier
def resample(frames, pts, times) -> np.ndarray
def reencode(src, dst, height) -> Path                   # Reading 6; ffmpeg via subprocess, check=True
def write_video(path, frames, fps)                       # test helper: libx264 crf 0 via PyAV
```
- [ ] Tests: `nearest_indices` on 30 fps and 24 fps pts (tie goes earlier); `analysis_times(2.0)` has 31 entries; a 30 fps synthetic video round-trips through `write_video`/`read_video` with pts k/30; `reencode` at 720 and 1080 produces those heights (ffprobe) and decodes onto 1280×720.
- [ ] Implement; tests green; commit.

### Task 3: `seam/align.py`, lag, fit, ρ, gate, warp

**Files:** create `seam/align.py`, `tests/test_align.py`.

API:
```python
def grey(frame) -> np.ndarray float32
def exclusion(page_mask, margin=64) -> bool mask (True = excluded)
def motion_energy(frames, masks) -> np.ndarray (N-1,)
def best_lag(e_take, e_render, max_lag=5) -> tuple[int, float]
def lag_ok(lag, tol=1) -> bool
@dataclass class Fit: M (2x3), scale, residual, n_matches, n_inliers
def fit_similarity(render, take, exclude) -> Fit | None     # render -> take, Reading 2
def round_trip_rho(take_frames, rt_frames, exclude) -> tuple[float, list[float]]  # max(1, 2*P99)
def frame_ok(fit, rho, scale_tol=0.01) -> bool
def gate(fits, rho, lag, min_frac=0.90) -> dict {pass, lag, rho, frames_ok, ok: [bool]}
def warp(frame, M, size=SIZE) -> np.ndarray       # INTER_LINEAR, BORDER_REPLICATE
def warp_mask(mask, M, size=SIZE) -> bool mask    # INTER_NEAREST, border 0
```
Fixture: a deterministic textured "room" (seeded rectangles, circles and lines on a mid-grey with mild noise), and a page rectangle in the middle.
- [ ] Tests:
  - shift (3.5, −2.0) → fit recovers translation within 0.1 px, scale within 0.002, residual < 1, `frame_ok`;
  - scale 1.02 about the centre → scale ≈ 1.02, not ok; scale 1.005 → ok;
  - local sinusoidal warp (amplitude 4 px, period 300 px) → residual > ρ (=1.0) → not ok;
  - identical round trip → ρ = 1.0; a round trip with residuals [0.6]*n → ρ = 1.2;
  - `gate`: 10 frames with 1 bad → pass; 2 bad → fail; lag 2 → fail;
  - `best_lag` recovers a shift of 3 and −2 on a random energy series; ties → smaller |lag|;
  - frame-rate conversion: a moving square rendered at 24 fps against a take at 30 fps, both resampled to 15 fps by timestamp → square x agrees within 200/48 px, best lag 0;
  - a render delayed by 2 analysis frames → lag 2, lag check fails;
  - `warp` of the shifted render with the fitted M equals the take within 2 grey levels (mean abs) away from the borders.
- [ ] Implement; green; commit.

### Task 4: `seam/regions.py` and `seam/cells.py`

**Files:** create both, `tests/test_cells.py`.

API:
```python
# regions.py
def dilate(mask, r) -> bool mask           # EDT(~mask) <= r; empty -> empty
def measured_region(creature, home, m) -> R  # ~dilate(creature | home, m)
def contact(creature, touched, hand, d=8) -> bool  # dilate(creature, d) & (touched | hand) nonempty
# cells.py
CELL = 32; NONE, KEPT, REDRAWN, CREATURE = 0, 1, 2, 3
def grid_shape(h=720, w=1280, cell=CELL) -> (rows, cols)   # (23, 40)
def tol_dilate(m, tau=2) -> skimage binary_dilation(m, disk(tau))
def classify(Lt, Lr, R, kappa, tau=2, min_px=20, cell=CELL) -> (codes uint8 (rows, cols), iou float (rows, cols) nan where unscored)
def room_ious(codes_iou, codes) -> list[float]       # iou of room cells (fully in R, >= min_px in either)
def pack(codes_seq) -> bytes;  def unpack(data, rows, cols) -> np.ndarray (n, rows, cols)
```
- [ ] Tests: `grid_shape` = (23, 40); identical maps → all room cells with lines kept (iou 1); a 3 px shift of vertical lines → those cells redrawn at κ = 0.8; cells with < 20 px in both → none; a cell touching ~R → creature; an iou between κ/2 and κ → none; with one cell the size of the frame, `classify`'s iou equals `inkstab._tol_iou(a, b, 2)` (skip if missing); pack/unpack round-trip on random codes, 230 bytes per frame; `measured_region` and `contact` on small synthetic masks (`dilate` equals `binary_dilation(disk(r))` on a test mask).
- [ ] Implement; green; commit.

### Task 5: `seam/drawn.py`

**Files:** create `seam/drawn.py`, `tests/test_drawn.py`.

API: `moment_align(src, ref) -> bool mask on ref.shape | None` (Reading 11; points rounded to nearest pixel, out-of-grid dropped); `density(lines, mask) -> float | None`.
- [ ] Tests: a ring scaled 2× and translated aligns back onto the reference ring with chamfer < 1 px (scipy EDT chamfer); empty → None; density of a half-filled mask = 0.5.
- [ ] Implement; green; commit.

### Task 6: `seam/pairs.py` and `seam/controls.py`

**Files:** create both, `tests/test_controls.py`.

API:
```python
# pairs.py  (np.savez, uncompressed; meta as JSON string)
def write_pair(path, *, take, render, valid, R, t, creature=None, homes=None, scan=None, meta=None)
def read_pair(path) -> dict
# controls.py
M_CHOICES = (32, 48, 64)
def paste(frames, rgba, xy, window) -> (frames, masks)     # alpha composite, mask = alpha > 127
def d_series(maps_a, maps_b, regions) -> list[float|None]   # frame_rule per frame
def p95(xs) -> float | None
def paste_control(take_maps, paste_maps, null_maps, paste_masks, home, m_choices=M_CHOICES, need=0.95) -> dict {m, testable, per_m: {m: {threshold, frac, pass}}}
def shift_patch(frames, xy, size=64, dx=3, dy=0) -> frames
def choose_shift_patch(maps, regions, cell=32, min_px=20) -> (x, y) | None
def shift_control(take_maps, shifted_maps, regions, xy, kappa, need=0.90) -> dict {frac, pass, per_frame}
def kappa_keep(ious) -> float | None   # np.percentile(ious, 1)
```
Synthetic extractors: `dark` (grey < 128) and `leaky(r)` (dark dilated by r px, which spreads a pasted figure's lines outward like a large receptive field).
- [ ] Tests: paste with `dark` → m = 32, testable; with `leaky(40)` → 32 fails, m = 48; with `leaky(80)` → not testable; shift of a vertical-line patch → ≥ 90 % frames redrawn at κ = 0.8, pass; zero shift → fail; `choose_shift_patch` returns a cell-aligned origin with enough lines and avoids ~R; `kappa_keep([...])` equals `np.percentile`; pairs round-trip preserves dtypes and shapes.
- [ ] Implement; green; commit.

### Task 7: `seam/lines_job.py` (ComfyUI venv) and the netG hash

**Files:** create `seam/lines_job.py`, `tests/comfy/__init__.py`, `tests/comfy/test_lines_job.py`; modify `models/MODELS.md`.

- Guard: `in_comfy_venv()` is True iff `Path(sys.prefix).resolve() == Path.home()/"tools/ComfyUI/.venv"` resolved. `main()` refuses otherwise (exit 2). It sets `STILLDRAWN_CONTROLNET_AUX_SRC` to `~/tools/ComfyUI/custom_nodes/comfyui_controlnet_aux/src` if unset, puts `--stilldrawn` (default `/Users/aaron/projects/stilldrawn`) first on `sys.path`, imports `metrics.inkstab`, and checks `DEFS["version"] == "inkstab 1.0 (2026-08-12)"` and `DEFS["iou_tolerance_px"] == 2`.
- `NETG = ~/tools/ComfyUI/custom_nodes/comfyui_controlnet_aux/ckpts/lllyasviel/Annotators/netG.pth`; `NETG_SHA256` constant; the job hashes the file at start and refuses on mismatch.
- `measure(pair, null=None, kappa=None, extract=line_maps) -> dict`: line maps once per frame; `D` = frame rule (render vs take) under R(t) where valid, else None; `D0` likewise for the null pair (same R); cells when κ given (else only `room_iou` for κ); homes: frame rule per home mask; stays drawn: density and scan chamfer. Writes the seam file with `cells.pack`.
- CLI: `measure --pair P.npz [--null N.npz] [--kappa K] --out OUT.json [--seam OUT.bin]`; `paste-control`, `shift-control` (wrapping `seam.controls` with real line maps); `hash-netg`.
- Output JSON `p47-lines/1`: `{schema, inkstab_version, stilldrawn_commit, netG_sha256, device, params{tau, cell, min_px, kappa}, n_frames, t, D, D0, homes, density, scan_chamfer, room_iou, seam{file, cols, rows}, seconds}`.
- [ ] Tests (unittest): pure parts run anywhere (refusal outside the venv; output schema with a fake extractor); detector tests `skipUnless(in_comfy_venv())`: inkstab imports and its DEFS match; `NETG_SHA256` matches the file; `frame_rule` with R all-true equals `inkstab._chamfer` on real line maps of two synthetic drawings; a 3 px shift of a synthetic line drawing gives D ≈ 3 (2–4) through the real extractor; vanished lines on real maps score the one-sided term.
- [ ] Record the SHA-256 in `models/MODELS.md`.
- [ ] Run `~/tools/ComfyUI/.venv/bin/python -m unittest discover -s tests/comfy -t . -v` green; `uv run pytest` green (detector tests skipped).
- [ ] Time one synthetic 150-frame pair end to end (`tools/time_lines_job.py`) and record seconds per frame in LOG.
- [ ] Commit.

### Task 8: `seam/hands.py` and `seam/ocr.py`

**Files:** create both, `tests/test_hands.py`, `tests/test_ocr.py`.

- hands: `keypoint_drift(take_kp, render_kp)`; `HandTracker(model_path=models/hand_landmarker.task)` with `.detect(frame) -> (21, 2) | None` (MediaPipe Tasks, IMAGE mode, one hand); `drift_series(tracker, take, render, valid)`.
- ocr: `recognise(rgb, box=None) -> str`; `normalise(s)`; `levenshtein(a, b)`; `cer(ref, hyp)`; `cer_series(take, render, boxes, valid, every=3)` (None on frames not sampled).
- [ ] Tests: drift of a translated skeleton = shift / diagonal; None handling; `HandTracker` on a blank frame returns None (skip when the model file is missing); OCR reads a rendered "HELLO" (Helvetica, 140 px) as HELLO; `cer("HELLO", "HELP") == 0.4`; `cer("", x)` is None.
- [ ] Implement; green; commit.

### Task 9: `analysis/h_contact.py`

**Files:** create `analysis/h_contact.py`, `tests/test_h_contact.py`, fixtures generated in the test.

Input: `p47-measure/1` JSON files (`render`, `align.pass`, `series.{D, contact, eligible, motion?, hand?, ocr_cer?, redrawn_object?, redrawn_rest?}`, optional `variants: {name: {D, contact, eligible}}`), optional `--meta` `{render: {material}}`.

API: `render_r(D, contact, eligible, min_side=8) -> (r | None, n_c, n_nc)`; `test(renders, rng, draws=10_000, min_side=8) -> {n_testable, T, p, median_r, per_render}`; `verdict(res)`; `secondaries(...)`; `run(paths, meta) -> dict`; CLI `h_contact.py MEASURE.json... [--meta M] --out analysis/out/h_contact.json`.
- [ ] Tests: hand-computed r and T on a 2-render fixture; eligibility excludes D None and object-absent frames; a render with 7 frames on one side is not testable; unaligned render not testable; fewer than 4 testable → "not testable"; 6 renders with strong contact peaks (r ≈ 2) → supported, p ≤ 0.05; 6 renders with no effect → not supported; p's formula `(1 + k) / 10001` (p ≥ 1/10001); median r below 1.25 with small p → not supported; secondaries present (all_frames, motion terciles, variants, ink_only); two runs write byte-identical files.
- [ ] Implement; green; commit.

### Task 10: `analysis/ratings.py`

**Files:** create `analysis/ratings.py`, `tests/test_ratings.py`.

Answer key (`sealed/answer-key.json`, fictional in tests): `{salt, questions: {clip_target: "q1", clip_behaviour: "q2", base_target: "q1b", base_behaviour: "q2b"}, clips: {item: {law, target, behaviour}}, baseline: {item: {law, target, behaviour}}}`.

API: `read_export(path) -> rows` (blindpanel v0.2 CSV: `visitor,instrument,part,position,item,question,score,flags,option`); `wilson(k, n, z=1.959963984540054)`; `fleiss_kappa(table)`; `analyse(raters: {id: rows}, key) -> dict`; CLI `ratings.py --key K --rater R1=path ... --out analysis/out/ratings.json`.
- [ ] Tests: Wilson against known values (k = 0, n = 10 → upper 0.2775; 5/10 → 0.2366–0.7634); Fleiss on the Wikipedia example (κ = 0.210); κ None on a single category; per-law Q1, law (both), baseline Q2, difference on a 3-rater fictional fixture computed by hand; an export with two visitors refused; a CSV option containing a comma parses; two runs byte-identical.
- [ ] Implement; green; commit.

### Task 11: records

- [ ] LOG.md entry (what was built, counts, seconds per frame, netG hash, deviations).
- [ ] Append the readings above and any deviations as numbered calls to `~/projects/studio/docs/p47-calls.md` (re-read it first).
- [ ] Commit LOG.md (and this plan if amended).

## Self-review (done at writing)

- Spec coverage: lag, fit, ρ, None frames, 90 % rule, warp, re-encodes, synthetic shifts/scales/lags/fps (Task 3, 2); frame rule and both equality tests (1); lines job, netG hash, D, D0, cells, seam file, stays drawn, timing, unittest (7, 4, 5); hands, OCR, moment helper (8, 5); paste and shift controls (6, run with real maps in 7's CLI); H primary and secondaries (9); ratings (10). Redrawn share in the touched object, hand drift and note CER contact vs non-contact are descriptive secondaries in 9, read from the measure file's series.
- The plan gives full contracts and test cases rather than complete code: the same agent executes it immediately, test-first, and each task's commit is the reference code.
