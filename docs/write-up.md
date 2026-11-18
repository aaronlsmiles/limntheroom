# Limn the Room: the failure write-up

*Results as registered (PREREGISTRATION §19, §21 step 10): verdicts and deviations, no new analyses. 17–18 November 2026.*

> **EXPLORATORY.** Every number here is exploratory (§22). Five raters rated three clips. No result here is a confirmatory test, and none is reported as one.

## What was registered, and what this is

On 10 November 2026, before any generation, this study registered one question: can a video model bring a hand-made drawing to life on its real page, make it answer a real object beside it by the laws of its own material, and keep the rest of the room as it was? The registration (`PREREGISTRATION.md`, tag `registered`, archived by Software Heritage) fixed the renders, the alignment gate, a hypothesis H about where the room drifts, a cold rating study and the kill rules.

The study reached Gate K by §14's rescue rule: no probe arm qualified as the final model, and the keyframe rescue came to life but failed the alignment gate. (§19's process kill, as worded, fires only if no render comes to life out of its place on the page; two did, so it never fired.) At Gate K the author chose the registered alternative to stopping:

> **At Gate K** Aaron chooses between stopping and the failure write-up: the glass ×3 rendered for the seam view, rated as registered, and written up as why the model ignores the cues.

This document is that write-up. It quotes the registered phrase, "why the model ignores the cues", because the registration asks for it. The data do not support it. **The models did not ignore the cues.** What they show instead is below.

## Verdicts

| Registered item | Verdict |
|---|---|
| **H** (drift outside the creature peaks at contact, §13) | **Not testable.** No glass render passed the alignment gate (§6), so none was measured, and H needs at least four testable renders. Under D2 the failure path has three renders at most. |
| **Success criterion 1** (a stranger can wipe any take and see what was kept, what was redrawn and which cue fired which law) | **Not met.** Nothing was aligned, so nothing was measured as kept or redrawn. The seam view shows the three glass renders for display only, labelled "not aligned, not measured". |
| **Success criterion 2** (3–5 cold raters, two in person and the rest remote, rate the eight renders; hit rate per law against a still baseline, with intervals, null or not) | **Met as deviated** (D3; all five remote): five raters rated the failure path's three items, and every hit rate is reported with its still baseline, Wilson 95 % interval and n. The registered eight renders were never made, and no rater rated in person (departure 6). |
| **Success criterion 3** (the film and the thesis, published and linked from the portfolio) | To follow, after this write-up. |
| **Kill rules** (§19) | The card's kill rule was never reached: there were no draft rounds. The process kill did not fire, because two renders came to life. Gate K was reached by §14's rescue rule, after the rescue failed the alignment gate (hub call 140). |

## What happened, in registered order (§21)

All renders are of one take, the glass take (`t01f`): a phone take of the page with the three creatures on it, a glass ramekin of water set down beside them, cue at 3.6 s. Gate records are in `runs/probe/`, `runs/rescue/` and `runs/gate/`; every paid call is a row of `runs/runway-calls.jsonl`.

### 1. The probe (Gate P1, §14)

Four arms on the take's first 10 s, the ink creature acting. The blind rater agent answered the rubric from a contact sheet of each render.

| Arm | Output | Alignment gate (§6) | Came to life, out of its place (rubric 1) | Named a reaction (rubric 2) |
|---|---|---|---|---|
| aleph2 | 10.0 s | **pass**: lag 0, every frame passes | no | no |
| seedance2_5 | 9.71 s from a 10 s input | fail, on duration only: lag −1, 97.3 % of frames pass | **yes** | **yes**, to the glass |
| kling_4 | 4.04 s | fail: lag 2, no frame passes, short | can't tell | no |
| gemini_omni_flash_1.1 | rejected by the API, nothing billed: the registered request sends `ratio` 640:360 in edit mode, which the API accepts only in reference mode | counts as failing (§14, call 136) | — | — |

By §14 no arm qualified as the final model, and seedance2_5 became the draft model.

### 2. The keyframe rescue (§14; deviation D1)

One aleph2 run on the probe's input, seed 1, with two gen4_image keyframes at 4.1 s and 4.6 s made by the registered recipe. The blind rater said it came to life and reacted to the glass (rubrics 1 and 2 pass). The gate failed it narrowly: **lag −2 analysis frames** (the gate allows ±1) and **89.3 % of frames pass** (the gate needs 90 %). The keyframes had re-composed the scene: the page larger and shifted, the framing moved. By §14 the rescue fails, so Gate K.

