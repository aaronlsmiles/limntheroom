# Sub-plan B: masks, cues, compiler. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development. Every task is red → green → commit. Steps use checkbox (`- [ ]`) syntax. Executed inline by one Opus 5.5 · high subagent on 31 Oct 2026, overnight, while sub-plan C ran in the same repo.

**Goal:** Turn a phone take into SAM 2.1 masks and a `p47-cues/1` cue sheet, and turn a cue sheet × a `p47-laws/1` file into a `p47-render/1` request plus a clause trace, all tested on synthetic fixtures only.

**Architecture:** `seam/masks.py` owns frame sampling at 15 fps, the SAM 2.1 CPU tracker, the bit-packed mask store, the R0.3 quality rule and grid-overlay frames for the point-placing agent. `seam/cues/*.py` are independent detectors; each returns plain event dicts and has a pure, separately tested core (interval logic) beneath its heavy front end (MediaPipe, Vision, OpenCV). `seam/cues/sheet.py` validates and assembles the sheet. `seam/laws.py` validates laws; `seam/compile.py` renders a fixed-template prompt and hands it to per-model adapters whose output must pass the hub client's offline `estimate`.

**Tech stack:** Python 3.12 (repo uv venv), numpy, OpenCV, SciPy, PyAV, MediaPipe 1.2 tasks API, SAM 2.1 small at `2b90b9f` on CPU, Apple Vision through pyobjc 13, pytest 9. The hub's `tools/runway/runway_gen.py` (stdlib only) is called as a subprocess for validation; it is never imported, and `runway.sh` is never run.

**Source spec:** master plan `~/projects/studio/docs/p47/plan-2026-10-30.md`: R0.3 (mask quality rule, 15 fps), Phase 2 (2.1, 2.2, 2.4) and Interfaces (`p47-cues/1`, `p47-laws/1`).

---

## Ground rules for this sub-plan

1. **Sealed laws.** The real laws live only in gitignored `sealed/`. No committed file (tests, fixtures, docstrings, commit messages, this plan) states a real law, label, clause or decoy. Tests use fictional fixture laws whose behaviours are deliberately absurd (spinning like a top, juggling dots, standing on its head) and tagged `(fixture)`. The validator's vocabulary check is shown with the fictional "felt" material, which it must refuse.
2. **Compiled real requests are sealed too.** A compiled prompt contains law clauses. `seam/compile.py` refuses to write a request compiled from a laws file inside `sealed/` to any path outside `sealed/`. Real requests therefore live in `sealed/requests/` until the rating window closes; their hashes go in the manifest at R0.
3. **Shared repo.** Sub-plan C owns `seam/align.py`, `seam/maskrule.py`, `seam/lines_job.py`, `seam/hands.py`, `seam/ocr.py`, `seam/drawn.py`, `analysis/` and their tests. This plan touches only the files listed below. Stage by explicit path; check `git status` for `sealed/` before each commit; retry on `.git/index.lock`.
4. **No generation, no spend.** The only Runway touch is `env -u RUNWAY_API_KEY python3 tools/runway/runway_gen.py estimate <file>` (offline, sends nothing). Never `runway.sh`, never `--yes`.
5. **Speed.** The default `uv run pytest` must stay under about 2 minutes. The one SAM test that runs by default tracks 6 frames (~15 s); the longer track runs only with `LIMN_SLOW=1`.

## Decisions taken while writing (also in LOG and the hub calls file)

