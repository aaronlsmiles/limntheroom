# Limn the Room — process log
Newest first. A "call" or "hub call" is a numbered decision in the studio's private calls file; each one that shaped the study is summarised here, without the laws.
The registered outputs in `runs/registration/` record the local interpreter path they ran under (a home folder on the machine that ran them); it is not a secret, and registered outputs are never hand-edited.

## 10 Nov 2026 (evening, later): the database, the live check and addendum A2 (hub call 145)

- **Aaron chose option (c):** the controller applies the schema through the database provider's management interface, under his own login. The kit's v0.2.0 `sql/schema.sql` was applied unchanged (sha256 `0bc600d8…`), and `blindpanel` was added to the exposed schemas, alongside the ones already there.
  - Checked: no rows; the caps at 500 a day and 20,000 in all; insert and select only for the server's key; nothing for the public roles; row-level security forced.
- **The live check (§17), on a throwaway study id** built from the same sealed key and copies, in a scratch folder (the real build untouched). One session went in exactly as a browser sends it:
  - stored, and a repeat of it refused;
  - the kit's `export` from the live database holds Q2 options 7 and 9 on the clips and 12 on the baseline, with their labels;
  - the database's own tally keeps options above 5.
  - Then the throwaway's row was deleted and its study taken off the host. The submissions table is empty.
- **Addendum A2, before any invitation:** 49 rows added to `MANIFEST.sha256` (419 in all, every row OK):
  - the build inputs and the sealed rating manifest;
  - the three rating copies and three ringed stills;
  - for each of the five studies: its `study.yaml`, lock, banned-terms file and built `study.json`, `reveal.json` and `index.html`;
  - the host code and the vendored kit (`npm pack` of blindpanel `v0.2.0`).
- The CLI used is `bin/blindpanel.mjs` of the blindpanel `v0.2.0` checkout (`dd45f85`), sha256 `ad7e4a393aed6914c6287af7af409ef009812778ad7a26b4ddd2db9e655c8aa0`.
- **Next:** Aaron's raters and invitations (Gate RT), with the failure path's invitation (D3). The window is 7 days from the first invitation.

## 10 Nov 2026 (evening): the study host (hub call 144)

- **Aaron:** "Go with your recommendation now." The study is hosted at a neutral address on the personal Vercel team. Raters must not reach the studio's site, so no studio or project word is in the address, the pages, the headers or the staged files. The address stays out of every public file until the window closes, because this repository is indexed and links to the studio.
- **The pages** are the five verified builds, byte for byte (`rating/host/stage.sh` copies them, re-runs the kit's `verify` on each and refuses project words). Each rater's study lives in its own folder.
- **Submissions.** One function passes each session to its own study's handler, the kit's `createSubmitHandler`, unchanged. The allowed origin comes from the environment. Tests for the routing, the refusals and the keep-warm were written first (5 pass).
  - The daily keep-warm stops the free database from pausing during the window.
  - `noindex` everywhere, a robots file that disallows all, and no referrer.
- **The database:** the kit's Supabase store, in its own `blindpanel` schema (the kit's v0.2.0 SQL, unchanged) on a studio database that a shipped page does not use. The StillDrawn explorer's database, which runs blindpanel 0.1, is untouched.
- **Checked live:**
  - the pages return 200 with `noindex`, and a clip's bytes equal the built copy's;
  - the API refuses an unknown study, a foreign origin and an unauthorised keep-warm.
- **Waiting:** the schema needs Aaron's confirmation (the database connector asks a person to confirm its `revoke` and `drop trigger` statements). Then the live check on a throwaway id, addendum A2 (hashes only) and Gate RT.

## 10 Nov 2026 (afternoon): deviation D3, the failure path's three-item rating study (hub call 143)

- **Aaron (call 143):** "Deviation D3: agree with your recommendation."
- **Why it was needed:** §19 says the failure path's glass ×3 are "rated as registered", but the registered build refused a study without all eight rated renders, and the registered invitation promises eight pictures.
- **What changed (§24, D3), built test-first; the new tests failed before the code existed:**
  - `rating/prepare.py build --failure-path`: the glass take ×3 only, with their sealed codes. Inputs holding anything else or less are refused, and the whole sealed key is still checked against all eight rated rows. Nothing else in the build changes.
  - `analysis/ratings.py --study`: the key is restricted to the study's items. The session rule then counts a session complete when it answers the three, and the five laws with no item are listed as not in the study. The registered run, without `--study`, is reported first, beside it (§23).
  - A new human record, `agents/briefs/human-rater-study-failure-path.md`: version 1 word for word, except "three" for "eight" (four places) and "about 5 minutes" for "about 15". Version 1 is not edited. Tests hold the new record to version 1 and to the invite quoted in D3.