### 3. Gate K, and the glass take ×3 (§19; deviation D2)

The author chose the failure write-up. The registration did not name its model, so D2 filled the gap with seedance2_5, the registered draft model, using its three glass requests exactly as hashed at Gate R: one render per creature (ink, gold, paper), each of the same take.

| Render | First render (seed 1) | Re-render (§16, seed 2), the one rated |
|---|---|---|
| t01-ink | lag 0, 21.9 % of frames pass, short | lag 0, **0 %** of frames pass, short |
| t01-gold | lag 0, **99.5 %** of frames pass, short by the last analysis frame | lag 0, **99.5 %** of frames pass, short by the last analysis frame |
| t01-paper | lag 0, **99.5 %** of frames pass, short by the last analysis frame | **lag 5**, 0 % of frames pass, short |

Every one of the six came back 12.708 s from the take's 12.767 s, about 0.06 s short, so all six fail the gate on duration. By §16 each first render was re-rendered once with seed 2, and the re-render replaces the first for the study whatever its outcome. **No glass render passes the gate.** The three re-renders are what the raters saw.

## "Why the model ignores the cues": what the data say instead

The registered phrase assumed a model that would not react. The models reacted. Across the probe and the rescue, the two renders the blind rater said came to life both reacted to the right cue, the glass. The failure is in time and space, not in attention:

- **At the probe and the rescue, every render that brought the drawing to life drifted just outside the timing gate, and the one that kept time did not animate it.** aleph2 without keyframes kept the room exactly (lag 0, every frame) and left the drawing on the page. seedance2_5 brought it to life and came back 0.29 s short. aleph2 with keyframes brought it to life and lagged two analysis frames, with 89.3 % of frames aligned.
- **On the glass take ×3, seedance2_5 returned every clip about 0.06 s short of its input, and its alignment varied by seed.** Three renders in six (gold on both seeds, paper on seed 1) kept the room aligned in every frame they had and missed on duration alone; of the three re-renders the raters saw, only gold held. The others ran from 21.9 % of frames aligned down to none, and the paper re-render lagged five frames.

Some misses were narrow and some were not. The probe's seedance2_5 arm was 0.29 s short with 97.3 % of frames aligned; the rescue missed by one frame of lag and 0.7 percentage points of aligned frames; the gold renders and the first paper render missed by one analysis frame of duration. The ink and paper re-renders, two of the three the raters saw, missed by far: no frame aligned. That is the finding: on this take, the models that answered the cue did not keep the room's time and place while they did it.

**A word on what "drift" measures.** Drift here is line structure that moved; it is not a judgement that the model erred, and shadows, reflections and ripples count as drift (§22). Line structure is a proxy for the room, not the room itself.

## The rating study (§17; deviation D3)

Five cold raters (`rs-r2`, `rs-r4`, `rs-r5`, `rs-r6`, `rs-r7`), one session each, all remote. Each saw the three ringed stills first (the baseline: "If the ringed drawing came alive here, what would it react to?", "What would it do?"), then the three clips (the first 12.0 s of each re-render, muted, beside its ringed still: "What did the creature react to?", "What did it do?"). The author's own session (`rs-r1`) is kept, reported as a test and not analysed (§17: he knows the laws and sent no declaration).

**The laws under test** (published at close, `sealed/LAWS.md`):

| Creature | Law (the Q2 answer) | What it was asked to do |
|---|---|---|
| ink | "Backed away from it" | walk to the foot of the glass, dip one toe, recoil as its wet ink starts to run, then back away and keep its distance |
| gold | "Looked at its reflection" | walk up to the glass, rest its front feet against it and admire its own reflection |
| paper | "Wilted" | lean against the glass, then slowly soften and wilt as if damp |

The twelve Q2 options, in display order: Was blown along · Shivered · Did what it said · Wilted · Looked at its reflection · Drank from it · Hid from it · Climbed onto it · Backed away from it · Turned towards it · Nothing in particular · Can't tell.

### The registered run first (§23)

`analysis/ratings.py` as registered (`analysis/out/ratings.json`) scores the three glass laws below, and reports the five laws that have no item on the failure path (ink.light, ink.pen, ink.breath, ink.note, ink.hand) at n = 0. The D3 run (`--study`, `analysis/out/ratings-study.json`) gives the same three laws exactly, number for number, and lists those five as not in the study.

### What it did: Q2, the still baseline Q2b, and the law hit

