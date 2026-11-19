# Limn the Room — status
Card: P47 · Started: 30 Oct 2026 · Public slug: limntheroom (cleared 31 Oct 2026)

## Criteria (registered in PREREGISTRATION §1, 10 Nov 2026)
- Success:
  1. A stranger can wipe any take and see what was kept, what was redrawn and which cue fired which law.
  2. 3–5 cold raters (two in person, the rest remote; call 115; in the event all five rated remotely, call 162) rate the eight renders (on the failure path, the glass take ×3: D3), with the hit rate per law reported against a still baseline, with intervals, null or not.
  3. The film (60–120 s, ending on the drawing still on the page) and the thesis are published and linked from the portfolio.
  - Also: registration is public before any generation; the contact hypothesis is reported whatever it shows.
- Kill rule: no nameable reaction in 3 of 4 draft takes after two rounds → Gate K. Process kill: no probe arm, nor the keyframe rescue, brings the drawing to life out of its place on the page → Gate K.
- Budget: 9 focused days (the card says 8); a £50 target, up to £60 approved for the worst case only (a seedance final needs a fresh go); every paid call logged.

## Rounds
| # | Date | What was tried | Result | Kept? | £ |
|---|---|---|---|---|---|
| P1 | 10 Nov | The probe: four arms on the glass take's first 10 s | No final model. Rubric 1 passes: 1 of 3 rated arms (seedance2_5). The gate passes: 1 of 3 (aleph2). gemini was refused by the API | — | 851 credits ≈ £6.70 |
| R | 10 Nov | The keyframe rescue (D1): aleph2 with two gen4_image keyframes | Rubrics 1–2 pass; the gate fails narrowly (lag −2, 89.3 % of frames): Gate K | — | 296 credits |
| K | 10 Nov | Gate K: the failure write-up, the glass take ×3 on seedance2_5 (D2), then the §16 re-renders | None passes the gate: gold aligned but one frame short; ink and paper misaligned | the re-renders are the study's | 3,312 credits |
| A | 18 Nov | After the study (Aaron's go, call 178): the five unreached cues on seedance2_5 from their Gate R requests, and the curtain call (two seeds) from its hand-written request | Unregistered, unrated. Every cue performs; the five hold the room in every frame they return and fail on length only; curtain seed 2 kept, seed 1 reframed | seed 2 bow; all five | 3,949 credits ≈ £31 |

## Run log
| Date | Task | From | To | Why |
|---|---|---|---|---|

## Spend: 8,408 credits (≈ £66): the study 4,459 (≈ £35) of £50; after the study 3,949 (≈ £31) on Aaron's go · £ per keeper: n/a
- Cap (Aaron, 10 Nov): aim to stay under £50; up to £60 is pre-approved for the worst case only. The after-study renders took the card past £60 by his go (call 178, 18 Nov).
- £0 elsewhere: the machine rater on the subscription; Hume never read (its TTS API retired 13 Nov).

## Links
- Master plan and calls file: in the studio's private hub (outside this repo); the LOG summarises every ruling.
- Demo: https://limntheroom.studionephele.com (the seam view; `?after=hand` for after the study)
- Films: https://media.studionephele.com/limntheroom/films/v1/film-16x9.mp4 (the study, 99.1 s) · https://media.studionephele.com/limntheroom/films/v1/after-16x9.mp4 (after the study, 58.5 s); 9:16 and .srt beside each
- Thesis: `THESIS.md` · write-up: `docs/write-up.md` · site: https://studionephele.com/work/limntheroom/ (v1.50)

## Gates
- N, T, L passed (31 Oct). **C1 passed 3 Nov: c05** (loaf-bodied blob on four stub legs); c03 fallback. C2 done: c05 made in ink, gold paint and cut paper, and scanned (`creature/scan/`).
- **S passed 9 Nov** on the printed terrazzo (calls 127–131). The chosen takes are t01f, t02e, t03c, t04d, t05c, t06c and t07e. The plain-desk takes are superseded (`raw/plain-desk/`).
- **Gate R, 10 Nov 2026.** The registration was reviewed twice before the push: an adversarial review (call 135) and an independent gate review in two rounds (call 136), each taken in full (LOG, 10 Nov night).
  - Filled in: the take masks and contact sheets (seen 9 Nov), ρ, D0, κ_codec, m, the shift control and its room share, the lag floor (kept at 1.0), the versions, the hashes and the sealed files.
  - Settled: the picker stride (3, stepping up only to fit).

## Next
- **19 Nov: steps 9 (in part) and 10 done** (call 180). Left: the author runs the hub's step 9 wizard (exposed schemas, key rotation); then drop `blindpanel`, check the new key, delete `tools/limntheroom-host.env.op`.
- **18 Nov: close step 8 done** (hub calls 166–179): write-up, seam view, two films, thesis and site entry public. Next: step 9 (take-down and key rotation) on Aaron's explicit go; step 10 (records, planner final cost, CV bullets); the plain-words proofread and real-reader test (soft to-dos).
- **D3 done (call 143):** `rating/prepare.py build --failure-path` builds the glass take ×3 study; `analysis/ratings.py --study` scores it. The five studies (`rs-r1`…`rs-r5`) are built and verified locally. The host is deployed (call 144: a neutral address, its own database schema; the address stays private until close). The schema is applied, the live check passed and addendum A2 is pushed (call 145). Raters (call 146): `rs-r2`, `rs-r4`, `rs-r5`, `rs-r6`, `rs-r7`, addendum A2b pushed; Aaron's own `rs-r1` session is not analysed. Invitations sent 12 Nov (Gate RT, call 148): the window closes at the end of 19 Nov. Declarations in: R6, R2, R4, R7, R5. Sessions: all five raters in (`rs-r6`, `rs-r4`, `rs-r7`, `rs-r5`, `rs-r2`; calls 149, 152, 154); the window closed early on 17 Nov (call 155, a reported departure: all five in, no answers read) and the address is offline; declarations matched (call 156). **17 Nov (calls 157–158):** the exports are in and hashed on arrival (one session per study; no answer read); deviation D4 lets the machine rater's two study rounds rate the same three items. Then (calls 159–162) the machine rater and addendum A3, the sealed files committed locally, the manifest check and the analysis (five raters, all remote; results in `LOG.md` and `analysis/out/`); an expert read twice (accept with changes) and Aaron's go; **unsealed publicly 17 Nov** (`33efcb9`; a fresh clone checks 415 rows OK) and the private history published as a bundle on the release `close`. Next: close step 8 (the write-up, the seam view, the film, the thesis, the plain-words layer), then 9–10. The display-only seam view and the write-up follow.
- **The probe (Gate P1):** four arms on the glass take's first 10 s, each gated against that span; the blind rater rates them (round `probe`); then the model decision (Gate P2), the no-op null, κ_keep and the shift control rerun.
- **Then:** drafts (Gate D), finals (Gate F), the render masks, addendum A1 per render, the lines job and H.
- **Before the study:** blindpanel v0.2.0 needs its schema upgrade on the live database (`sql/schema.sql`); the throwaway live check must answer a Q2 option numbered 6 or higher and find it in the export.

## Clearance log
- **17–18 Nov 2026, close step 8** (publish-clearance on every piece, hub calls 169, 174, 179):
  - the write-up: three independent gate reviews (the last ACCEPT ALL) and clearance; pushed `8cf0660`, corrected `22f35fc` (call 177), LOG `5aa72f8`;
  - the seam view and thesis: PASS AFTER FIXES (call 174); thesis pushed `e8b0839`; seam view live on the personal Vercel project, scan-checked on what ships;
  - both films: PASS AFTER FIXES (call 179); on the media host under `limntheroom/films/v1/`, checked byte for byte;
  - the site entry: facts rule, identifier scan and 1,768 unit tests; production v1.50.
- **10 Nov 2026, the site (studionephele.com v1.30, Worker `334114ee`):** the Work entry now carries the registration and the probe.
  - Three real stills: the take, and single frames from the Aleph 2 and Seedance 2.5 probes, never re-encoded.
  - Links: the registration and its Software Heritage copy.
  - P47's 58 sealed needles find nothing in the entry; no law, label or Q2 option (§2). The identifier scan is clean.
  - Under Aaron's go (call 136a, b): raters never see the site; his hand appears in the take still.
- **10 Nov 2026, the registration push** (publish-clearance, all five sections pass):
  - the identifier scan over the public tree: clean;
  - one orphan commit, so no history;
  - no media, sealed, raw, take or cache file (276 files);
  - 58 sealed needles: no hit in any file or the commit message;
  - no private or uncleared names; fonts under OFL;
  - the name was cleared 31 Oct and the GitHub name was free;
  - manifest: 360 rows, all verified.
  - Pushed to github.com/aaronlsmiles/limntheroom as `main`, tag `registered` on `945c54d`; private head `045efe8`.
- **10 Nov 2026 (Aaron):** his hand and wrist tattoo, as seen in the takes (t02e, t05c, t06c), are cleared for the website. Raters never see the site. **17 Nov (call 162):** the clearance covers the public repository too (the takes' input copies, published at close).
- 2026-11-03: studionephele.com now carries the rehearsal demo (three stills, an 11 s silent film; site 793111c). Scan clean on the entry and the data; labelled "synthetic, not results"; Aaron waived the cue and contact hold (no rater has the address; hub call 116).
- **3 Nov 2026:** the studionephele.com Work entry "Limn the Room", a list line with one frame (site commit `9b0b723`; frame `docs/promo/limn-seam-wipe.png`, `24603ea`).
  - Identifier scan: clean.
  - Content rules: pass. The frame is script-drawn (own). It is a wipe-only early frame with no creature, cue or contact in shot. The line names no behaviour and carries the "synthetic sketch, not results" label.
  - The name was cleared 31 Oct.
  - Final look at 1440 light and 390 dark: clean.
  - Site checks: 1388 unit and 911 e2e tests pass.
  - The earlier promo stills (`limn-seam-1440x900-*`, the loop) are **not** for public use before the rating closes: their timeline shows a cue and contact.