- **Laws file format: JSON** (`sealed/laws.json`). PyYAML is present only transitively (hydra-core → omegaconf), not as a declared dependency, and stdlib JSON gives canonical bytes for hashing. This changes R0.9's `sealed/laws.yaml` to `sealed/laws.json`.
- **Context events fire nothing.** Hands appear in every take to set props down (D11), so not every event is a law cue. `sheet.assemble(..., target, fires)` gives `target` only to events whose cue is the take's cue; every other event has `target: null`, appears in the trace with `law: null`, and adds no clause. "Each event fires exactly one clause" is tested over targeted events.
- **Event timing.** `t` is when the cue becomes available to the creature (hand enters, prop settles, torch spot appears, breath starts, note becomes readable); `t_end` is when it ends, or `null` for a lasting state.
- **Breath needs audio; page flow is evidence.** A breath may barely move a taped page, so a breath event requires the audio burst; mean page flow inside the burst is recorded and `flow_confirmed` is true or false.
- **Quality rule at the edges.** Frame 0 is valid iff its mask is non-empty. A non-empty frame after an empty one is invalid (an infinite relative change). Exactly 50 % is still valid ("more than 50 %" fails).
- **Take cue → sheet cue.** `capture/takes.json` names take cues `glass`, `torch`, `pen`, `breath`, `note`, `hand`; the sheet's vocabulary is `water`, `light`, `pen`, `breath`, `note`, `hand`. `compile.TAKE_CUE` maps them.
- **Single acting creature.** The compiler handles one target material per take (all eight rated renders). The unrated curtain call (three targets) is out of scope here and is compiled by hand or by a later extension.

## File map

| File | Responsibility |
|---|---|
| `seam/masks.py` | `sample_frames`, prompt loading, `track` (SAM 2.1), `save_masks`/`load_masks` (bit-packed npz), `mask_digest`, `quality_ok`, `grid_overlay`/`write_grid_frames`, CLI |
| `seam/cues/sheet.py` | `CUES`, `make_event`, `assemble`, `validate_sheet`, `write_sheet`, `from_take` orchestrator, CLI |
| `seam/cues/hands.py` | `presence_intervals` (pure), `HandDetector` (MediaPipe VIDEO mode), `detect` |
| `seam/cues/props.py` | `detect(areas, centroids, fps, obj, cue)`: onset and settle from mask area |
| `seam/cues/torch.py` | `spots` (per-frame bright blob vs baseline), `detect`: persistence and glint rejection, aim |
| `seam/cues/breath.py` | `audio_features`, `bursts` (RMS + flatness), `page_flow`, `detect` |
| `seam/cues/note.py` | `ocr_words` (Apple Vision, accurate), `stable_word`, `detect` |
| `seam/laws.py` | `load_laws`, `validate_laws`, `get_law`, `UnknownLaw`, `canonical_sha256` |
| `seam/compile.py` | `TAKE_CUE`, `MODELS` adapters, `NOOP_PROMPT`, `build_prompt`, `compile_request`, `compile_noop`, `write_outputs`, sealing guard, CLI |
| `tests/test_masks.py`, `tests/test_masks_sam.py` | Masks |
| `tests/test_cues_*.py` | One per detector, plus `test_cues_sheet.py` |
| `tests/test_laws.py`, `tests/test_compile.py` | Laws and compiler |
| `tests/fixtures/laws_fixture.json` | Fictional laws (fixture only) |
| `models/MODELS.md` | Add `hand_landmarker.task` URL and SHA-256 |

## Interfaces fixed here

- **Mask prompts** `masks/prompts/<take>.json`:
  `{"take": "t01", "frame_rate": 15, "objects": {"glass": [{"frame": 30, "x": 812, "y": 401, "positive": true}, ...], ...}}`. Coordinates are pixels on the 1280×720 analysis grid; `frame` indexes the 15 fps analysis frames.
- **Mask store** `masks/<take>.npz` (`p47-masks/1`): key `meta` holds a JSON string `{schema, take, fps, n_frames, height, width, objects}`; key `obj:<name>` holds `np.packbits(mask.reshape(n, -1), axis=1)`, uint8, shape `(n, ceil(h·w/8))`.
- **Event** (inside `p47-cues/1`): `{id, t, t_end, cue, what, target, source, evidence}`; `id` is `e01`, `e02`, … in time order; `source` is `detector:<name>` or `hand`; `evidence` is a JSON object of numbers, strings and frame indices.
- **Clause trace** `<request>.trace.json` (`p47-trace/1`): `{schema, take, model, prompt_chars, clauses: [{event, t, cue, law, clause}]}`, where `law` and `clause` are `null` for context events.

---