Exploratory; n = 5 raters for every cell; Wilson 95 % intervals.

| Glass take | Clip Q2 (what it did) | Still Q2b (baseline) | Q2 clip − still | Law hit (Q1 and Q2 both right) |
|---|---|---|---|---|
| ink, "Backed away from it" | 2/5 (0.12–0.77) | 0/5 (0–0.43) | +0.4 | 2/5 (0.12–0.77) |
| gold, "Looked at its reflection" | **0/5** (0–0.43) | 0/5 (0–0.43) | 0.0 | 0/5 (0–0.43) |
| paper, "Wilted" | 2/5 (0.12–0.77) | 0/5 (0–0.43) | +0.4 | 2/5 (0.12–0.77) |

- No rater guessed any law from the still (0/5 on every Q2b), so a law hit's still counterpart is 0/5 too.
- Two of five raters named the ink creature's law and two of five the paper creature's. None named the gold creature's: the render that kept the room best is the one whose behaviour nobody read.
- The intervals are wide, from 0.43 to 0.65 across, and overlap on every row. **No paired test is reported:** with five raters the only paired test of clip against still (an exact McNemar test) cannot reach a two-sided p below 0.0625, even if all five moved the same way.

### What it reacted to: Q1, the still baseline Q1b

| Glass take | Clip Q1 (reacted to) | Still Q1b (baseline) | Q1 clip − still |
|---|---|---|---|
| ink | 4/5 (0.38–0.96) | 1/5 (0.04–0.62) | +0.6 |
| gold | 5/5 (0.57–1.00) | 2/5 (0.12–0.77) | +0.6 |
| paper | 5/5 (0.57–1.00) | 1/5 (0.04–0.62) | +0.8 |

**Q1 is at its ceiling by construction.** On the failure path every right Q1 and Q1b answer is the same cue, the glass (D3), so a rater who answers "the glass" every time scores 100 %. Q1 shows that the raters saw something answer the glass in the clips; it cannot show that they read a law. Q2 and the law hit carry the result.