- **Not changed, disclosed:** `build` on the command line still demands `--seconds` or `--frames`, though §17 registers the length "with no length given". The study is built as the registered test does it (parse a placeholder, clear it), so the registered rule applies. The three re-renders are 12.708 s, so the copies are their first 12.0 s (288 frames at 24 fps).
- **Suite:** 771 passed, 13 skipped. The 13 need the blindpanel CLI; run against a fresh checkout at tag `v0.2.0` (`dd45f85`, built from its lockfile), all 49 rating-build tests pass. Manifest addendum D3: 370 rows, all OK.
- **Study ids:** the build uses the neutral prefix `rs` (`rs-r1` … `rs-r5`), not the default `limn`, so no rater's link carries a word of the project's name. The prefix is a build option, not a registered value.
- **D3 pushed publicly first** (`4bd2ca4`), then the study was built locally (`rating/inputs-failure-path.json`; the three §16 re-renders; stills from `takes/t01f.analysis.mp4` at each material's cue-sheet time, 3.6 s):
  - five studies, three items each, validated, locked, built and verified by blindpanel v0.2.0, plus the builder's own checks (tally off, codes-only reveal, code-named media);
  - copies 288 frames each (H.264, 1280×720);
  - the sealed key unchanged (`a65f7f13…`); each ring on its own creature (checked by eye on the three stills).
  - A throwaway session through the kit's `export` scores in both analyses: the registered run reports eight laws (five with n = 0), the D3 run the three glass laws, with the other five listed as not in the study. Nothing is deployed.
- **Open before Gate RT:** the remote host (plan 9.1), its live check and addendum A2. The live database named in STATUS is the StillDrawn explorer's, which a shipped page uses.

## 10 Nov 2026 (morning, later): Gate K, the failure write-up; the glass take ×3 on seedance2_5 (hub calls 141–142)

- **Aaron at Gate K:** the failure write-up (§19), not a stop.
- **Deviation D2:** the registration does not name the failure path's model, so it is filled with seedance2_5, the registered draft model, using its three glass requests as hashed at Gate R (§24). Pushed before rendering (`a9f590c`).
- **First renders:** 552 credits each, 12.708 s each against the take's 12.767 s.

| Render | Lag | Frames that pass | Gate |
|---|---|---|---|
| t01-gold | 0 | 99.5 % | fails on duration only: the last analysis frame is missing |
| t01-paper | 0 | 99.5 % | fails on duration only |
| t01-ink | 0 | 21.9 % (from frame 0, before anything moves; scale within 1 ± 0.003) | fails: frames and duration |

- **Reading:** seedance kept the gold and paper renders aligned in every frame they have, and returned every clip about 0.06 s short of its input, as in the probe. In the ink render it re-synthesised the desk enough to move the residuals past ρ (1.0 px) from the first frame.
- **By §16**, a render that fails the gate or comes back short is re-rendered once, always, with seed 2, and the re-render replaces the first whatever its outcome. The three seed-2 requests (the registered ones, seed changed) were hashed in a dated addendum and pushed before sending. The registry's row was updated: its registered state is still a byte prefix.

- **The re-renders (§16, seed 2; 552 credits each, 12.708 s each)**, which replace the first renders for the study whatever their outcome:

| Render (re-render) | Lag | Frames that pass | Gate |
|---|---|---|---|
| t01-gold | 0 | 99.5 % | fails on duration only (the last frame is missing, as before) |
| t01-ink | 0 | 0 % | fails |
| t01-paper | **5** | 0 % | fails |

- **No glass render passes the registered gate.** H was never testable on three renders, and none is measured. The study's renders for rating are the three re-renders.
- **Spend:** 4,459 credits (about £35): probe 851, keyframes 16, rescue 280, glass ×3 1,656, re-renders 1,656.
- **Next, for Aaron:**
  - The rating study, as §19 registers it, rates these three. `rating/prepare.py` refuses a study without all eight registered items, so building it needs a code change (deviation D3, proposed, not made).
  - The raters and their invitations (Gate RT).
  - A display-only seam view, labelled "not aligned, not measured".

## 10 Nov 2026 (morning): deviation D1 and the keyframe rescue; the study is at Gate K (hub calls 139–140)

- **Deviation D1 (Aaron: "A", call 139).**
  - A sixth rater round, `rescue`, with the probe's brief, agent and rubric. Built test-first; full suite 757 passed, 13 skipped.
  - Entered in PREREGISTRATION §24 with its diff and what had been seen.
  - Manifest addendum D1, which also rows the append-only registry: its registered state is a byte prefix of the current file.
  - Pushed to the public repo (`18f680e`) before the rescue.
- **The rescue, run as registered in §14.**
  - Keyframes at 4.1 s and 4.6 s (the cue at 3.6 s + 0.5 and + 1.0): two gen4_image stills, each from the take's frame with the ink crop as reference and the fixed law-free prompt, 16 credits.
  - The request is the probe's aleph2 request, prompt unchanged, plus the two timed keyframes. It, the keyframes and their source frames were hashed in a dated addendum and pushed (`6f634f7`) before the call.
  - aleph2, seed 1: 280 credits.
- **The keyframes:** gen4_image re-composed the scene (the page larger and shifted, the camera framing moved). aleph2 was asked to meet those frames at 4.1 s and 4.6 s.
- **The result:**
  - Rubric 1 yes, rubric 2 yes: a reaction named, to the glass. The blind rater's round `rescue` was valid on the first attempt.
  - Rubric 3 **fails**, narrowly: lag −2 analysis frames (the gate allows ±1), and 89.3 % of frames pass (the rule needs 90 %); ρ 1.0.
- **§14: the rescue does not pass rubrics 1 and 3, so the study goes to Gate K (§19).** At Gate K Aaron chooses between stopping and the failure write-up: the glass take ×3 rendered for the seam view, rated as registered, and written up.
- **What the probe and the rescue show together:**
  - The one model that kept the room's timing exactly (aleph2, no keyframes) did not bring the drawing to life.
  - Every render that did bring it to life and react to the right cue drifted just outside the registered timing gate: seedance2_5 came back 0.29 s short, and aleph2 with keyframes lagged two frames with 89 % of frames aligned.
- **Spend: 1,147 credits** (probe 851, keyframes 16, rescue 280), about £9 of the £50 target.

## 10 Nov 2026 (early morning): the probe (Gate P1), and a gap in the rescue (hub call 138)

After Gate R and the completed archive visit. Four arms on the glass take's first 10 s, ink acting. Spend: 851 credits (the probe budget was 926), the first rows of `runs/runway-calls.jsonl`.

| Arm | Output | Gate (§6, span 0–10 s) | Rubric 1 (comes to life, out of its place) | Rubric 2 (names a reaction) |
|---|---|---|---|---|
| aleph2 | 1920×1080, 10.0 s, 280 credits | **pass** (ρ 1.0, lag 0, every frame) | no | no |
| kling_4 | 1280×720, **4.04 s**, 151 credits | fail (duration, lag, frames) | can't tell | no |
| seedance2_5 | 1280×720, **9.71 s**, 420 credits | fail (duration only; 97 % of frames pass, lag −1) | **yes** | **yes** (reacted to the glass) |
| gemini_omni_flash_1.1 | refused by the API, nothing billed: `ratio` is accepted only in reference mode, and the registered arm sends 640:360 in edit mode | — | — | — |

- **The rater:** one blind round (`probe`), valid on the first attempt. Only the pass counts and the cue are reported here, never a label.
- **The gemini arm counts as failing** (§14, call 136): a re-run of the identical request would be refused the same way, so no deviation was made.
- **§14's decisions:** no arm qualifies as the final model (aleph2 fails rubric 1; seedance fails the gate). The draft model is seedance2_5, the only arm that passes rubrics 1 and 2. So the registered keyframe rescue is next.
- **Stopped: the rescue has no rater round.** §14 asks the rescue to pass rubric 1, which the blind rater answers. The code's rounds are a fixed set (`probe`, `draft-1`, `draft-2`, `study-baseline`, `study-clips`), and the probe round is closed. Adding a round is a change to registered code after outputs have been seen, so under §23 it is a deviation for Aaron. Nothing further was generated.
- **Findings, whatever comes next:**
  - The arm that kept the room exactly did not bring the drawing to life.
  - The arm that brought it to life, reacting to the right cue, returned a slightly short clip, which the registered gate fails on duration.
  - kling_4 returned 4 s from a 10 s input.

## 10 Nov 2026 (night, later): the independent gate review, and its fixes (hub call 136)

A fresh referee (the gate-reviewer agent) read the registration, the code and the calls independently of this session. Verdict: **accept with changes**: no blocks; six fixes before the freeze; four notes. All were taken, each checked against the code first. Built test-first.
- **F1.** The claim that the sealed contact tags name the §4 objects was true for six of seven by word, and nothing checked it. The torch take's tag names the standing object in other words. *Fix:* `tests/test_sealed_tags.py` maps every tag to its take's `touched_object` through a sealed one-entry alias table (`sealed/tag-aliases.json`, salted and hashed in §18). The test names cell ids only, and the public text says what it does.
- **F2.** The session rule was registered in §17 but not built: `analysis/ratings.py` still refused a multi-session export. *Fix:* `read_sessions` and `choose_session` take the first session that answers every item, else the first session, and the output records the choice.
- **F3.** H could be carried by drift that grows over the clip with contact coming late. *Fix:* two registered secondaries in `h_contact.py`: a time-matched r (contact against eligible non-contact frames within 2 s, with the shift null within those frames) and the descriptive slope of D over time. A synthetic pure trend clears the r floor on the primary but not on the time-matched r.
- **F4.** The success criteria were cited but not in the registration. *Fix:* §1 carries them, and STATUS's stale lines are fixed.
- **F5.** `prepare.py` defaulted to a removed checkout path. *Fix:* the CLI comes only from `--blindpanel` or `BLINDPANEL_CLI` (the repository at tag v0.2.0).
- **F6.** The seedance branch's cost was stale: its worst case is about 10,180 credits (about £80), over the £60 go. *Fix:* §20 says so, and that branch needs a fresh go before Gate F.
- **Notes:**
  - in-person raters use a separate macOS account;
  - a model retired mid-run means the remaining renders are reported missing, with no switch;
  - the draft window is computed from the cue sheet (`compile.py --draft-window`);
  - local paths are gone from the public text;
  - this LOG says what a "call" is.
- **Also registered** (Aaron, 10 Nov): renders and seam views may go on the studio's website before the rating window. The raters are never told of it.
- **Second round of the gate review** (on the revised file): accept with changes, no blocks; all six first-round fixes verified in code. Taken: the alias file is in the manifest; a rater round or probe arm that fails has a registered outcome (§14, §15, §17); STATUS's stale lines rewritten; nothing published before close names a law, a label or a Q2 option (§2); the t01 triple disclosed under §1's status; the exact take seconds (103.5 s). Suite on the tree of `19f1158`: 756 passed, 13 skipped.


Phase 4.2 of the plan: a fresh agent (Opus, xhigh) read the draft registration against the code, the measured values and the calls, looking for leaks, forking paths, double readings and stale facts. It found seven items it rated as blocking, seven to fix and a set of notes. Aaron gave his go in advance to decide each one on its merits and record the reasoning ("go with your recommendations"). Each decision is below, with its reason. Built test-first. Full suite: 746 passed, 13 skipped; HEAD and `~/.blind` were unchanged by the run.

1. **Public text narrowed one law.** The torch take's set-up wording and object names, read together, hinted at what the creature might do.
   - *Decision:* neutral wording in `capture/PROTOCOL.md`, `capture/takes.json`, §4 and this LOG; the making guide (`creature/template/`) stays out of the public tree with the media.
   - *Decision:* each take's touched object stays public by design (§2).
   - *Why:* H is registered on the touched objects, so they cannot be sealed without hiding the test. Every clip shows them anyway, and the raters are recruited cold and never pointed to the registration.
2. **Trimmed inputs could never pass the gate.** The gate demanded the take's whole span, so the 10 s probe arms and the 10 s no-op failed on duration by construction.
   - *Decision:* a render from a trimmed input is gated against the same span of the take, taken from the request's recorded trim (`align.py gate --start --seconds`).
   - *Decision:* new `render_pair.py noop`, which writes the no-op pair with R_noop ∩ cover, valid = the gate's ok; `null` takes the same span.
   - *Why:* this is the only reading under which the registered probe and κ_keep work at all. The span is fixed by the compiler before anything is rendered, so it leaves no choice.
3. **The probe and draft question asked whether the figure leaves the page.** Calls 108 and 110 put the props on the page and made every prompt say the creature "comes to life and steps up out of its place on the page".
   - *Decision:* the question is now "Does a drawn figure come to life and move out of its place on the page?" (key `leaves_place`), in the brief, §1, §14, §15 and §19.
   - *Why:* the old wording would answer No for a faithful render and send the study to Gate K by construction. The new one is the prompt's own first step, matches the prompt-frame rule ("clear of its home"), and names no behaviour.
4. **The mask-quality text disagreed with the code.** *Decision:* §7 now states the code's rule, built 3 Nov: the prompt frame and every earlier frame pass, A(t) = dilate(home, m), and the creature mask is empty, so it makes no contact.
   - *Why:* the creature is its drawing at home then. Counting the home as the creature for contact would score resting frames as touches (the t02 home sits about 19 px from its object).
5. **The picker's stride overflowed the payload guard.** Stills at every 2nd frame came to 18.8–20.1 MB on the terrazzo takes, over the 16 MB guard.
   - *Decision:* every 3rd frame (12.5–13.5 MB); a larger stride (4–6) only if a render's folder would not fit, decided from the video before any attempt (`frame_pick.choose_stride`).
   - *Why:* it is the smallest stride with headroom on every take. A pick can be at most two frames late, and those frames count as at home, which works against H, not for it.
6. **The re-render rule had two readings.** *Decision:* a technical failure triggers exactly one re-render, which replaces the first for the study and for H whatever its outcome.
   - *Why:* "allowed" left the analyst to choose after seeing the render.
7. **The rating side had choices left to people who know the laws.** Decisions:
   - the first session that answers every item counts (else the first session);
   - the rating copies are the first 12.0 s of each render, or all are cut to the shortest render (`prepare.py` with no length given);
   - a Q2 order that lists the rated labels in the Q1 order is redrawn from the next derived seed;
   - `rating/` is in the frozen code;
   - late sessions are not analysed;
   - with fewer than three raters, everything is still reported and success criterion 2 is marked not met.
   - *Why:* each rule removes a decision that would otherwise be made after seeing renders or ratings.
8. **The H inputs were free command-line choices.** *Decision:* `h_contact.py` accepts only the eight registered render ids (refusing the curtain call by name) and lists every missing render as not testable. `assemble.py` reads the touched object and the hand from `takes.json`, and refuses a home or an extra-record name that is not registered.
9. **The secondaries' text promised more than the code did.** *Decision:*
   - the redrawn share, hand drift and note error rate are labelled descriptive (as coded);
   - "interior" is defined as the touched object's take mask, and its pair is built (`render_pair.py render --exclude-touched`).
   - *Why:* refraction inside the glass could inflate drift at contact, so that check matters for H; the others never had a test.
10. **Stale facts:** 4K takes of 12.6–13.7 s; the finals at full length (aleph2 keeps the input's length); the budget repriced (finals 2,903 credits; worst case about 7,510, about £59, inside Aaron's £60 worst-case go); the glass is a ramekin.
11. **The rating ring missed the creatures.** *Decision:* each rated row's `ring_bbox` is its own home mask's box plus 4 px; a missing box refuses the build, and a test ties the boxes to the masks.
12. **The frozen environment was not enforced.** *Decision:* the lines job pins StillDrawn's `metrics/inkstab.py` and `metrics/masked.py` by SHA-256 (not by commit, since the public tree is regenerated) and the ComfyUI venv's versions, and refuses on any difference. §3's versions are filled in.
13. **The squashed public history dropped the ledgers' commit trail.** *Decision:* the private head commit at registration, which fixes every ledger commit, is recorded with the tag, and the full private history is published as a bundle at close. Tracked media stay out of the public tree (ruling of 3 Nov).
14. **The rescue keyframes were unregistered.** *Decision:* a fixed, law-free recipe: two gen4_image keyframes at the cue + 0.5 s and + 1.0 s, "the drawing has come to life and stands up in its place", with no behaviour or clause.
    - *Why:* keyframes written by the controller, who knows the laws, after seeing failed probes would be the clearest forking path in the study.
- **Notes taken:**
  - placement wording (4.0–5.0 px); "seven renders with a touched object"; the m-threshold range at m = 32;
  - the sampler described as coded; hand drift None on unscored frames; a failed pick or point means not testable;
  - a second draft round's recompiled requests go into a manifest addendum; gemini's 640×360 noted;
  - the leak guard now also checks the unrated cells, the decoys and the sealed tags (58 needles, none found);
  - the t01–t04 paste inputs were rebuilt so every result records its cue and placement frames (the arrays are identical).
- **Draft window fixed:** a draft's 4 s window starts 1.0 s before the firing event (not before 0 s), so the window is not chosen per draft.

## 10 Nov 2026 (later): call 133's three rulings accepted and built (hub call 134)

Aaron: "accept all recommended rulings". Built test-first: 9 new tests, all failing first for the missing feature. Full suite 660 passed, 12 skipped; HEAD and `~/.blind` were unchanged by the run. Local compute only; no renders, no paid calls.

- **Ruling 1, the paste placement** (`seam/controls_inputs.py`).
  - `placement_frame(track, i0)` returns the cue frame, or the first frame at or after it on which the touched object is tracked. It refuses an object never tracked from the cue on.
  - `build_paste` places against that frame; the window still starts at the cue. `cue_frame` and `placement_frame` are recorded in the placement info.
  - t05's and t06's inputs, rebuilt by the tool, equal the provisional ones array for array (cue frame 51 against placement frame 54, and 41 against 48).
  - Rerun through the paste control at both resolutions, every threshold, pass fraction and count matches the provisional results. The results no longer carry the provisional flag.
  - The other six place at their cue frame, so their inputs are unchanged. The provisional files are in `media/reshoot-2026-11-09/controls/provisional-results/` and `cache/controls/provisional/`.
- **Ruling 3, the glass take's own sheets.**
  - `cues/t01-gold.json` and `cues/t01-paper.json` were written by the registered command with `--target gold` and `--target paper`. They are byte-identical to the cache copies the paste windows used.
  - `controls_inputs.sheet_path` defaults to `cues/<take>-<material>.json` when it exists.
- **Ruling 2, the shift failure.**
  - The rule stands; the failure is reported.
  - New and descriptive: `controls.move_frames` moves the whole take by (3, 3) and marks the strip with no source as uncovered. `controls.room_shift_share` classes every room cell of the moved take against the take under R0 at κ. `lines_job.py shift-room` runs it on the shift input, and the moved maps are cached, so the second κ costs no extraction. Results: `<render>.shiftroom720.json` and `.shiftroom1080.json`.

    | | Redrawn | No verdict | Kept |
    |---|---|---|---|
    | 720p (κ 0.8611) | 69.6–73.8 % | 26.2–30.3 % | 0–0.12 % (t02) |
    | 1080p (κ 0.7539) | 50.8–53.0 % | 47.0–48.4 % | 0–1.46 % (t02) |

    About 102,000–107,000 room cells a render.
  - The wording proposed in call 133 said a moved cell "never" reads kept. That is wrong at 1080p, and on t02 at 720p, so the label says "almost never".
- **PREREGISTRATION.**
  - §4: the gold and paper sheets.
  - §6: ρ.
  - §9: the D0 floors per render, and κ_codec.
  - §10: the placement reading, m = 32 at both resolutions, the shift results, the room share and the label: "On the textured desk, a 3 px move shows as redrawn in about 70 % of room cells at 720p and about half at 1080p. Elsewhere, in the densest texture, it shows as no verdict, and almost never as kept."
  - §25: call 133 in the rulings list.
  - Still blank for Gate R: the lag-energy floor's confirmation, the dates, commits, versions and hashes, the sealed files and the testable count.

## 10 Nov 2026 (early): codec nulls, m and the controls on the terrazzo keepers (hub call 133)

Local compute only (repo venv for the inputs, the ComfyUI venv lines job on MPS); no renders, no paid calls. Results in `runs/registration/`; drivers, previews and diagnostics in `media/reshoot-2026-11-09/controls/` (gitignored: they show the take). StillDrawn `62ec261`, `metrics/` clean.

- **Paste control** (§10; `controls_inputs.py paste` → `lines_job.py paste-control`, aleph2 → `<render>.paste1080.json`, kling_4 → `.paste720.json`). Crops are scaled to each home's area (0.105–0.106) and placed 4–5 px from the touched object at the cue frame, on the line to the home. t04's crop sits 4 px below the page. Placement previews: `controls/paste/`.
  - **Every render passes every margin on every scored frame, at both resolutions** (135–164 frames a render; pass fraction 1.000 at m = 32, 48 and 64). The null's 95th percentile (the threshold) is 0.030–0.056 px at 720p and 0.065–0.083 px at 1080p.
  - **So m(720p) = m(1080p) = 32**, the smallest margin, voted by the seven touched renders. The breath render (t04-ink) passes too and does not vote.
- **Two takes needed a reading (provisional; for Aaron, call 133).** On t05 and t06 the touched object's take mask is empty at the cue frame, so `build_paste` refused. SAM tracks forward from the blind placer's prompt frame only:
  - t05: the note is read at 3.4 s (frame 51) but tracked from 3.6 s (frame 54);
  - t06: the hand comes in at 2.733 s (frame 41) but is tracked from 3.2 s (frame 48).
  - t01 and t03 pass only because their cue time is the prompt frame. t05's cue moved earlier when call 132 read the note inside its track box.
  - Run provisionally (`controls/paste_provisional.py`, a data substitution with no repo code change): the crop is placed against the touched object's first tracked frame at or after the cue frame, and the window still starts at the cue. The provisional entry is recorded in both results' `input_meta`.
  - Either reading leaves m at 32, because every margin passes everywhere.
- **Codec null and κ_codec** (§9; `controls_inputs.py null` → `lines_job.py codec-null --m 32`, `--noop` on the glass take; `<take>.null720.json`, `.null1080.json`).
  - **κ_codec(720p) = 0.8611; κ_codec(1080p) = 0.7539.** Each is the 1st percentile over 106,363 and 106,721 room cells (the terrazzo puts lines in almost every room cell).
  - **D0 under R0 = ~dilate(home, 32), median / 95th percentile, px:**

    | Render | 720p | 1080p |
    |---|---|---|
    | t01-ink | 0.0301 / 0.0374 | 0.0670 / 0.0760 |
    | t01-gold | 0.0294 / 0.0364 | 0.0654 / 0.0742 |
    | t01-paper | 0.0299 / 0.0371 | 0.0665 / 0.0754 |
    | t02-ink | 0.0466 / 0.0557 | 0.0624 / 0.0695 |
    | t03-ink | 0.0266 / 0.0358 | 0.0631 / 0.0687 |
    | t04-ink | 0.0272 / 0.0429 | 0.0648 / 0.0706 |
    | t05-ink | 0.0287 / 0.0383 | 0.0649 / 0.0750 |
    | t06-ink | 0.0265 / 0.0344 | 0.0723 / 0.0814 |

  - Every frame is scored (189–205 a take). The 720p null is about half the 1080p one: it is one lanczos downscale, like the analysis copy, while the 1080p null is downscaled only on decode.
- **Shift control** (§10; `controls_inputs.py shift --m 32` → `lines_job.py shift-control --kappa κ_codec`; `<render>.shift720.json` and `.shift1080.json`; PREREGISTRATION names one `<render>.shift.json`, and m and κ are per resolution).
  - **It fails on every render at both resolutions: no frame has all four patch cells redrawn.**
  - The registered rule picks the block with the most line pixels. That is the densest terrazzo: (384, 96) on the stand takes and (320, 288) on t02e, coherence 0.06–0.36. Dilated lines cover 62–82 % of each cell there, so a 3 px move leaves IoU at 0.38–0.58 (t01 sample). Redrawn needs IoU below κ/2: 0.431 at 720p and 0.377 at 1080p.
  - **Diagnostics** (`controls/shift_diag.py`, `shift_blocks.py`): the line map moved by (3, 3) rather than re-extracted, over the rule's eligible blocks.
    - At 720p, 24–28 % of blocks would pass on the stand takes (about half of the sparsest third; 2–5 % of the densest third), and 7 % on t02e.
    - At 1080p, about 7 % pass on the stand takes and none on t02e.
    - Per cell, 74 % of t01's room cells fall below κ/2 at 720p.
  - So on the textured desk a 3 px move in dense texture reads **no verdict, not redrawn**. It never reads kept, since its IoU is far below κ.
  - By §10 the failure does not change H; it is reported, and the seam view's redrawn cells carry the insensitivity label. Wording for Aaron (call 133).
- **Lag-energy floor:** unchanged at 1.0. On the keepers it splits as call 131 found (t01f, t02e and t03c applicable; t04d, t05c and t06c on the 90 % rule).
- **Timings:** 16 paste runs in 58 min, 12 null runs in 47 min, 16 shift runs in 38 min. Take and null maps are cached per stack in `cache/lines/`.
- **Housekeeping:** the paste and null inputs (`cache/controls/`, 23 GB) and the t01 gold and paper cue sheets used for the window (`cache/controls/cues/`) are gitignored. Both sheets equal `cues/t01.json` apart from the target. **Before the t01-gold and t01-paper renders**, `compile.py` will need a sheet whose events target gold or paper; where those sheets live (`cues/t01-gold.json`?) is open.

## 9 Nov 2026 (night): the torch and note detectors ruled and built (hub call 132)

- **Aaron accepted both rulings of call 131.** Built test-first (13 new tests; full suite 651 passed, 12 skipped; HEAD and `~/.blind` unchanged by the run).
- **`seam/cues/torch.py`:** `region(masks, n)` is the page track eroded by `PAGE_ERODE_PX` (4) minus every hand and prop track dilated by `TRACK_DILATE_PX` (8); homes are not obstacles. `detect(..., masks=)` counts lit pixels only there, and `lands_on` is the home with the largest mean lit share over the run's first `LANDS_FRAMES` (8) frames, if at least `LANDS_MIN_SHARE` (0.05); the evidence adds `lands_share` and `region`. Thresholds, registration, run and glint rules unchanged; without masks (unit fixtures) the old whole-frame rule and home boxes apply, and streaming still matches the reference.
- **`seam/cues/note.py`:** `box_from_track` gives the note track's box in its last tracked frame, padded by `BOX_PAD` (10) and clipped.
- **`seam/cues/sheet.py`:** the torch requires the take's masks with the page track; the note requires its track (or an explicit `--note-box`). The dead `--home` option is gone.
- **Sheets regenerated:** t02 light at 2.667 s, lands on ink (14.5 % of the home lit; gold and paper 0), committed for the first time; t05 note "JUMP" at 3.4 s (box 405,356,149,104). The ruled torch detector over all seven keepers: t02e 2.667 s (ink), t07e 3.0–5.4 s (ink, the sweep's start), none on t01f, t03c, t04d, t05c, t06c.
- **PREREGISTRATION:** §4 describes both detectors; the rulings list gains calls 131–132 (the chosen takes, ρ, both rulings, the breath detector's check on the new takes).
- **Next:** D0, κ_codec, m and the controls on the terrazzo keepers (tooling built), then Gate R.

## 9 Nov 2026 (evening): the terrazzo reshoot, all seven takes through the pipeline (hub call 131)

- **Renamed by content** (shot out of protocol order): IMG_4143 → `t01-glass-f`, IMG_4156 → `t02-torch-e`, IMG_4146 → `t03-pen-c`, IMG_4148 → `t04-breath-d`, IMG_4147 → `t05-note-c`, IMG_4152 → `t06-hand-c`, IMG_4155 → `t07-curtain-e`. All 4K 30 fps SDR, CFR, 12.6–13.7 s; ingested (`973eca4`). The keepers: t01f, t02e, t03c, t04d, t05c, t06c, t07e. t01e stays as the record of call 129.
- **Blind take-mask points:** seven attempts, all `recorded`, valid and `placed` on the first try, 30–58 s each (t01f's folder 13.5 MB at stride 6). Not found: t02e hand, t05c hand (both cross the frame edge; context only), t04d hand (none in shot), t07e hand and torch (outside the frame). Every touched object was found, including call 127's two failures: t02e's standing object and torch, t06c's hand.
- **SAM 2.1 tracks** (CPU, 12–16 min a take), contact sheets in `media/reshoot-2026-11-09/masks/` (gitignored: they show Aaron's hand). Clean on t01–t06: homes and page every frame; glass from 3.6 s (base and water, as on t01d), torch from 4.0 s (after the hand lets go), the standing object every frame, pen and note from 3.6 s, t06's hand from 3.2 s to the end. t07e: the sweep washes out the gold home (4 s) and the paper home (5 s), which SAM loses for a few frames or puts on the tape, as on t07d; all three recover by 6 s (not rated).
- **ρ** (`seam/align.py rho`, the SAM page track): **1.0 px (the floor) on every take, 0 failed fits** (t01 192, t02 199, t03 192, t04 189, t05 194, t06 205; t07e 194, recorded under `media/`, not `runs/`). The plain desk gave 1.95, 1.30 and undefined on t03–t06. ORB keypoints outside the page + 64 px: at least 2,974 a frame on handheld t02e and 3,536 on the stand takes (diagnostic, `media/reshoot-2026-11-09/diag_take_checks.py`).
- **Take checks (diagnostic):** stand takes still to 0.47 px or better; the stand framing is identical across takes (page box within 1 px). t02e handheld: up to 35 px from its last frame, every fit succeeds; exposure on a registered desk patch drifts 3 % with no step at the torch onset. t07e: the whole frame dims 10–20 % during the sweep (body shadow or exposure), steady from 7 s. t06c: a far desk patch dims 20 % while the hand comes in (body shadow), then holds within 0.5 %.
- **Cue sheets** (registered detectors; committed t01, t03, t04, t05, t06):

  | Take | Fires | t (s) | Right? |
  |---|---|---|---|
  | t01 glass | water (props), ink | 3.6 | yes: the placer's first glass prompt frame (stride 0.4 s); down at about 3 s, hand out by 3.8 s |
  | t02 torch | light | **1.0**, to the end, lands on nothing | **no**: the light comes on at 2.87 s. Not committed |
  | t03 pen | pen (props), ink | 3.6 | yes |
  | t04 breath | breath, ink | 3.557–5.211 | yes (56 dB over the room) |
  | t05 note | note, ink | 3.6 | time yes; the word reads **"LARR JUMP"** (OCR reads the ink creature's legs) |
  | t06 hand | hand, ink | 2.733, to the end | yes (MediaPipe now finds it: the wrist is in frame) |

  Context hands: t01 2.4, t03 2.8, t05 2.267 s. MediaPipe finds no hand in t02e (the hand on the torch has no wrist in shot). Breath fires on t04d and on none of the other six (diagnostic run over all seven).
- **Why t02 misfires:** the terrazzo. The torch detector counts any luma rise of 40 over the take's first frames as light. On the cream desk only a beam could do that; on terrazzo, skin or glass over a dark chip does too. Here the hand holds the torch from frame 0 and moves; registering by similarity, or excluding the strip a shift uncovers, still fires at 1.0–1.07 s. In diagnostics the registered detector also false-fires on t01f (1.8 s) and t05c (2.73 s), where it is not on the sheet.
- **Diagnostic fix, not registered** (`media/reshoot-2026-11-09/diag_torch_onpage.py`): lit pixels count only on the page (SAM page track, eroded 4 px) and off every hand and prop track (dilated 8 px); thresholds and run rules unchanged. t02e fires at 2.667 s (lit area jumps at 2.867 s); t07e 3.0–5.4 s, aimed at ink; none on t01f, t03c, t04d, t05c, t06c. The aim point (the pool's centroid) misses the ink home on t02e because the pool is wide, but the beam lights 18–25 % of the ink home from 2.87 s and none of gold or paper.
- **Diagnostic note box:** OCR inside the note's track box at the last frame, padded 10 px, reads "JUMP" at 3.4 s.
- **Lag energy** over hand and prop frames (floor 1.0): t01f 2.17 (156 frames), t02e 6.23 (198), t03c 1.45 (150; 0.94 on the plain desk); t05c 0.41 and t06c 0.81 are under the floor (the note and the hand lie still), so not applicable; t04d no active frame. Those three rest on the 90 % rule.
- **Notes for Aaron:** t02e: the hand holds the torch from 0 s (PROTOCOL has it lying, the hand in only at 2–3 s), so the wrist tattoo shows 0–3.5 s; it also shows at about 3 s in t05c. The gold creature sits against the standing object's side. t04d: the straw tip is about 1.5 cm from the tail (t04c's 2 cm was accepted; PROTOCOL asks 3 cm); static, outside the ink home. t06c: fingertips about 1 cm from the tail; the wrist is just in frame, no tattoo visible.
- **Housekeeping:** the stale untracked plain-desk sheet `cues/t02.json` (t02c, 0.4 s) moved to `media/reshoot-2026-11-09/stale/`; `cues/t06.json` is now t06c's.
- **Open for Aaron (call 131):** the torch detector change and its `lands_on` rule; the note box. Then the t02 sheet, and D0, κ_codec, m and the controls on the new keepers.

## 9 Nov 2026 (later): take stills thinned, a payload guard, a dry run on textured stills (hub call 130)

- **Aaron's rulings (call 130):** take-mask folders at every 6th analysis frame; t02's torch wholly in frame, the fingertip at switch-on accepted; t06's wrist in frame, a little of the wrist tattoo accepted. PROTOCOL updated (and 4K 30, the terrazzo, one framing for every stand take).
- **`points.TAKE_STRIDE` 3 → 6** (2.5 stills a second; 33 for a 13 s take). The brief's text is unchanged ("evenly spaced in time"); each folder records its stride and its still-to-frame map.
- **`blind.write_folder` payload guard.** `payload_bytes` re-encodes every image as Claude Code does (quality-90 JPEG, base64; it matches the t01d and t01e folders to the byte). A folder over `PAYLOAD_BUDGET` (16 MB) is refused before anything is written. Every caller (take and render points, the frame pick, the rater) writes its folder before it logs an attempt, so a refusal uses none. Tests: the estimate, the refusal writing nothing, a refused take folder logging no attempt and keeping both, the stride.
- **Dry run on real textured stills** (`tools/dry_run_blind.py --only take --take-video takes/t01e.analysis.mp4`, new option; everything under the gitignored `blind/dryrun/`): valid, all six objects placed, 7 model turns, 36 reads, no re-reads, 45 s. Its answer is not used anywhere.
- **Still open:** the frame picker on a textured render (97 stills at 960×540, about 21 MB) would now be refused by the guard; decide its stride, or test a higher budget with a dry run, before the first render mask. The rater's sheets go through the same guard.
- **A test leaked into the real ledger, then reverted.** The first version of the refused-folder test called `monkeypatch.undo()`, which also undid the conftest's redirect of the ledger roots, so its second prepare wrote a real ledger for the synthetic take "t01a", a registry line and a commit (`4c60703`, code bee4faad0f2; never dispatched). Reverted in `caaf99b` (history kept, not rewritten); its `~/.blind` folder and state file removed. The test now re-sets the budget instead. Suite after the fix: 638 passed, 12 skipped (the 5 extra skips: the blindpanel v0.2 worktree is gone), HEAD and `~/.blind` unchanged by the run.

## 9 Nov 2026: the first textured take (t01e): ingest; the blind placer fails on payload; diagnostic ρ (hub call 129)

- **Ingest:** `raw/IMG_4142.MOV` renamed `raw/t01-glass-e.MOV` (4K 30 fps SDR, 12.9 s); `seam/ingest.py` (absolute path; a relative one fails inside ffmpeg) wrote `takes/t01e.*` and the t01e row in `capture/ingest.json`. No warnings, CFR, no HDR.
- **Blind take-mask points:** two attempts, b15b176b546 and b40c27c76d5, both `recorded` and invalid (`error_max_turns`: 40 model turns, no JSON answer); the step is closed `failed`. Ledger commits by the tools. Both sessions read all 68 files in nine turns, then re-read stills (121 and 284 times), saying they "had not loaded". Cause: Claude Code sends each still as a quality-90 JPEG; on terrazzo that is 461 KB (base64, median) against 240 KB on the plain desk, so 65 stills are about 29 MB, near the 32 MB request limit, and earlier ones fall out of the context (t01d: 15 MB, answered in 10 turns). No masks, so no registered ρ and no props (glass) cue for t01e.
- **Diagnostic ρ** (not registered; `media/reshoot-2026-11-09/diag_rho.py`): `align.fit_similarity` and `rho_from_residuals` unchanged, with a page mask thresholded from frame 0. ORB outside page + 64 px: 3,850–4,000 a frame; 194/194 round-trip fits; residual P99 0.33 px; ρ = 1.0 px. t01d under its SAM page track for comparison: 1–62 a frame, 31 frames under 20.
- **Diagnostic cues** (`seam.cues.sheet`, `--detectors hands,torch,breath`, written to `media/`, not `cues/`): hand 2.67–4.0 s; breath none; torch a false fire at 2.27 s on the glass's highlight (the torch detector is not on t01's sheet).
- **Take checks:** camera still to 0.18 px after the hand leaves; desk brightness within 1.05 % from 4.5 s; creatures 91–95 px long (about three cells).
- **Next (hub call 129):** Aaron's ruling on thinning take-mask folders to every 6th analysis frame; a payload budget check in `prepare` and a dry run on textured stills before any ledger attempt (also for the frame picker, about 21 MB on terrazzo, and the rater sheets); t01f shot with the rest.

## 8 Nov 2026 (evening): take masks on the seven keepers; cue sheets; ρ. Stopped before the controls

- **Blind take-mask points** (`seam/points.py take`, `seam/dispatch.py run`), one attempt per take, all `recorded`, valid and `placed`; no lost or failed attempt. Ledgers and registry committed by the tools (14 ledger commits); prompt files `masks/prompts/<take>.json`. The placer gave **not found** for: t02c the standing object and the torch, t06b the hand, t03b the hand, t04c the hand, t07d the hand and the torch. In t02c and t06b these are the touched objects, and each is cut off by the frame's edge for the whole take, which the brief's first rule ("not cut off by the frame's edge") excludes. Brief and answers unchanged; nobody edits a valid answer.
- **SAM 2.1 tracks** (CPU, `masks/<take>.npz`), 11–16 min a take. Contact sheets: `tools/mask_sheet.py` (new; for looking only). Homes and page are clean on t01–t06. The t01 glass track covers the ramekin's base and water, not its rim. t07d's page track spills into the torch's light pool from about 3 s to 6 s and the paper home catches the tape at 5 s (t07 is not rated). For Aaron: reject-take (reason `missing`) on t02c and t06b, or rule on the brief; a second attempt under the same brief would likely give the same answer.
- **Cue sheets** (`seam/cues/sheet.py`, registered detectors):

  | Take | Fires | t (s) | Plausible? |
  |---|---|---|---|
  | t01 glass | water (props, the glass) | 3.0 | yes (2–3.5); settle = the placer's first prompt frame, since SAM tracks forward only |
  | t02 torch | light | **0.4**, aimed at (1177, 556), lands on nothing | **no**: the light comes on between 3 and 4 s |
  | t03 pen | pen (props) | 3.2 | yes |
  | t04 breath | breath | 2.715–3.824 | yes |
  | t05 note | note (OCR) | 3.2 | yes |
  | t06 hand | (none) | — | **no**: MediaPipe finds no hand in any frame, even at confidence 0.1; the fingers come in from the left edge with no wrist in shot |

  Committed: t01, t03, t04, t05. t02 and t06 are not committed. t07 has no sheet: the sheet takes one target, and the curtain call has three.
- **ρ** (`seam/align.py rho`, ruling 3: report the failed round-trip fits): t01 1.95 px with 32 of 193 failed (frames 0–31, before the ramekin is down); t02 1.30 px, 99 of 199 failed; **t03, t04, t05, t06: ρ undefined, every fit failed** (195, 191, 191, 203). Cause: the plain desk outside the page (dilated by 64 px) gives 1–2 ORB keypoints a frame; only a prop or the torch reaching past the page gives the 20 needed. This is the rehearsal's finding 3 on the real takes. A render on these takes would fail the gate ("ρ undefined"), and on t01 at most 83 % of frames could pass the 90 % rule.
- **Lag energy** over the frames with a hand or prop mask (the floor is 1.0 at drafting): t01 2.50 (160 frames), t05 1.40 (149), t03 0.94 (147; below the floor, so not applicable), t02 and t04 no active frame.
- **Not run (stopped, as the brief asked):** the paste and shift controls, the codec nulls, D0 and κ_codec, m. The tooling for D0 and κ_codec is built and tested: `controls_inputs.py null` and `lines_job.py codec-null` (`controls.codec_null`).
- **Suite:** 639 passed, 7 skipped, 1 deselected (was 637).

## 8 Nov 2026: Aaron's seven rulings before Gate R (hub call 126) and the mixed raters (call 115)

- **Lag check (ruling 1).** `align.lag_check` averages the take's motion energy over the frames where its hand or prop masks are non-empty. A take with no such frame (the breath take) is "not applicable" and rests on the 90 % rule; the page fallback goes. The gate records `lag_n_active`. Tests: an 11 s take whose hand moves for 2 s now gets a lag (0 on a copy, 2 on a render 2 frames late), where the whole-take mean sat under the floor; a take with no hand or prop frame passes at 36 of 40 frames and fails at 35. PREREGISTRATION §6; the §25 note on the breath take is resolved.
- **Uncovered pixels (ruling 2).** `align.cover` marks the take-grid pixels whose source lands inside the render frame. `render_pair.py` stores it in the pair as `cover` and removes the rest from R(t). `cells.classify` gives a cell with an uncovered pixel no verdict (not creature, never a room cell). The lines job passes `cover` for the render and for the null scored under its R(t). The assembler rebuilds R with it. Test: a no-op-like render framed 40 px off scored κ_render_p1 0.15 with the strip in R and 1.0 without it, with no border cell scored. PREREGISTRATION §6, §7, §11.
- **Breath detector (ruling 7).** A breath is a run at least 30 dB above the room floor (10th percentile of frame RMS) lasting at least 0.5 s, merged across gaps under 0.1 s, ignoring frames that reach into the first or last 0.5 s. The spectral-flatness test goes; page flow stays as evidence. PREREGISTRATION §4 now has a cue-sheet paragraph.
  - **Checked on the seven chosen takes** (mono 48 kHz WAVs pulled from `raw/` into a temp folder, nothing written here):

    | Take | Room floor (dBFS) | Highest rise inside the edges | Fired |
    |---|---|---|---|
    | t01-glass-d | −66.6 | 40.5 dB at 2.38 s, 75 ms (the ramekin set down) | no |
    | t02-torch-c | −60.3 | 24.4 dB | no |
    | t03-pen-b | −68.4 | 15.1 dB | no |
    | t04-breath-c | −66.2 | 58.3 dB at 2.94 s | **yes: 2.72–3.82 s** |
    | t05-note-b | −63.6 | 17.2 dB | no |
    | t06-hand-b | −63.2 | 28.0 dB | no |
    | t07-curtain-d | −59.6 | 19.7 dB | no |

  - In the six other takes the loudest moment (43–57 dB over the room) falls in the last 0.15 s: the record button, which the 0.5 s edge removes. The breath fires from 2.72 s, where it first reaches 30 dB; the blow is audible from about 2.4 s (call 124).
- **Shift pair (ruling 5):** PREREGISTRATION §10 records that it is measured only through `shift-control`.
- **Clearance (ruling 6):** the private repo is "StillDrawn's private working repo" in PREREGISTRATION §8, the 31 Oct entry below and the measurement sub-plan. Nothing else in the tree names it (outside `sealed/`, `raw/` and git history, which the squashed public push leaves behind).
- **Raters (call 115):** PREREGISTRATION §17 and §25: two in person on Aaron's Mac, one to three remote, same instrument and wording, mode recorded and reported, in-person raters kept away from the making, the shoot and the reactions.
- Rulings 3 (desk texture: check ρ's failed fits on the first real run) and 4 (disk) change nothing.

## 3 Nov 2026: the render pair writer, the end-to-end rehearsal, the maskrule clearance

- **The render pair writer** (`seam/render_pair.py render`).
  - Inputs: the take's analysis copy; the render, warped onto the take by the gate's per-frame transforms; the logged final track.
  - It writes `meta.render`, and computes `render_mask_digest` and `render_mask_file_sha256` from the track file itself. It has no digest argument.
  - It also writes the video, take, take-mask and prompt-file hashes, the prompt frame, m, the acting home, the gate's canonical hash and pass, and the digest of the warped creature mask it stores.
  - It refuses: a missing or "none" pick; the wrong video; a gate run on other inputs; a gate that failed or contradicts itself; a track not made from the final prompts; any custody break (it runs `points.custody` before writing).
  - `render_pair.py null` writes the codec null pair.
- **`seam/align.py` gets a command line.**
  - `rho` gives ρ from the take's 720p round trip (`p47-rho/1`).
  - `gate` writes `p47-gate/1` with each frame's transform and the input hashes.
  - Both read videos as the masks and the pick do (`masks.analysis_frames`).
- **The custody is tighter** (`points.custody`).
  - Besides the logged track's digest and file hash, it now needs the pair's video to be the picked one, a passing gate, the track's prompt file, and the pair's creature array to match the digest its writer recorded.
  - `assemble.py` refuses a `--gate` file that is not the gate the pair was built under.
  - The no-op null stays the only exemption, unchanged.
  - Tests cover a full chain that passes, and each break: a missing pick, an uncommitted ledger, a track that isn't the logged one, the wrong video, a failed or self-contradicting gate, a gate on other inputs, and a pair edited after writing.
- **The rehearsal** (`tools/rehearse.py`; `tests/test_rehearsal.py`, marked `rehearsal` and deselected by default).
  - A synthetic take: a drawn page, three shapes at the protocol's positions, and a glass carried in by a hand.
  - A synthetic render at 24 fps: the left shape walks to the glass and touches it, under a drifting similarity warp, with noise and a CRF 26 encode.
  - Every stage runs in order in a throwaway repo (`blind/rehearsal/`). Stub blind answers go through the test helpers' fake transcripts; no live dispatch and no paid call. The prototype's history is untouched; the throwaway repo holds the 9 ledger commits.
  - **The full-length run (11 s take, 165 analysis frames; real lines job in the ComfyUI venv on MPS): 27 min.**

    | Stage | Wall time |
    |---|---|
    | make inputs | 20 s |
    | ingest | 11 s |
    | take-mask points (stub) | 1 s |
    | take masks (SAM 2.1, 6 objects, CPU) | 930 s |
    | cue sheet | 3 s |
    | compile and the offline estimate | 0.3 s |
    | ρ and gate | 20 s |
    | blind pick (stub) | 3 s |
    | place, two tracks, check, track-done | 274 s |
    | render pair and null pair | 8 s |
    | lines job (with the null) | 333 s (2.0 s per analysis frame) |
    | assemble | 5 s |
    | H | 0.02 s |
    | rating seal and build (blindpanel lock, build, verify) | 18 s |

  - **Results:** take-mask IoU against the truth was 0.86–0.92. The gate passed (ρ 1.0 px floor; residuals about 0.6 px). The render track IoU had a median of 0.86 (the check accepted the first point). All 165 frames were scored, 126 eligible and 37 contact, against 30 contact frames in the truth (d = 8 px reaches before the touch). H was "not testable", as it must be with one render; a rerun was byte-identical.
- **Bugs found and fixed:**
  - `pairs.write_pair` didn't create its folder, so the first pair of a run failed (fix and test).
  - The test helpers' fake transcripts gave every read its own turn, so a 45-still pick went past maxTurns. `blindkit.PER_MESSAGE` now batches reads, as a real agent does.
- **Findings for the controller** (not changed; registered rules):
  1. **The lag check goes "not applicable" on a full-length glass take.** The take's mean motion energy in the hand and prop masks was 0.67, below the floor of 1.0: the hand moves for 2 s of 11, and the mean runs over the whole take. At 6 s it was applicable (lag 0). The energy floor is still to be set from the real takes; consider whether the mean should run over the frames where the masks are non-empty.
  2. **κ_render_p1 was 0.0**, because the frame-edge cells are redrawn: 1,696 of 2,765 redrawn cells sit on the border ring, which is 13 % of the cells. Partly this is the synthetic render's reflected border. But any warp leaves a replicated strip, and the no-op render's P1 is κ_keep. Decide before Gate R whether pixels the warp did not cover leave R(t) (or cells touching them get no verdict).
  3. **ORB needs desk texture.** The first synthetic desk, a muted wood-like palette, left about 10 keypoints outside the page dilated by 64 px, so every round-trip fit failed and ρ was undefined. The protocol's "clear desk" could do the same. Check ρ's failed-fit count on the first real take.
  4. **A pair is large.** It is uncompressed by contract: 1.2 GB for an 11 s render, plus the same again for its null pair.
  5. `controls_inputs.write_shift_pair` names `meta.render` as `<take>-<material>`. `lines_job.py measure` would now refuse it (no custody). Is the shift pair ever measured, or only the `shift-control` command?
  6. While StillDrawn's `metrics/` had uncommitted files (P46 adding `masked.py`), the lines job refused, as designed. The equality test now covers both `masked.py` files.
- **Clearance:** `seam/maskrule.py` and `tests/test_maskrule.py` cite P46's masked rule instead of the private repo. The test loads the same files through the hub's repo links. The private repo's name is still in PREREGISTRATION §8, in LOG (31 Oct) and in `docs/superpowers/plans/2026-10-31-c-measurement.md`: Phase 4.3 needs to settle these.
- **Suite:** 630 passed, 7 skipped, 1 deselected (the rehearsal). It was 615.

## 3 Nov 2026: blind agents, final review fixes (two Critical)

- **C1, ledgers can't be rewound before or after their first commit.**
  - Prepare refuses a ledger or registry that was deleted, rewound or edited since its last commit, and commits both itself ("blind ledger: <kind> <code> prepared").
  - `dispatch.py run` needs them committed at HEAD with the code `prepared`.
  - After the call is settled, the dispatcher commits them again in a `finally`, with a fixed message and only those paths. Recorded, failed and lost attempts are all committed, for the rater too. `track-done` and `reject-take` commit their entries.
  - The reviewer's demonstrations are tests: `git clean -fd agents` and then a second pick; `git checkout -- <ledger> <registry>`; a checkout of the prepared commit; and the rater variant. Each now fails to produce a second answer, and `verify` keeps the first pick.
  - PREREGISTRATION §18 now says the logs are tamper-evident, not tamper-proof, and that the public, archived A1 addenda after Gate R make any later rewrite visible.
- **C2, deleting the evidence never earns a retry.**
  - `adjudicate` always records `lost_after_dispatch`.
  - `run` reads the call's stdout through a pipe, keeps every byte in memory while writing the exclusive-create audit file, and decides only from those bytes. `dispatch_failed` needs no init, model or result event and a non-zero exit.
  - A stream file replaced mid-run is `stream-replaced`, which is lost.
  - Tests cover "kill -9, delete the stream and the store, adjudicate" and "stop the call, unlink the stream and the store mid-run": both are lost, and the step is closed.
- **Suite:** 615 passed, 7 skipped (was 608).

## 3 Nov 2026: blind agents, re-review fixes (2 Critical, 3 Important, minors) and call 110

- **C1, no fork, no rewind.**
  - The ledger, state, transcript and prompt roots are fixed module constants (tests set them). No command takes `--log-dir`, `--state`, `--pick-log` or `--points-log`.
  - Every prepared code is appended to `agents/logs/registry.jsonl`, and a ledger whose attempts are not the registry's is refused by `prepare`, `verify` and the custody.
  - The custody, and so `assemble.py` and `lines_job.py measure`, needs each ledger and the registry committed and unmodified at HEAD (`git ls-files --error-unmatch`, `git diff --quiet HEAD`).
  - Audit copies are written by exclusive create.
- **C2, losing the store gains nothing.**
  - The dispatcher writes the stream-json pipe itself (exclusive create) as the audit transcript. Claude Code's session store is the cross-check: the tool calls and the final text must match, and only the store holds the dispatch text, the agent and the system prompt.
  - `dispatch_failed` happens only when nothing reached the API. Otherwise the attempt is `lost_after_dispatch` (a missing, duplicated or mismatched store, or an unbound stream): the step closes as failed, with no fresh attempt, and the attempt is flagged for A1.
  - `dispatch.py adjudicate` settles a stuck attempt by the same rule.
  - The store is copied and then purged in a `finally`.
- **I1.** The render check needs the first track's meta to name `<render>.p1.json` and the pick's video, and logs the track's hash. `track-done` checks the video too.
- **I2.** Rater rounds are a fixed set (`probe`, `draft-1`, `draft-2`, `study-baseline`, `study-clips`). Each ledger holds its refs' hash, and a second round over the same refs is refused. Panel hashes come from `sealed/rating-manifest.json`.
- **I3.** No `--allowedTools`. The canary, run live once (two runs, law-free, on the subscription), passed:
  - the real picker agent declined to read a sibling folder's file;
  - a permissive probe with the same flags tried it and was refused by the harness ("…is outside ~/.blind/…; --restricted confines the file tools to the working directory");
  - the word never leaked.
- **Minors:**
  - turns are counted from distinct message ids and capped at maxTurns;
  - exactly one message may carry a JSON answer, and it must be the last. Plain narration is allowed: 2 of the 5 real dry-run sessions wrote text between reads, so "one text-bearing message" would have failed valid runs;
  - only `t01-noop` with its `MANIFEST.sha256` row is exempt from custody (closed until then);
  - the custody needs `meta.render_mask_file_sha256` equal to the logged track file (the pair builder isn't written, so this fails closed);
  - §7 notes that the home outline is drawn on unwarped frames.
- **Call 110** (ratified by Aaron with call 108, 3 Nov): the compiler says the creature "steps up out of its place on the page" (`seam/compile.py`; test; PREREGISTRATION §4 and §25).
- **Suite:** 608 passed, 7 skipped (was 591). The comfy-venv CLI test was run there (run only, nothing installed).

## 3 Nov 2026: review fixes for the blind agents (2 Critical, 7 Important), call 108, and a dry run

- **C1, no choosing among answers.** Every call site now has a committed ledger:
  - `agents/logs/prompt-frame/`, `take-mask-points/`, `render-mask-points/` and `rater/<round>`.
  - Preparing a folder appends a `prepared` attempt (code, dispatch hash, inventory hash, time).
  - A new folder is refused while one is unrecorded, and every prepared folder counts against the two attempts.
  - `verify`, the assembler and the lines job refuse a ledger with an unrecorded attempt.
- **C2, transcripts are bound.** The first message must be the stored dispatch, and the session the one `dispatch.py` logged (`dispatched`). The agent (`agent-setting`), the system prompt's hash, the pinned model and Read as the only tool are checked.
  - An empty, unparseable or unbound transcript is refused outright: it is not an attempt and frees none.
  - Every transcript is copied to the gitignored `blind/transcripts/`, with its hash in the ledger.
  - The two reported abuses are tests: an empty `.jsonl` and a hinted dispatch.
- **I1, custody is required.** `assemble.py` has no manual `--prompt-frame`. `--prompts` is required, with the pick and points ledgers as defaults.
  - `lines_job.py measure --render` refuses a render unless its pick is valid and its prompt file is the logged final points.
  - `points.py track-done` logs the final track's digest, and the pair's `meta.render_mask_digest` must equal it.
  - The no-op null (`<take>-noop`) has no creature and no pick.
- **I2, no agent text in committed files.** Problems count stray keys and name only our own letters, codes and positions. Reads outside the folder, or of unlisted files, are stored as hashes plus a count. Unknown tool names become `unlisted`. Duplicate JSON keys are refused. Tests put free text in a key and in a path.
- **I3.** `masks track` samples any 16:9 source onto the 1280x720 grid, as the picker and placer do, and refuses another shape. The masks meta records the source size and the prompt and video hashes.
- **I4, call 108.** The prompt frame is the first frame fully clear of the creature's home.
  - Each pick still and the point placer's frame show the home as a thin grey dashed outline, from the take's home mask. `target.txt` is gone.
  - "none" means the render is not testable for H.
  - The briefs are at version 2. PREREGISTRATION §7 and §25 are amended.
- **I5, bare sessions.** `seam/dispatch.py` runs each call as `claude -p` from the folder itself (directly under `~/.blind`):
  - flags: `--agents/--agent` from the vendored file, `--tools Read`, `--restricted`, `--strict-mcp-config`, `--disable-slash-commands`, the pinned model and effort, and a fresh `--session-id`;
  - the caller's `CLAUDE*` environment is dropped;
  - context files are allowlisted (only the global CLAUDE.md), each with its content hash;
  - after recording, Claude Code's own session store is removed, since the Mem indexer walks it.

  A probe showed a bare session loads no CLAUDE.md or memory, and its system prompt is exactly the agent body.
- **I6.** Rater item codes are drawn inside `build_rater_folder` from a fresh salt, and the code-to-ref map stays in `sealed/blind/`. `items.txt` is shuffled by a seed logged in the ledger. A study reference picture must hash to its baseline panel (call 108, §17).
- **Also:**
  - §17 amended (ringed reference; the declaration-before-rating exclusion; the fixed reply);
  - A3 commits the rater ledger (read paths, hashed where agent-chosen), with the answers sealed;
  - `render_sealed_brief` refuses output outside `sealed/`;
  - the neutral root is the persistent `~/.blind`, and paths may not hold take ids or material words;
  - `reject-take` reasons come from a fixed list;
  - `dispatch.py addendum` prints the A1 rows (ledgers, prompt files, hashed folder maps and transcripts);
  - the leak test scans commit messages;
  - the manifest draft has 308 rows.
- **I7, dry run** (`tools/dry_run_blind.py`, drawn shapes only, fixture Q2 labels, on the subscription). Every brief at full length finished, valid. "Turns" are model turns; `num_turns` in the CLI result counts tool results.

  | Brief | Model turns | `num_turns` | Answer |
  |---|---|---|---|
  | pick (90 stills) | 8 | 53 | frame 96; the first clear frame was 94, one still late, the direction the brief asks for when unsure |
  | take points (60 stills) | 9 | 64 | page and the three homes placed; the thin circle and the hand blob reported not found |
  | render point | 3 | 5 | inside the blob |
  | outline check | 3 | 6 | correctly asked for a second point on a half-outline |
  | rater probe (4 clips, 12 sheets) | 5 | 15 | |

  All are inside maxTurns 40 thanks to batched reads (10 per turn). The run cost about $1.70 in total on the subscription. The `~/.blind` folders and session stores were removed; the audit copies are in the gitignored `blind/`.
- **Suite:** 591 passed, 7 skipped (was 547).
- **Comfy venv:** the lines job's CLI test passes there with `--render t01-noop` (run only, nothing installed).

## 3 Nov 2026: the blind agents' pieces (prompt frame, points, rater briefs), vendor copies, manifest paths

- **Blind prompt-frame pick (call 106).** `seam/frame_pick.py` writes a folder outside the repo under a random code: the frozen brief (`agents/briefs/prompt-frame.md`), `target.txt` (left, centre or right), `stills.txt` and every 2nd analysis frame of the render at 960x540 as `001.png` and up, no grid. `record` reads the agent's own transcript: the brief must be read first, nothing outside the folder, no tool but Read, the folder unchanged, the answer exactly `{"pick": n}` or `"none"`, every still up to the pick read. It logs the brief's and agent's hashes, every file's hash, the read log and context files, and the analysis frame (still k is frame 2(k-1)) to `agents/logs/prompt-frame/<render>.json`. Free text is never stored, only its hash. An invalid attempt allows one fresh one; a valid pick is final; the controller never judges it. `verify` and `assemble.py --pick-log` refuse a prompt frame that is not the logged pick.
- **One agent for frames and points.** `blind-frame-picker` (hub `.claude/agents/`, copy in `agents/`) serves three briefs in separate calls; the rater stays its own agent.
- **Point placers.** `seam/points.py`: take masks from gridded stills (every 3rd frame, 1280x720, objects as opaque letters with plain descriptions; Aaron's contact-sheet rejection allows one fresh placement), and render masks from the picked frame only, then a blind check that accepts the outline or gives the one second point. Only the check writes the final prompt file.
- **Rater briefs.** Law-free templates for the probe and drafts, the study baseline and the study clips, and the human study record (the invite and on-screen wording, held by a test to `rating/prepare.py` and PREREGISTRATION §17). The Q2 options are a placeholder; the filled copies go in `sealed/briefs/` at Gate R (`seam/blind.py render-brief`). The rater folder builder and recorder write answers under `sealed/machine-rater/`.
- **Vendor copies.** `vendor/runway/` (client and tests, hub `3929bf0`) and `agents/` (both definitions), each with a `SOURCE.md` of hub path, commit and SHA-256; `tests/test_vendor.py` checks them, and the hub files where present.
- **Manifest draft.** `seam/controls_inputs.py`, `takes/tNNX.*`, `masks/prompts/tNNX.json`, per-take point logs, the seven briefs, the four sealed briefs and every new code and test file: 302 rows, zeros as before.
- **A guard.** `python -m seam.masks track` refuses a video that is not 1280x720, since every point prompt is in analysis pixels.
- **Suite:** 547 passed, 7 skipped (was 427). Nothing read from `sealed/` except to write `sealed/briefs/README.md`; nothing generated, installed or pushed.

## 3 Nov 2026: Gate C1 and the registration rulings

- **Gate C1:** Aaron picked **c05** (C16-4716, the loaf-bodied blob on four stub legs), with c03 as the fallback. Making notes: drop the dashed lines and the ink smear, and keep the eye. One sealed law's wording was adjusted to suit the body (a free change before Gate R).
- **Registration rulings** (PREREGISTRATION §25, rulings block):
  - Q2 options by salted hash only;
  - a fresh, squashed public history with no media at Gate R;
  - item codes assigned at Gate R;
  - the item-8 readings accepted;
  - a blind agent picks each render mask's prompt frame, logged before any D.
- **Laws (sealed):** the 10 unrated cells approved, and the sealed table of record written. The clause wording stays as approved. The curtain call is hand-written and not a test. `laws.json` still validates.
- **Page layout confirmed** as the protocol gives it.

## 31 Oct 2026: rating preparation, review fixes (blinding)

- **Opaque kit ids.** The kit ships `seed` in `study.json` and hashes (seed, kind, id) into the code, so the readable ids (`t01-ink`) let a rater recover take and material. Each item's kit id is now `"i" + sha256(salt:ref)[:10]`, stored in the sealed key (`ids`) and checked by `build`. Refs stay in the sealed key and the local, unshipped `study.yaml` (the export uses them). Test: no code is reproducible from a readable id built from takes x materials, with a control that finds codes made the old way.
- **Banned terms.** The exact model ids (`seam.compile.MODELS`) are plain-substring lines. The check on the wording a rater reads uses a word-start material pattern, so `t01-ink`, `inky` and `ink-stained` hit; the dist scan keeps the standalone pattern so the kit's `--bp-ink` passes.
- **Copy length is chosen.** `build` needs `--seconds` or `--frames` (no default to the shortest source). It prints each source's length and the chosen one, and stops before encoding if a source is shorter.
- **Minor.** `cue_time` no longer falls back to another material's event (give `cue_s`); a missing key in the takes or inputs is a clean error; `seal` writes both files or neither; the container scan moved to `rating/container.py`.
- **Tests.** 37 passed in `tests/test_rating_prepare.py`.

## 31 Oct 2026: ingest, assembler and control inputs (synthetic clips and fixtures only)

- **`seam/ingest.py` (Phase 1.5).** An iPhone original becomes the render input (SDR Rec.709 H.264 1080p30 CFR), the 1280x720 analysis copy, a mono 48 kHz WAV and a row of `capture/ingest.json`; SHA-256 of the original and of each output. HDR (PQ, HLG) is tone-mapped from stock ffmpeg filters (no zscale in this build); VFR becomes CFR; a take over 30 s, a non-16:9 or sub-720p source, or an original outside `raw/` is refused. Single-threaded and bit-exact, metadata stripped: hashes are stable run to run. `takes/` is gitignored. 31 tests (calls 96).
- **`seam/assemble.py` (Phase 8).** One `p47-measure/1` per render from the gate, masks, lines-job record, hand and OCR series: scored frames (gate and mask quality from the prompt frame; before it the creature is at home), contact and eligible, motion in R, d and proximity variants, redrawn shares, κ and κ source, the seam bin path. Mismatched lengths, a wrong render or margin, a κ the job did not use, and a bad seam bin are refused; NaN D becomes null. Its output goes through `analysis/h_contact.py` in the tests. 42 tests (call 97).
- **`seam/controls_inputs.py`.** The paste composite (crop scaled to the home's area, placed 4 px from the touched object on the line to the home, held through the cue window), the codec nulls from the render input at 720p and 1080p, the shift region, and the npz files `lines_job.py` reads (`paste-control`, `shift-control`, and a pairs-format shifted copy). `capture/takes.json` rows gained a `paste` entry. 26 tests (call 98).
- **Suite:** 395 passed, 7 skipped. Nothing read from `sealed/`, nothing generated, nothing pushed; nothing installed in the ComfyUI venv.
- **Readings to confirm at Gate R:** see calls 96-98 (tone-map as a fallback only; crop scale by area; placement rounding; redrawn-share definition; paste mask names; manifest paths `takes/` and `controls_inputs.py`).

- **Review fixes (call 101).** The assembler cross-checks the gate (`pass`, `reason`, `frames_ok`) and carries the lag basis (`lag_source`, `lag_applicable`, `lag_reason`, `duration_ok`, `lag_energy_mean`); it checks `extra_lines` runs against the primary and needs `--prompts` or `--prompt-frame`. Ingest validates `ingest.json` first, works in a directory beside the outputs, refuses outputs inside `raw/`, and wraps tool failures. The control inputs gained `shift-pair`, identity checks on the paste and shift results (`input_meta`), and tRNS alpha. `seam/util.py` holds the shared `sha256_file` and `ffmpeg_version`.

## 31 Oct 2026: rating preparation (`rating/prepare.py`, synthetic clips only)

- **What.** `rating/prepare.py seal` (Gate R, once) and `rating/prepare.py build` (Phase 9.2). `seal` writes `sealed/answer-key.json` (salt, seed, opaque item codes, and the answer key in the shape `analysis/ratings.py` reads) and `sealed/q2-options.json` (the seeded shuffle, "Nothing in particular" and "Can't tell" last). `build` reads both and never re-codes or reorders. It refuses if the key is missing, if a code is not the kit's code for the key's seed and the item id, if the key's answers disagree with the takes and laws, or if the options differ from the laws' labels and decoys.
- **Build.** Rating copies (H.264, 1280x720, one constant rate, one frame count for all, no audio, `-map_metadata -1 -fflags +bitexact`, colour tags fixed to Rec.709, byte-identical on a rerun), each checked (one video stream, structural tags only, no `uuid`, `jumb`, `jumd`, `c2pa`, XMP box and none of the long C2PA markers). Ringed cue-frame stills (`ring_bbox` in `capture/takes.json`, else a placeholder from `target_position`, with a warning). One `study.yaml` per rater id (`limn-r1`...), `tally: false`, banned terms from models, material names, the slug and the sealed law words. Then `blindpanel lock`, `build` and `verify --dist` through the v0.2 worktree CLI.
- **Tests.** `tests/test_rating_prepare.py`, 27 passed on synthetic clips and fixture laws: the strip (a fake JUMBF box and tags injected and gone), identical sizes and frame counts, the ring position, code-named files, the sealed-code and Q2-order refusals, banned terms absent from the built study, the answer key against `ratings.py` on a fixture export, and a `blindpanel export` round trip.
- **Kit limits found.** (1) The kit shows one image per panel, to the baseline question and beside the clip, so the clip's reference still is the ringed cue frame, not the take's first frame as R0.8 says. (2) The page's submit button still says "public tally" when `tally` is false.
- **Not done.** Real renders, a real seal, and the real-run check of banned terms against the actual Q2 labels. Nothing deployed or pushed.

## 31 Oct 2026: R0 drafted (DRAFT, not registered)

- **What.** `PREREGISTRATION.md` (25 sections, labelled EXPLORATORY and DRAFT) and `MANIFEST.draft.sha256` (267 rows, all-zero placeholders except the netG, SAM 2.1 and hand-landmarker hashes), commit `c15dfd5`. Gate R is Aaron's; nothing pushed.
- **Sources.** The master plan's R0.1–R0.9, Decisions and Criteria; calls 1–77; the code in `seam/` and `analysis/`; P46's A9 for structure. `sealed/` was only listed, never read.
- **No law content.** The laws, LAWS.md, the answer key, the Q2 labels and the real requests appear only as manifest rows. The Q2 option list is registered by salted hash and published at close. The leak guard (`tests/test_sealed_leaks.py`) passes with both files staged.
- **Blanks** (⟨TBD at Gate R: …⟩): ρ per take, D0 floors, κ_codec at 720p and 1080p, m at 720p and 1080p, the shift results, take hashes, the StillDrawn commit, the ComfyUI venv and ffmpeg versions, the blindpanel and client commits, and the expected testable count (7 by design). κ_keep is set after Gate P2.
- **Flagged for Aaron** in §25: the Q2 labels against R0.8; the breath take can't pass the lag check (no hand or props, so the energy is flat); the probe's 10 s trim for every arm; the unbuilt 4 s draft trim; the mask quality rule before the creature leaves the page; m and κ_codec per output resolution; item codes at Gate R; eleven readings where nothing decides; a word in the tracked capture files that says too much (already in history at `6fc0c96`); media in history; the code and briefs still to build before Gate R. Hub calls 78–88.

## 31 Oct 2026: sub-plan C, measurement, controls and analysis (synthetic fixtures only)

Plan: `docs/superpowers/plans/2026-10-31-c-measurement.md` (`b5076a7`). Built test-first, one commit per task, `202f674` to `ebc6bef`. No take or render exists; nothing paid or hosted was called.

- **Built.** `seam/maskrule.py` (the A9.4 frame rule), `video.py` (decode by timestamp, codec-null re-encodes at 720p and 1080p), `align.py` (lag check, ORB + RANSAC similarity per frame, ρ, gate, warp), `regions.py`, `cells.py` (32 px cells at τ = 2 and the 2-bit seam file), `drawn.py`, `controls.py` (paste and shift), `pairs.py` (the npz contract between the venvs), `lines_job.py` (ComfyUI venv only), `hands.py`, `ocr.py`; `analysis/h_contact.py` (R0.4) and `analysis/ratings.py` (R0.8).
- **Tests.** Repo venv: 82 passed, 6 skipped (the frozen-extractor tests, which need the ComfyUI venv). ComfyUI venv (`python -m unittest discover -s tests/comfy`): 10 tests, 9 run and pass, 1 skipped (the refusal test, which only runs outside that venv). Nothing was installed in the ComfyUI venv.
- **Frozen inputs.** StillDrawn public checkout at `d787a0b`, `metrics/inkstab.py` DEFS "inkstab 1.0 (2026-08-12)". `netG.pth` SHA-256 `ccabdcc3f5cf3c07cf65d58776acb21df7dfda825cdc70c9766a93fd62bfc488` (217,631,959 bytes), recorded in `models/MODELS.md`. The job hashes the file on every run and refuses if it differs.
- **The frame rule** equals `inkstab._chamfer` bit for bit with R all-true. It also equals `metrics/masked.py` in StillDrawn's private working repo (`d4b8fde`) on 60 random cases across all four branches. StillDrawn has no `masked.py` yet, so that test is skipped until it does.
- **Timing.** One synthetic 150-frame pair (1280×720) plus its codec null, through `lines_job.py measure` on MPS: 824 s, so 5.5 s per analysis frame with the null and 1.8 s per extracted frame (three line maps per frame, plus the cells, EDTs and stays drawn). That puts a 10 s render at about 14 min. Batch work, run under `caffeinate`. Another agent's local generation may have shared the GPU during the run.
- **Probes.** On a synthetic desk, the H.264 CRF 18 round trip gives fit residuals of at most 0.14 px (720p) and 0.08 px (1080p), so ρ sits at its 1.0 px floor. The paste control with the real extractor, run on a synthetic striped page with a pasted stroke, passes at m = 32.
- **Align change during the build.** Plain ORB keypoints carried about 1 px of quantisation residual on sub-pixel shifts, which on its own would fail frames at ρ = 1. The fit now uses one pyramid level, a Gaussian blur of sigma 1 px on both greys and `cornerSubPix` refinement (11×11). Residuals on exact synthetic transforms dropped to about 0.2 px, and translation is recovered within 0.1 px.
- **Readings** the master plan is silent on are listed in the sub-plan and in the hub calls file (calls 44 to 54).
- **Amendment (controller, call 57).** The shift control now moves its patch diagonally, by (3, 3) px rather than (3, 0), so strokes in every direction are displaced. It was tested first. Afterwards, sub-plan C's tests were 83 passed, 6 skipped in the repo venv (the whole suite 207 passed, 7 skipped), and 9 of 10 ran and passed in the ComfyUI venv.
- **Spec-review fixes (calls 61–65).** Each fix was test first.
  - The shift patch must have no dominant stroke orientation (coherence below 0.5); the move stays (3, 3).
  - An undefined ρ now fails the gate with a reason, instead of raising.
  - H eligibility intersects "object present" with "D not None".
  - The paste control's codec null is encoded at the render model's output resolution, and needs at least 20 scored frames.
  - `tests/comfy` is now a package.
  - Afterwards the repo venv ran 235 passed, 7 skipped (sub-plan C's own tests 90 passed, 6 skipped). The ComfyUI venv ran 9 of 10 tests, all passing.
- **Quality-review fixes (calls 69–73; `bb1d681` to `91faa61`).** Each fix was test first.
  - H treats a non-finite D as ineligible, validates the schema and the series lengths, and computes T through the permuted statistic's code path.
  - The device is pinned to `mps`, with a recorded `--device` override, and a dirty or unreadable StillDrawn checkout is refused.
  - Codec nulls are single-threaded and byte-identical, with the ffmpeg and library versions recorded.
  - EDTs are shared, and the take's and null's line maps are cached in the gitignored `cache/lines/`.
  - Smaller guards: read_video, resample, read_pair, `--seam`, and bounds checks.
  - **Speed** on the same synthetic 150-frame pair plus null: 1.87 s per analysis frame with an empty cache (it was 5.5 s), and 1.05 s with the take cached. The median D was unchanged to every digit.
  - Tests: the repo venv ran 252 passed, 7 skipped (sub-plan C's own 107 passed, 6 skipped). The ComfyUI venv ran 14 of 15 tests, all passing.
- **R0 review fix (call 91; `e3057eb`).** The breath take has no hand or prop masks, so its lag check had nothing to measure and always failed.
  - Such a take now times the lag on the page mask.
  - If the take's mean motion energy is below 1.0 grey level per frame, the lag check is "not applicable", and the gate rests on duration and the spatial test.
  - The gate output records the lag source.
  - The floor is a default, to be checked against real takes before Gate R.
  - Tests: the repo venv ran 282 passed, 7 skipped (sub-plan C's own 111 passed, 6 skipped). The ComfyUI venv ran 14 of 15 tests, all passing.

## 31 Oct 2026: sub-plan B, masks, cues and compiler (synthetic fixtures only)

Plan: `docs/superpowers/plans/2026-10-31-b-masks-cues-compiler.md`. Built test-first, one commit per task (`b87c8a6` to `8d068b0`). 113 tests, plus one slow SAM test behind `LIMN_SLOW=1` (passes). The whole default suite (B and C) ran in 67 s.

- **Masks** (`seam/masks.py`). Point prompts (`masks/prompts/<take>.json`) → SAM 2.1 small on CPU, forward from each object's first prompt → `p47-masks/1` npz, one `np.packbits` row per 15 fps frame, with a SHA-256 digest for the manifest addendum. The R0.3 quality rule is `quality_ok`: frame 0 needs a non-empty mask; a non-empty frame after an empty one fails; exactly +50 % passes. `grid_overlay` writes labelled pixel grids for the point-placing agent. SAM tracks a synthetic moving square at IoU ≥ 0.8.
  - **SAM 2 on CPU fix.** At `2b90b9f` SAM 2 stores mask memories as bfloat16 (it assumes CUDA autocast). On CPU, an object prompted after frame 0 crashes in memory attention (bf16 against float32). A forward pre-hook casts the memory inputs back to float32. Nothing in the package is patched.
- **Cue detectors** (`seam/cues/`), each with a pure core tested on synthetic inputs.
  - `hands`: MediaPipe Hand Landmarker, VIDEO mode, debounced enter and leave. The model is in `models/` (gitignored); URL and SHA-256 are in MODELS.md. Only a negative MediaPipe test exists (no synthetic image reads as a hand); the first real take is the positive check.
  - `props`: onset and settle from mask area and centroid.
  - `torch`: bright-spot onset, aim and path. The baseline is registered to each frame by phase correlation, because the torch take is handheld. Without that, a shaken page reads as light. A glint is small and stationary, and is rejected.
  - `breath`: RMS + spectral flatness on the WAV; page flow is evidence, not a requirement.
  - `note`: Apple Vision OCR at the accurate level; tested on rendered print and two script-style fonts.
  - `sheet`: the `p47-cues/1` schema, the per-take detector defaults (the note take reads by OCR only, so the note is not fired twice), the orchestrator and the CLI.
- **OpenCV gotcha.** In OpenCV 5.0.0.93, `cv2.phaseCorrelate` overwrites both of its input arrays. The torch detector passes copies.
- **Laws: JSON, not YAML.** PyYAML is present only transitively (hydra-core → omegaconf), not as a declared dependency, and stdlib JSON gives canonical bytes for hashing. R0.9's `sealed/laws.yaml` therefore becomes `sealed/laws.json`. `seam/laws.py` validates `p47-laws/1`; the tests use fictional fixture laws.
- **Compiler** (`seam/compile.py`). A fixed prompt template. The target is named by its position on the page. One style lock per material. Each targeted event fires exactly one clause, in time order; context events (the hand setting a prop down) fire nothing and are traced with law null. The no-op prompt is a fixed constant. The output is byte-identical across runs.
  - Adapters follow R0.5 (aleph2 seed 1; kling_4 `auto_720p`, no seed; seedance2_5 edit, audio off, seed 1; gemini edit 640:360). aleph2 over 1,000 characters is a hard failure.
  - Every compiled request passes the hub client's offline `estimate` with no warnings. No live call was made; `runway.sh` was not run.
- **Sealing.** A compiled prompt contains law clauses, so a request compiled from laws in `sealed/` can only be written inside `sealed/`; the compiler enforces this. A leak guard test checks that no tracked file holds sealed text. The real `sealed/laws.json` (salted), the draft of the other 10 cells (`sealed/laws-draft-18.md`, for Aaron's approval before Gate R) and a dry run of every real request (`sealed/requests/dryrun/`) are all gitignored.
  - **Dry run.** The longest real aleph2 prompt is 719 characters of 1,000.
  - **gemini needs trimmed inputs.** On the 11 s takes, `estimate` refuses gemini edit (10 s limit), as the probe plan's 10 s trim expects.
- **Review fixes** (`f867439`, `a647087`):
  - The compiler trims inputs longer than gemini's 10 s limit to the first 10 s, recorded in `meta.trim`. All 36 dry-run requests now pass `estimate`.
  - The sealed guard is anchored to the repo's own `sealed/`.
  - The leak guard prints needle indices, not text.
  - 122 tests.
- **Quality-review fixes** (`0aed18e`, `b4820bc`, `8e86f75`):
  - Every detector threshold is a named constant with its reason; the values are unchanged.
  - The torch detector streams frames, buffering only the baseline's 5; a 300-frame test matches the old algorithm.
  - Clear errors for a missing model, checkpoint, sam2, Vision, ffmpeg or input video. The compiler CLI catches only CompileError, ValueError and OSError.
  - Prompt times now have 2 decimal places; the longest aleph2 dry-run prompt is 720 characters.
  - No NaN is allowed in evidence; the props settle check needs `MIN_AREA`; point prompts are bounded by the take's frame count.
  - 140 tests.
- **seedance2_5 at 720p** (`2205f27`). seedance's edit mode renders and bills at the input's tier, so a 1080p take cost 1,122 credits per 11 s (68 + 34 per second). `prepare_input_for_model` now sends it a 1280x720 copy: a frame-accurate re-encode named by the source's hash and recorded in `meta.scale`. It now costs 495 (30 + 15 per second), the budget's tier.
  - aleph2 stays at full resolution (flat price); gemini is trimmed to 10 s; kling_4 is sent as is.
  - kling_4's price was checked: it depends on duration and `auto_720p` only, and is the same for 1080p and 720p inputs.
  - All 36 dry-run requests pass `estimate`.
- **Trims and the at-home rule** (`d9fa384`, `70f1df3`).
  - The compiler's `--trim-to SECONDS [--start S]` and `--window START DUR` trim any model's input (R0.5: the probe's shared 10 s clip, and drafts of 4 s around the cue). A clip that starts after 0 shifts every clause time to clip time; the trace keeps the take time `t` and adds `t_clip`, and `meta.trim` records the window. A targeted event outside the window is an error.
  - Dry run, 56 requests, all passing `estimate`. Probe: aleph2 280, kling_4 151, seedance2_5 450, gemini 45 (926 in all, as the plan says). Drafts: 112, 61, 180, 45.
  - SAM tracks render masks forward only. Before the prompt frame the creature is still its drawing at home: those frames are valid, and A(t) is the dilated home (`regions.measured_region(..., at_home=True)`, one optional flag in sub-plan C's file). `quality_ok(..., start=prompt_frame)` treats the prompt frame as valid and runs the rule from the next frame.
- **Not done here.** The vision-model log (2.3; `vlm_log` stays empty), the curtain call's three-creature request, and masks and cues on real takes (after the shoot).

## 31 Oct 2026: seam-view sketch on synthetic data (early spike of Phase 10)

- **What.** `web/` is a Vite 8 + React 19 + TypeScript 7 seam view (explorer versions; Vitest, Playwright) that plays a synthetic take under a synthetic render with a wipe, a canvas overlay synced by `requestVideoFrameCallback` (gold tint kept, ink hatch limned, dashed outline for the creature), a drift and kept timeline with contact windows and neutral cue markers, the "kept / limned" legend with the gloss, and a text equivalent (kept %, and when). `useFrameClock.ts` and `Segmented.tsx` are copied from the StillDrawn Explorer, credited in a comment. Paper and ink themes, Geist from the explorer's font files, feedback-only motion, reduced motion starts paused.
- **Fixture.** `tools/make_sketch_fixture.py` draws a desk (page, glass, standing book, mug, pencil, ruler) with hand wobble and camera breathing, 10 s at 15 fps, 1280x720, H.264, in `web/public/sketch/`. The render adds an ink scribble that walks off the page and touches the glass from 4 to 6 s; lines near the glass are shifted and wobbled over that window. Seam cells follow R0.3 in simplified form (32 px cells, tolerant IoU at tau 2 by a radius-2 disk dilation, kept at 0.6 or more, limned under 0.3, none under 20 line pixels, creature cells marked) on the decoded frames. Output: `seam.bin` and `seam.json`. Result: kept 100 % outside contact, a low of 87 % at 5.1 s; drift 0.2 px outside contact, 0.6 px inside, codec floor 0.04 px. The script self-checks these.
- **seam.bin layout (the sketch's choice, to align with `seam/export.py`).** Frame-major, row-major, 40 x 23 cells, four cells a byte with cell i in bits 2*(i%4), each frame padded to a whole byte (230 bytes a frame); codes 0 none, 1 kept, 2 limned, 3 creature. The last row is 16 px tall.
- **Tests.** Vitest 13 passing (decoder layout and edge cases, summary, wipe clamp and keys, URL parameters). Playwright smoke at 1440 and 390 in light and dark, console clean, 8 passing. The e2e and promo runs use Google Chrome (`channel: "chrome"`) because Playwright's bundled Chromium cannot decode H.264.
- **Promo.** Stills, a 7 s loop and `docs/promo/README.md`. `?capture=1` exposes a tiny `window.__limn` hook for them.
- **Rules kept.** Nothing read from `sealed/`, no laws, no creature behaviour tied to a material, no TFF names, no generation, nothing deployed or pushed. The `.mp4` files are gitignored by the repo, so they were added by explicit path with `-f`.
- **Not done (Phase 10 proper).** The cue to law to clause link, the material switch, the other readouts, the real `export.py` contract, the design pass (`impeccable`, motion review), axe, `break-ui`. This is a sketch.

## 31 Oct 2026: Phase 0 enablers, name, laws

- **Name.** Limn the Room (`limntheroom`), cleared after a sweep of 15 candidates. Concept: hub `docs/p47/name-concept.md`.
- **Enablers built, each through spec and quality review:**
  - The hub's Runway client gained video-to-video (aleph2, kling_4, seedance2_5, gemini_omni_flash_1.1), ephemeral upload, an offline estimate, a `--yes` guard on every paid call, an fsynced spend log and `fetch` for recovery. 120 tests, all HTTP mocked, no live call made.
  - blindpanel v0.2 choice scales (2–12 nominal options; v0.1 lock hashes unchanged): 217 unit and 44 e2e tests on branch `v0.2-choice`, not yet merged or released.
- **Laws.** The eight rated laws passed Gate L. They are sealed and live only in the gitignored `sealed/`.
- **Next:** pick the creature design (Gate C1), make the creatures, write the capture protocol, shoot.

## 31 Oct 2026 — Phase 0.3: scaffold, environment, SAM 2 timing

**Done.** Repo created (`git init -b main`, repo-local identity `Aaron Smiles` / noreply address). README, STATUS (draft criteria), `.gitignore`, `pyproject.toml` with exact pins, `uv.lock`, `tests/test_env.py`, `tools/time_sam2.py`, `models/MODELS.md`. Nothing pushed; no GitHub repo. Nothing installed into `~/tools/ComfyUI/.venv`.

**SAM 2 supply-chain review** (facebookresearch/sam2, pinned to `2b90b9f5ceec907a1c18123530e92e794ad901a4`, main HEAD at 15 Dec 2024, "remove `.pin_memory()` in `obj_pos` of `SAM2Base`"). Read `setup.py`, `pyproject.toml`, `MANIFEST.in` and grepped the `sam2/` package:
- `setup.py` has no network calls, no subprocess, no post-install hooks, no custom install command. It declares dependencies and an optional CUDA extension (`sam2/csrc/connected_components.cu`).
- `pyproject.toml` build requirements are `setuptools>=61` and `torch>=2.5.1`. So a build installs torch into the isolated build environment (a large download, but from PyPI, not surprising).
- The CUDA extension is on by default; `SAM2_BUILD_CUDA=0` skips it. `SAM2_BUILD_ALLOW_ERRORS` defaults to 1, so build failures are swallowed with a printed warning.
- In the package, the only network use is `build_sam.py` `hf_hub_download`, reached only through the optional `build_sam2_hf` / `from_pretrained` paths, which this repo does not call. The checkpoint comes from the explicit file in `models/`.
- Odd but harmless: at runtime on CPU, SAM 2 prints "Skipping the post-processing step due to the error above ... CUDA extension" because `sam2._C` is absent, and falls back to no hole-filling post-processing. This affects small hole filling in masks only. It is expected with `SAM2_BUILD_CUDA=0`. Also the git dependency must be fetched from GitHub on a fresh `uv sync`; the lock records the commit.
- Verdict: nothing surprising. Checkpoint downloaded from the URL in `checkpoints/download_ckpts.sh` (`dl.fbaipublicfiles.com/segment_anything_2/092824/`); SHA-256 in `models/MODELS.md`.

**Environment.** Python 3.12, uv 0.11.8. `uv sync` resolved cleanly with `SAM2_BUILD_CUDA=0`. `uv run pytest`: 2 passed (all imports, including `Vision`; SAM 2.1 small video predictor builds on CPU).

**SAM 2.1 small CPU timing** (`tools/time_sam2.py`, Apple M5, 4 torch threads, synthetic 1280x720, 150 frames, moving circle, one click): init (frame load and resize) 2.7 s; propagation 227.0 s for 150 frames = **1.51 s per frame**. Per-frame time was flat at about 1.2-1.5 s with bursts to 3 s (thermal or contention). A 10 s 15 fps take costs about 4 minutes per tracked object on CPU. Acceptable for batch masking; not interactive.