### Task 0: records and model file

**Files:** Modify `models/MODELS.md`, `.gitignore` (`models/*.task`). Create this plan.

- [ ] Download `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task` (the versioned URL, not `latest`) to `models/`; record its SHA-256 and size in MODELS.md.
- [ ] Commit: `git add .gitignore models/MODELS.md docs/superpowers/plans/2026-10-31-b-masks-cues-compiler.md`.

### Task 1: mask store, quality rule, grid overlay, sampling (`seam/masks.py`, fast)

**Tests** (`tests/test_masks.py`):
- `test_roundtrip_bitpacked`: random bool masks for two objects, `(5, 37, 53)` (odd sizes exercise padding) → `save_masks` → `load_masks` returns identical arrays, meta fps 15, objects sorted.
- `test_store_is_packed`: the stored array for one object is uint8 with shape `(5, ceil(37·53/8))`.
- `test_digest_stable_and_sensitive`: `mask_digest` is equal for equal masks, differs when one pixel flips.
- `test_quality_rule`: areas `[100, 140, 220, 0, 50, 75, 112]` → `[True, True, False, False, False, True, True]` (140→220 is +57 %; empty; after-empty; 50→75 is exactly +50 % and valid; 75→112 is +49 %).
- `test_quality_rule_drop`: `[100, 49]` → `[True, False]`; `[100, 50]` → `[True, True]`.
- `test_quality_from_masks`: `quality_ok` accepts a `(n, h, w)` bool array as well as an area list.
- `test_load_prompts_validates`: a good prompt file loads into `{obj: [(frame, x, y, positive)]}`; a point with `x` outside the frame or a missing key raises `ValueError`.
- `test_grid_overlay`: on a 720×1280 grey frame with step 64, pixels on `x = 64k` lines differ from the input; the output keeps the shape and dtype; the input is not modified.
- `test_write_grid_frames`: writes `grid_<frame:04d>.png` files for the requested frames and returns their paths.
- `test_sample_frames`: a synthetic 30 fps, 2 s mp4 written with PyAV, each frame's brightness encoding its index, sampled at 15 fps gives 30 frames whose source indices are the even ones (±1 for codec).

**Implementation notes:**
- `quality_ok(series)`: areas `a`; valid[0] = a[0] > 0; valid[t] = a[t] > 0 and a[t-1] > 0 and |a[t] − a[t-1]| / a[t-1] ≤ 0.5.
- `sample_frames(path, fps=15, size=None)`: decode with PyAV; for k = 0, 1, … pick the first decoded frame whose pts time ≥ k/fps − half a source frame; RGB uint8; optional resize with `cv2.INTER_AREA`.
- `grid_overlay(frame, step=64)`: thin lines in a high-contrast colour (magenta) every `step` px; pixel coordinate labels on the top and left edges (`cv2.putText`, scale 0.4); every 4th line heavier.

- [ ] Write tests → run (`uv run pytest tests/test_masks.py -q`): FAIL (module missing) → implement → PASS → commit `seam/masks.py tests/test_masks.py`.

### Task 2: SAM 2.1 tracking (`seam/masks.py` `track`)

**Tests** (`tests/test_masks_sam.py`):
- `test_tracks_moving_square` (default run; ~15 s): 6 frames of 320×240, a dark 40×40 square on light grey moving 20 px right per frame; one positive point at its centre on frame 0. Every frame's mask has IoU ≥ 0.8 with the true square; the centroid moves right monotonically.
- `test_two_objects_and_late_prompt` (only with `LIMN_SLOW=1`): two squares; the second prompted on frame 3; frames before 3 are empty for it (forward-only propagation), later frames track it.