**Agreement** (Fleiss' κ over the three items, option labels as categories): Q1 −0.07, Q2 0.08, Q1b −0.15, Q2b −0.14. With every right Q1 answer the same option, near-unanimous answers give κ near zero, so these values say little about agreement on this design.

### The machine rater, reported apart (§17, secondary)

The blind rater agent (`agents/blind-cue-rater.md`: Claude Opus 5.5, effort high, read-only, one folder) rated the same three items before unsealing: the stills in one call, then contact sheets of the clips (two frames a second over each rating copy) in a fresh call with no memory of the first. Both rounds were valid on the first attempt (addendum A3; `analysis/out/ratings-machine.json`, `ratings-machine-study.json`).

It answered the glass on every clip and every still (Q1 and Q1b right on all three, n = 1 each), and got Q2 and Q2b wrong on all three. It is one rater, so κ is not defined and nothing is pooled with the people.

## Departures and deviations

Every change to a registered rule, file or procedure after Gate R is in PREREGISTRATION §24, with its diff, what had been seen and who decided. Departures that changed no rule are listed with them. "Call" means a numbered decision in the studio's private calls file (a "hub call"); `LOG.md` summarises each one.

1. **D1, 10 Nov (deviation):** a sixth blind-rater round, `rescue`, so the registered keyframe rescue could be judged by rubric 1 as §14 requires (call 139).
2. **D2, 10 Nov (deviation, filling a gap):** the failure path's model, seedance2_5, with the requests hashed at Gate R; chosen after the probe and rescue had been seen (call 141).
3. **D3, 10 Nov (deviation):** the failure path's rating study has three items, not eight; `ratings.py --study` scores it, beside the registered run (call 143).
4. **The CLI length option (disclosed with D3):** `rating/prepare.py build` on the command line still demands a length, though §17 registers "no length given". The study was built as the registered test builds it (a placeholder parsed, then cleared), so the registered rule set the length: the first 12.0 s.
5. **D4, 17 Nov (deviation, a bug fix to registered code):** the blind-rater code's guard against a second round over the same items also refused the study's own baseline-then-clips pair; it now skips that one pair and nothing else (calls 157–159).
6. **No in-person raters:** §1 and §17 planned two raters in person on the author's Mac and the rest remote. All five rated remotely, each on their own device from their own link (call 162).
7. **The window closed early:** §17 registers 7 days from the first invitation (12 Nov, so to the end of 19 Nov). It closed on 17 Nov at 11:21 UTC, once all five recruited raters (the registered maximum) had completed a session, and before any answer was read (call 155).
8. **Session times from the database's API log:** the rating kit stores only the day a session arrives. The start times used for the declaration check were taken from the database provider's API edge log (each insert's time, less the session's own recorded duration), not from the kit (call 150).
9. **A Q2 label printed in the controller's session:** after the window closed and before the analysis, a text search matched a word inside one of the twelve Q2 option labels and printed that label in the controller's session, with no item, answer or key entry beside it. Every rater had already finished, and the machine rater runs in a separate session that cannot see the controller's (call 157).
10. **The probe's and rescue's rater files hashed only at close:** their answers and folder maps had no manifest rows. Their hashes were added at close; their ledgers hash the agent's raw reply, which lives only in unpublished session transcripts, so the row added at close is their only hash chain (call 162).
11. **The declarations:** Each rater's written declaration was checked by the author against their session's start time and came first; the replies are kept privately to protect the raters' anonymity.

Also reported, not departures: the gemini probe arm's registered request was rejected by the API on a parameter (`ratio` in edit mode), not on its content, and counts as failing under §14's rule (call 136); the author's own session is not analysed (§17); after close the leak guard's two tests fail on every clone by design, and two vendor checks fail on the author's machine because the studio's Runway client changed after this study's last call (README).

## What was never made

The study stopped at Gate K, so these registered steps never ran: the no-op null and κ_keep, the draft rounds, the eight finals (five of the eight rated laws were never rendered), the render masks, the lines job, the hand and note measures, H, and the curtain call. Nothing was measured on the three glass renders, because none was aligned.

## Unregistered observations

*Post-hoc, read by eye after unsealing; not results under §21 step 10. No test, no claim. Kept because they change how the tables above should be read, and because they shape the next study.*

- **The Q2 hits on ink and paper are the same two people.** `rs-r5` and `rs-r7` each named the ink creature's and the paper creature's behaviour on the clips, and both answered gold with "Nothing in particular". `rs-r2`, `rs-r4` and `rs-r6` missed Q2 on every clip. So the two 2/5 rows are two raters, not four independent hits. "Climbed onto it" was the commonest wrong clip answer (5 of 15) and was never right.
- **Answers on the stills clustered by rater, not by item.** On the stills, one rater gave the same pair of answers to all three; another answered "Can't tell" to all six still questions; a third answered "Can't tell" or "Nothing in particular" to all six. A per-rater response style is part of why κ sits near zero.
- **The stills did not give the laws away,** even to someone who knows them: the author's own session (`rs-r1`, not analysed) answered "Drank from it" on all three stills.
- **The machine rater never named a right Q2:** "Drank from it" on the ink clip and still, "Backed away from it" (the ink creature's law) on the paper still, "Can't tell" otherwise.
- **For the next study:** analyse at rater level, and register a check for per-rater response style.

## Spend

4,459 Runway credits (about £35 of the £50 target): probe 851, keyframes 16, rescue 280, glass ×3 1,656, re-renders 1,656. The machine rater ran on the author's Claude subscription, with no per-call charge. The study ran on a neutral address, with no project word in it, on free hosting tiers; it went offline on 17 Nov.

## Check it yourself

- The registration: `PREREGISTRATION.md`, `MANIFEST.sha256`, tag `registered`; `REGISTRATION.md` gives the Software Heritage snapshots and the private history's bundle on the release `close`.
- A clone checks its published files with `shasum -a 256 -c --ignore-missing MANIFEST.sha256` (415 rows).
- The ratings: `sealed/exports/rs-rN/ratings.csv` (one per rater), `sealed/answer-key.json`, `sealed/rating-manifest.json`. The registered run, then D3's, each byte-identical to the files in `analysis/out/`:

  ```bash
  uv run --frozen python analysis/ratings.py --key sealed/answer-key.json \
    --rater rs-r2=sealed/exports/rs-r2/ratings.csv --rater rs-r4=sealed/exports/rs-r4/ratings.csv \
    --rater rs-r5=sealed/exports/rs-r5/ratings.csv --rater rs-r6=sealed/exports/rs-r6/ratings.csv \
    --rater rs-r7=sealed/exports/rs-r7/ratings.csv --out /tmp/ratings.json
  # D3's run: the same line with --study sealed/rating-manifest.json and --out /tmp/ratings-study.json
  ```
- The gate records: `runs/probe/`, `runs/rescue/`, `runs/gate/`. The process, call by call: `LOG.md`.
