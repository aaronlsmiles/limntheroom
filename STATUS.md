# Limn the Room — status
Card: P47 · Started: 30 Oct 2026 · Public slug: limntheroom (cleared 31 Oct 2026)

## Criteria (registered in PREREGISTRATION §1, 10 Nov 2026)
- Success:
  1. A stranger can wipe any take and see what was kept, what was redrawn and which cue fired which law.
  2. 3–5 cold raters (two in person, the rest remote; call 115) rate the eight renders, with the hit rate per law reported against a still baseline, with intervals, null or not.
  3. The film (60–120 s, ending on the drawing still on the page) and the thesis are published and linked from the portfolio.
  - Also: registration is public before any generation; the contact hypothesis is reported whatever it shows.
- Kill rule: no nameable reaction in 3 of 4 draft takes after two rounds → Gate K. Process kill: no probe arm, nor the keyframe rescue, brings the drawing to life out of its place on the page → Gate K.
- Budget: 9 focused days (the card says 8); a £50 target, up to £60 approved for the worst case only (a seedance final needs a fresh go); every paid call logged.

## Rounds
| # | Date | What was tried | Result | Kept? | £ |
|---|---|---|---|---|---|
| P1 | 10 Nov | The probe: four arms on the glass take's first 10 s | No final model. Rubric 1 passes: 1 of 3 rated arms (seedance2_5). The gate passes: 1 of 3 (aleph2). gemini was refused by the API | — | 851 credits ≈ £6.70 |

## Run log
| Date | Task | From | To | Why |
|---|---|---|---|---|

## Spend: 851 credits (≈ £6.70) of £50 · £ per keeper: n/a
- Cap (Aaron, 10 Nov): aim to stay under £50; up to £60 is pre-approved for the worst case only.

## Links
- Master plan and calls file: in the studio's private hub (outside this repo); the LOG summarises every ruling.
- Demo · film · thesis · repo: not yet

## Gates
- N, T, L passed (31 Oct). **C1 passed 3 Nov: c05** (loaf-bodied blob on four stub legs); c03 fallback. C2 done: c05 made in ink, gold paint and cut paper, and scanned (`creature/scan/`).
- **S passed 9 Nov** on the printed terrazzo (calls 127–131). The chosen takes are t01f, t02e, t03c, t04d, t05c, t06c and t07e. The plain-desk takes are superseded (`raw/plain-desk/`).
- **Gate R, 10 Nov 2026.** The registration was reviewed twice before the push: an adversarial review (call 135) and an independent gate review in two rounds (call 136), each taken in full (LOG, 10 Nov night).
  - Filled in: the take masks and contact sheets (seen 9 Nov), ρ, D0, κ_codec, m, the shift control and its room share, the lag floor (kept at 1.0), the versions, the hashes and the sealed files.
  - Settled: the picker stride (3, stepping up only to fit).

## Next
- **Waiting on Aaron (call 138): a deviation for the rescue's rater round.** The probe ran (10 Nov): no final model, and the draft model is seedance2_5. The registered rescue is blocked because no rater round exists for it. Options and the recommendation are in call 138.
- **The probe (Gate P1):** four arms on the glass take's first 10 s, each gated against that span; the blind rater rates them (round `probe`); then the model decision (Gate P2), the no-op null, κ_keep and the shift control rerun.
- **Then:** drafts (Gate D), finals (Gate F), the render masks, addendum A1 per render, the lines job and H.
- **Before the study:** blindpanel v0.2.0 needs its schema upgrade on the live database (`sql/schema.sql`); the throwaway live check must answer a Q2 option numbered 6 or higher and find it in the export.

## Clearance log
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
- **10 Nov 2026 (Aaron):** his hand and wrist tattoo, as seen in the takes (t02e, t05c, t06c), are cleared for the website. Raters never see the site.
- 2026-11-03: studionephele.com now carries the rehearsal demo (three stills, an 11 s silent film; site 793111c). Scan clean on the entry and the data; labelled "synthetic, not results"; Aaron waived the cue and contact hold (no rater has the address; hub call 116).
- **3 Nov 2026:** the studionephele.com Work entry "Limn the Room", a list line with one frame (site commit `9b0b723`; frame `docs/promo/limn-seam-wipe.png`, `24603ea`).
  - Identifier scan: clean.
  - Content rules: pass. The frame is script-drawn (own). It is a wipe-only early frame with no creature, cue or contact in shot. The line names no behaviour and carries the "synthetic sketch, not results" label.
  - The name was cleared 31 Oct.
  - Final look at 1440 light and 390 dark: clean.
  - Site checks: 1388 unit and 911 e2e tests pass.
  - The earlier promo stills (`limn-seam-1440x900-*`, the loop) are **not** for public use before the rating closes: their timeline shows a cue and contact.