**Implementation notes:**
- `track(frames, prompts, ckpt=models/sam2.1_hiera_small.pt, config="configs/sam2.1/sam2.1_hiera_s.yaml")`: write the frames as JPEG (quality 95) to a temporary folder named `00000.jpg`…, `build_sam2_video_predictor(..., device="cpu")`, `init_state`, one `obj_id` per object in sorted order, `add_new_points_or_box` per (object, frame) with labels 1/0, `propagate_in_video` from the earliest prompt frame forward; masks are `logits > 0`; frames never reached stay empty. `torch.inference_mode()`; the temp folder is always removed.
- The CLI `python -m seam.masks track --video <analysis.mp4> --prompts masks/prompts/<take>.json --out masks/<take>.npz` and `python -m seam.masks grid --video ... --frames 0,30,60 --out masks/grid/<take>/`.

- [ ] Write tests → FAIL → implement → PASS → commit `seam/masks.py tests/test_masks_sam.py`.

### Task 3: cue sheet schema (`seam/cues/sheet.py`, the pure half)

Detectors return events made by `make_event`, so the schema comes first.

**Tests** (`tests/test_cues_sheet.py`):
- `test_make_event_fields`: `make_event(t=1.234567, t_end=None, cue="pen", what="the pen is set down", source="detector:props", evidence={"frame": 18})` has exactly the event keys, `t` rounded to 3 decimals, `target` null and no `id` yet.
- `test_assemble_sorts_and_numbers`: three events given out of order → ids `e01…e03` by `(t, cue, source)`.
- `test_assemble_targets_only_the_take_cue`: `fires="water", target="ink"` sets target on water events only; hand events stay `null`.
- `test_validate_rejects`: unknown cue, `t_end < t`, a source not `detector:<name>` or `hand`, `t` beyond the take length, and an unknown top-level key each raise `ValueError`.
- `test_write_is_deterministic`: `write_sheet` twice gives identical bytes; sorted keys, 2-space indent, trailing newline.
- `test_hand_entered_event`: an event with `source="hand"` is accepted (for entries made by hand, such as the curtain call's spoken line).

**Constants:** `CUES = ("water", "light", "pen", "breath", "note", "hand")`; `SCHEMA = "p47-cues/1"`.

- [ ] Write tests → FAIL → implement → PASS → commit.

### Task 4: hands detector (`seam/cues/hands.py`)

**Tests** (`tests/test_cues_hands.py`):
- `test_intervals_basic`: presence `[0]*5 + [1]*10 + [0]*10` at 15 fps → one interval, enter frame 5, leave frame 15.
- `test_intervals_debounce`: a 1-frame dropout inside a run does not split it; a 2-frame blip of presence (below `min_on=3`) is not an interval.
- `test_interval_open_at_end`: presence to the last frame → `t_end` null and `open_at_end` true in evidence.
- `test_detect_events`: `detect_from_presence` gives `cue="hand"`, `source="detector:hands"`, `what="a hand comes into view"`, `t = enter/fps`.
- `test_mediapipe_no_hand_on_blank` (skips if the model file is missing): `HandDetector` on 5 blank 640×360 frames reports no hand; it loads the `.task` model and runs in VIDEO mode with increasing timestamps.

No positive MediaPipe test exists: no synthetic image reliably reads as a hand, and no photo of a real hand is a fixture here. The first real take is the positive check (Aaron's contact sheet in 2.1).

- [ ] Write tests → FAIL → implement → PASS → commit `seam/cues/hands.py tests/test_cues_hands.py`.

### Task 5: props detector (`seam/cues/props.py`)

**Tests** (`tests/test_cues_props.py`):
- `test_onset_and_settle`: area 0 for 10 frames; the prop slides in over 10 frames (area and centroid changing); then still for 20 frames → one event, `cue` as given, `t` = settle frame / fps (± 1 frame), `evidence.onset_frame` = 10.
- `test_never_settles`: a prop that keeps moving → no event (`settle` needs `settle_frames=5` frames with area change ≤ 5 % and centroid motion ≤ 3 px per frame).
- `test_hand_occlusion_dip`: a brief area dip while settled does not create a second event.
- `test_from_masks`: `areas_centroids(mask_stack)` gives the area and centroid series used above.

`what` is `"the {obj} is set down"`.

- [ ] Write tests → FAIL → implement → PASS → commit.

### Task 6: torch detector (`seam/cues/torch.py`)

**Tests** (`tests/test_cues_torch.py`), frames 180×320 grey (luma 90):
- `test_moving_beam_detected`: a soft bright disk (radius 30, +120 luma) appears at frame 10 and drifts 4 px per frame for 20 frames → one `light` event with `t` = 10/15, `t_end` = 30/15, `evidence.aim` = the centroid at onset (± 3 px), `evidence.path` subsampled.
- `test_short_glint_rejected`: a 3×3 saturated spot for 2 frames → no event.
- `test_static_glint_rejected`: a 4×4 saturated spot, still, for 25 frames → no event (small and stationary: the signature of a metal edge catching the beam).
- `test_beam_with_glint`: the moving beam plus a static glint elsewhere → one event whose aim follows the beam.
- `test_lands_on_home`: with `homes={"ink": (x, y, w, h)}` covering the beam's onset point, `evidence.lands_on` is `"ink"`.

**Implementation notes:** baseline = per-pixel median of the first `baseline_frames=5` frames (luma, Gaussian-blurred σ 2); a frame's spot = the largest connected component of `(Y − base > 40) & (Y > 150)`; tracks are runs of frames with a spot; a run is the torch if it lasts ≥ `min_on=5` frames and is not a glint, where a glint has median area < `glint_area=150` px **and** total centroid travel < `min_travel=12` px. The handheld beam both covers more area and moves; a metal prop's glint does neither.

- [ ] Write tests → FAIL → implement → PASS → commit.

### Task 7: breath detector (`seam/cues/breath.py`)

**Tests** (`tests/test_cues_breath.py`), 48 kHz mono WAV written with SciPy:
- `test_noise_burst_detected`: low noise floor (−60 dBFS) with a 0.8 s white-noise burst at −20 dBFS starting at 3.0 s → one `breath` event, `t` within 0.05 s of 3.0, `t_end` within 0.1 s of 3.8.
- `test_tone_rejected`: a 0.8 s 440 Hz sine at the same level → no event (spectral flatness is low).
- `test_short_click_rejected`: a 40 ms noise click → no event (`min_dur=0.15` s).
- `test_page_flow_confirms`: frames whose page texture shifts 2 px per frame during the burst → `evidence.flow_confirmed` true and `flow_peak` > 0.5; static frames → false.
- `test_stereo_input`: a stereo file is mixed to mono.

**Implementation notes:** frames of 2048 samples, hop 512, Hann window; RMS in dBFS; flatness = geometric / arithmetic mean of the power spectrum (300 Hz–8 kHz); a frame is breath-like if RMS > noise floor (10th percentile) + 15 dB and flatness > 0.25; runs merged across gaps < 0.1 s; runs ≥ 0.15 s are bursts. Page flow: Farnebäck flow on the analysis frames within the page box, mean magnitude per frame pair.

- [ ] Write tests → FAIL → implement → PASS → commit.

### Task 8: note detector (`seam/cues/note.py`)

**Tests** (`tests/test_cues_note.py`):
- `test_ocr_rendered_word` (macOS only): PIL renders `BELL` in Helvetica 120 px, black on white, 800×300 → `ocr_words` returns a word whose upper-cased text is `BELL`, with confidence > 0.3 and a box in pixel coordinates inside the image.
- `test_ocr_blank`: a blank image → `[]`.
- `test_stable_word`: per-frame reads `[None, None, "BELL", "BELL", "BELL", "BELL"]` with `min_reads=3` → first stable index 2; `[..., "BELL", "BEL", "BELL"]` is not stable.
- `test_detect_on_frames` (macOS only): 6 blank frames then 6 frames with the word → one `note` event at the first stable sample, `what` = `a note reading "BELL" is set down`, `evidence.word = "BELL"`.

**Implementation notes:** encode the RGB array to PNG bytes (OpenCV), wrap as `NSData`, `VNImageRequestHandler.alloc().initWithData_options_`, `VNRecognizeTextRequest` with `VNRequestTextRecognitionLevelAccurate` and language correction on; revision 3 reads handwriting. Boxes convert from Vision's normalised bottom-left origin to pixels. `detect` OCRs every `every=3`rd frame inside an optional `box`.

- [ ] Write tests → FAIL → implement → PASS → commit.

### Task 9: take orchestrator (`seam/cues/sheet.py` `from_take`)

**Tests** (add to `tests/test_cues_sheet.py`):
- `test_from_take_synthetic`: a synthetic 4 s take (15 fps frames, a mask store with a `pen` object that slides in and settles, a WAV with no burst), `fires="pen"`, `target="ink"`, the hand detector replaced by a stub presence list (`hands_presence=` parameter) → a valid sheet with one targeted pen event, one untargeted hand event, and the right `fps`, `n_frames` and `size`.
- `test_cli_writes_sheet`: `python -m seam.cues.sheet` on the same inputs writes `cues/<take>.json` that `validate_sheet` accepts.

`from_take(take, frames, fps, masks=None, objects={obj: cue}, wav=None, page_box=None, note_box=None, homes=None, fires, target, hands_presence=None, detectors=(...))` runs the enabled detectors and calls `assemble`.

- [ ] Write tests → FAIL → implement → PASS → commit.

### Task 10: laws (`seam/laws.py`)

**Fixture** `tests/fixtures/laws_fixture.json`: salt `"fixture-not-a-real-salt"`; materials ink, gold and paper with fixture looks; four fictional laws, e.g. `ink.pen` → "spins on the spot like a top (fixture)", `ink.hand` → "stands on its head (fixture)", `gold.water` → "juggles three dots (fixture)", `paper.breath` with `touches: null`; decoys `"Decoy A (fixture)"`, `"Decoy B (fixture)"`.

**Tests** (`tests/test_laws.py`):
- `test_loads_fixture`: loads; `get_law(laws, "ink.pen")["clause"]` is the fixture clause.
- `test_unknown_law_errors`: `get_law(laws, "gold.light")` raises `UnknownLaw` (a `KeyError` subclass) naming the id.
- `test_rejects_felt`: a law with material `felt` (and `felt` in materials) fails: materials must be ink, gold or paper.
- `test_rejects`: an id that is not `<material>.<cue>`, an unknown cue (`bell`), a duplicate id, a missing salt, an extra key, a decoy equal to a law label, and decoys not exactly two each raise `ValueError`.
- `test_canonical_sha256`: stable across key order.

- [ ] Write tests → FAIL → implement → PASS → commit.

### Task 11: compiler core (`seam/compile.py`)

**Take spec:** a `capture/takes.json` entry (`id`, `cue`, `target_material`, `target_position`, `touched_object`) plus the page layout `{material: position}` (from the take list's three-target entry) and the input paths.

**Prompt template (fixed; every line in order):**
1. `Keep the camera, framing, timing, desk, page and every object and hand exactly as filmed.`
2. `The drawing {position phrase}, the {material} one, comes to life and steps off the page onto the desk.`
3. One style lock per material on the page, in page order: `The {material} drawing stays {look}.`
4. For each resting drawing: `The {material} drawing {position phrase} stays still on the page.`
5. For each targeted event in time order: `At {t:.1f} s, when {what}, it {clause}.`
6. Adapters that send a reference add: `It keeps the exact look of the drawing in the reference image.`

Position phrases: `left` → "on the left of the page", `centre` → "in the centre of the page", `right` → "on the right of the page". The no-op prompt is exactly `Change nothing. Keep every object, hand and line exactly as filmed.`

**Tests** (`tests/test_compile.py`, using the fixture laws and a synthetic sheet):
- `test_aleph2_over_1000_is_hard_failure`: a sheet whose `what` texts push the prompt past 1,000 UTF-16 units raises `CompileError` mentioning 1000 (no truncation).
- `test_each_event_fires_one_clause_in_time_order`: three targeted events given out of order → the trace has one clause per targeted event, sorted by `t`, each clause string appearing exactly once in the prompt, in that order.
- `test_context_events_fire_nothing`: an untargeted hand event appears in the trace with `law: null` and adds no `At … s` line.
- `test_style_lock_per_material`: each of ink, gold and paper has exactly one `The {m} drawing stays {look}.` line.
- `test_target_named_by_position`: the prompt contains "The drawing on the left of the page, the ink one"; a `centre` target uses "in the centre of the page".
- `test_unknown_law_is_error`: a targeted event whose cell has no law raises `UnknownLaw`.
- `test_noop_is_fixed_template`: `compile_noop` prompt equals the constant; no clauses; `meta.purpose == "noop"`.
- `test_byte_identical`: compiling twice and writing gives identical request and trace bytes.
- `test_take_cue_mapping`: take cue `glass` fires `water` events; `torch` fires `light`.

- [ ] Write tests → FAIL → implement → PASS → commit.

### Task 12: model adapters, estimate validation, sealing guard, CLI

**Adapters** (`compile.MODELS`), per R0.5:

| Model | seed | options | references | prompt limit |
|---|---|---|---|---|
| `aleph2` | 1 | none | never (the API has none) | 1,000 |
| `kling_4` | none (first output) | `ratio: auto_720p` | the target's scan crop | 26,000 |
| `seedance2_5` | 1 | `mode: edit`, `audio: false` | the scan crop | 15,000 |
| `gemini_omni_flash_1.1` | none | `mode: edit`, `ratio: "640:360"` | the scan crop | 4,000 |

**Tests** (add to `tests/test_compile.py`):
- `test_adapter_shapes`: per model, the request has exactly the table's seed, options and references; aleph2 has no references and no reference sentence.
- `test_requests_pass_hub_estimate` (skips if the hub client is absent, e.g. in the public repo): a synthetic 10 s 1280×720 mp4 and a small PNG crop; each of the four compiled requests and the no-op request run through `env -u RUNWAY_API_KEY python3 <hub>/tools/runway/runway_gen.py estimate <file>`; exit 0, JSON with `estimate_credits > 0` and the right model; no warnings for any model.
- `test_sealed_guard`: compiling from a laws file under a `sealed/` folder and writing outside `sealed/` raises `CompileError`; writing under `sealed/requests/` works.
- `test_cli`: `python -m seam.compile --sheet … --laws … --takes … --take t01 --material ink --model aleph2 --video … --out …` writes the request and `.trace.json`.

- [ ] Write tests → FAIL → implement → PASS → commit.

### Task 13: sealed files and records (no sealed content committed)

- [ ] Write `sealed/laws.json` (`p47-laws/1`) from `sealed/laws-gate-L.md` with a random salt (`secrets.token_hex(16)`); validate with `seam.laws.load_laws`.
- [ ] Draft the other 10 cells in `sealed/laws-draft-18.md`, marked "for Aaron's approval before Gate R".
- [ ] Compile a dry run of the real requests into `sealed/requests/` against a synthetic mp4 and run `estimate` on each (checks the real clauses stay under aleph2's 1,000).
- [ ] `git status` shows nothing in `sealed/`; LOG.md entry; the hub calls file; commit `LOG.md` only.

## Self-review

- **Spec coverage.** 2.1: Tasks 1–2 (point prompts, SAM 2.1 CPU, bit-packed npz at 15 fps, quality rule, grid frames; moving square; round trip). 2.2: Tasks 3–9 (all five detectors and the sheet in `p47-cues/1`, `source` on every event). 2.4: Tasks 10–12 (every listed compiler test, adapters for four models, hub `estimate`). Sealing: rules 1–2 and Task 13. The vision-model log (2.3) is not in this sub-plan: `vlm_log` stays `[]`.
- **Placeholder scan.** This plan fixes tests by name and assertion, signatures, constants and algorithms; the code itself is in each task's commit, which is the canonical record (a deliberate departure from writing every line twice).
- **Names.** `make_event`, `assemble`, `validate_sheet`, `write_sheet`, `from_take`; `load_laws`, `get_law`, `UnknownLaw`; `compile_request`, `compile_noop`, `CompileError`, `NOOP_PROMPT`, `MODELS`, `TAKE_CUE` are used consistently across Tasks 3–12.
