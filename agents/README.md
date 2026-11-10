# The blind agents: who sees what, and in what order

Two read-only agents work for this study. Neither is shown a law, a behaviour, a rater label paired with a take, a prompt, a take name or a material name. Each call gets one folder, directly under `~/.blind` under a random code (no path names the project, a take or a material), and a frozen brief. Each call is a fresh, bare session, so nothing carries over from one folder to the next.

| Agent | Definition | Briefs | Used for |
|---|---|---|---|
| `blind-frame-picker` | `blind-frame-picker.md` | `briefs/prompt-frame.md`, `briefs/take-mask-points.md`, `briefs/render-mask-points.md` | the render mask's prompt frame; the take-mask and render-mask point prompts |
| `blind-cue-rater` | `blind-cue-rater.md` | `sealed/briefs/*-rater.md`, rendered from `briefs/rater-*.md` at Gate R | the probe and draft ratings; the machine rater (both study parts) |

`briefs/human-rater-study.md` records everything a human rater is sent and shown. A test holds it to `rating/prepare.py` and to the invite text in PREREGISTRATION §17.

**One agent for frames and points, separate from the rater.** Picking the prompt frame and placing points share one contract: Read only, one folder, numbered stills, a JSON answer, one attempt. So one definition serves three briefs. Each runs as a separate call: the frame pick sees the render's stills, and the point placer then sees only the picked frame. The rater stays a separate agent so that its ledger (addendum A3) is its own, and so that no brief listing the Q2 options ever reaches the agent that makes the masks.

**What a session can hold (hub calls 129–130).** Claude Code sends each image the agent reads as a quality-90 JPEG. Past about 16 MB of those in one folder, earlier images drop out of the session and the agent re-reads until it runs out of turns: the first textured take lost both its attempts that way. `blind.write_folder` therefore estimates every folder's images exactly as the session receives them and refuses one over `PAYLOAD_BUDGET` (16 MB) before anything is written or logged, so an oversized folder never uses an attempt. Check a new kind of folder with `tools/dry_run_blind.py` (outside the ledgers) first; `--take-video` runs the take brief on a real analysis copy.

## How a call runs: `seam/dispatch.py run --code <code>`

A subagent dispatched from a project session would inherit that session's context (the studio CLAUDE.md, AGENTS.md and memory, which name the project). So every blind call is a bare `claude -p` session instead:

- **Working directory:** the folder itself.
- **System prompt:** the vendored agent file is the only system prompt (`--agents`/`--agent`).
- **Tools:** Read is the only tool, with no `--allowedTools`. `--restricted` confines it to the folder and ignores user, project and local settings, so no hooks or plugins load. `--strict-mcp-config` drops every MCP server, and `--disable-slash-commands` every skill. A live canary on 3 Nov showed both layers: the real agent declined to read a sibling folder's file, and a permissive probe that tried was refused by the harness ("…is outside … --restricted confines the file tools to the working directory").
- **Model:** pinned, with the agent's maxTurns.
- **Session id:** fresh, and logged before the call.

A trial run on 3 Nov loaded no CLAUDE.md or memory at all. The only context files allowed are the user's global `~/.claude/CLAUDE.md`, and any other fails the attempt.

**Two records of each call.**
- **The stream** (`--output-format stream-json`) is written by `dispatch.py` itself, by exclusive create, to `blind/transcripts/<code>.jsonl`: the audit transcript.
- **Claude Code's session store** is the cross-check, since it alone holds the dispatch text, the agent and the system prompt. It is copied (exclusive create, `<code>.store.jsonl`) and then removed from `~/.claude/projects` in a `finally`: the Mem indexer walks that folder, and a rater session's reads hold the sealed Q2 options.

The dispatcher never prints the answer.

## The ledger: nothing can be chosen

Every call site has a committed ledger:
- `logs/prompt-frame/<render>.json`;
- `logs/take-mask-points/<take>.json`;
- `logs/render-mask-points/<render>.json`;
- `logs/rater/<round>.json`.

1. **Preparing a folder** appends a `prepared` attempt (code, dispatch hash, inventory hash, time) before anything can be dispatched. A new folder is refused while any attempt is unrecorded, and every prepared folder counts against the two attempts.
2. **Dispatching** marks the attempt `dispatched`, with the session id. Then one of three outcomes:
   - `recorded`: the folder's `record` checked it (valid or not).
   - `dispatch_failed`: only when nothing reached the API (no init, model or result event in the streamed bytes, and a non-zero exit). It uses one of the two attempts.
   - `lost_after_dispatch`: anything else, for instance a store that is missing, duplicated or doesn't match the stream. The step closes as failed, with no fresh attempt, and the attempt is disclosed in A1. So deleting or copying the store after reading the answer gains nothing.

   `dispatch.py adjudicate --code` settles an attempt stuck at `dispatched`, always as `lost_after_dispatch`.
3. **Recording** binds the transcript before reading anything from it:
   - its first message must be the stored dispatch text;
   - its session must be the logged one;
   - its agent (`agent-setting`), system prompt hash, model and tools must be the expected ones.

   An empty, unparseable or unbound transcript is refused outright: it is not an attempt and frees nothing. A bound transcript is copied to the gitignored `blind/transcripts/` (the rater's to `sealed/blind/transcripts/`), with its hash in the ledger, so an invalid attempt can be audited.

**Committed at every step.** Prepare commits the ledger and the registry (only those paths) with a fixed message, "blind ledger: <kind> <code> prepared". `dispatch.py run` refuses unless the ledger and the registry are committed at HEAD with this code `prepared`. When the call is settled, it commits them again in a `finally` ("… recorded", "… dispatch_failed" or "… lost_after_dispatch"), so a pick cannot be deleted with `git clean` or rewound with `git checkout` and then prepared over. `track-done` and `reject-take` commit their entries the same way. All of this is tamper-evident, not tamper-proof: a rewrite of git history before the registration push is still possible, and the public, archived A1 addenda after Gate R are what make a later rewrite visible (PREREGISTRATION §18).

**Decided from the pipe.** The call's stdout is a pipe. Every chunk is kept in memory and written to the exclusive-create audit file, and the outcome is decided from the bytes in memory, never by re-reading a file that could have been unlinked or replaced mid-run. A replaced stream file is `lost_after_dispatch` (`stream-replaced`). `dispatch_failed` needs no init, model or result event in those bytes *and* a non-zero exit. `adjudicate` always records `lost_after_dispatch`, since the files it could look at are erasable.

**No second ledger, no rewind.** The ledger, state and transcript roots are fixed; no command takes another directory. Every prepared code is also appended to `logs/registry.jsonl`, and a ledger whose attempts are not the registry's (rewound with `git checkout`, say) is refused. The assembler and the lines job use a ledger only if it is committed and unmodified at HEAD.

An attempt is valid only if all of the following hold:
- the brief was read first;
- nothing outside the folder's list was read;
- no tool but Read was used;
- the folder is unchanged;
- the answer has exactly the brief's fields;
- every file the step needs was read (every still up to the pick, all of them for "none"; every file for the points and the rater);
- no more model turns than the agent's maxTurns, counted from distinct message ids;
- exactly one message carries a JSON answer, and it is the last one (so a revised answer is invalid; plain narration between reads is allowed, since real sessions write it).

A valid answer is final, and nobody edits it.

**What the ledgers hold, and what they don't.** Everything an agent can choose is stored as a hash and a count, never as text:
- the name of a file outside the folder's list;
- a path outside the folder;
- a field name it adds;
- a free-text answer.

Problems name fields by count or position. The only agent-written content a ledger holds is a valid answer, which is numbers, or option labels kept under `sealed/`. One residue remains: a valid answer's numbers (a still number, coordinates) are themselves the agent's choice. They are the measurement.

**How the controller checks the pick.** It doesn't judge it. The controller knows the laws, so looking at a pick and redoing it would be a forking path. Its checks are all mechanical, in `record` and `verify`. A wrong-looking mask is handled only by the registered mask quality rule (frames score None), never by a re-pick.

## The render mask, step by step (after a render passes the gate)

1. `frame_pick.py prepare --video <render> --render <id> --take-masks <take masks>`. The folder holds:
   - the brief and `stills.txt`;
   - every 2nd analysis frame (7.5 a second) at 960×540, with the acting creature's home drawn as a thin grey dashed outline from the take's home mask (call 108).

   Then `dispatch.py run`. The rule: the first still in which no part of the creature overlaps its home. "none" means the creature never leaves its home, so the render has no render mask and is not testable for H.
2. `points.py render ...`: only the picked frame, plain and gridded, with the same outline. Then `dispatch.py run` writes `masks/prompts/render/<render>.p1.json`, and the first SAM track follows.
3. `points.py render-check ... --masks <first track>`. The first track must have been made from `<render>.p1.json` and on the video the pick was made on (its meta says so; its hash is logged). Then `dispatch.py run`. The check always runs: the agent accepts the outline, or gives the one second point the registration allows. Only this step writes the final `masks/prompts/render/<render>.json`. If both check attempts are invalid, the first point stands alone. A null `place` answer leaves the render with no render mask.
4. The final SAM track, then `points.py track-done --render <id> --masks <final track>`. This logs the track's digest and file hash. The track must come from the final prompt file and the pick's video, which the masks file's meta records. The pair builder (not yet written) must carry `meta.render_mask_digest` and `meta.render_mask_file_sha256`; until it does, the custody fails closed.
5. Addendum A1: `dispatch.py addendum --render <id>` prints the rows (ledgers, prompt files, and the hashed folder maps and transcripts). Commit them before the lines job runs on that render.
6. `lines_job.py measure --render <id> --prompts <final>` and `assemble.py` both refuse a render unless all of these hold (`points.custody`):
   - its pick is valid, with no unrecorded attempt;
   - its prompt file is the logged final points and starts at the pick;
   - its final track is logged;
   - the pair's creature-mask digest is that track's.

   There is no manual prompt frame. Only the registered no-op null (`t01-noop`) is exempt: its pair has no creature mask, and its video must hash to its row in `MANIFEST.sha256` (it fails closed before then).

## The take masks (before registration)

1. `points.py take --video takes/<take>.analysis.mp4 --take <take> --cue <cue>`, then `dispatch.py run`, which writes `masks/prompts/<take>.json`.
2. The folder holds every 6th analysis frame (2.5 a second; every 3rd until hub call 130, when the textured desk made 65 stills too heavy for one session) at 1280×720 with the labelled grid, plus `objects.txt`. In `objects.txt` each object is an opaque letter with a plain description: the page, the drawings by position, the props, the hand.
3. Aaron checks the tracks on a contact sheet. If he rejects them, `points.py reject-take --reason <wrong-object|lost|spill|missing>` logs why and allows the second attempt.

The ledgers go into the registration manifest.

## The rater

- **Sealed briefs:** at Gate R, after `prepare.py seal`, the four templates are rendered into `sealed/briefs/` (see the note there).
- **Rounds** are a fixed set: `probe`, `draft-1`, `draft-2`, `study-baseline`, `study-clips`. Each ledger holds the hash of its items' refs, and a second round over the same refs is refused. A ref should name one rendered output; its file's SHA-256 is the safe choice.
- **The folder:** `blind.build_rater_folder` holds `rater-brief.md`, `items.txt`, and contact sheets of two frames a second, nine to a sheet, labelled in seconds.
  - For the study it also holds each baseline panel, copied byte for byte and checked against its hash in `sealed/rating-manifest.json`.
  - Its item codes are drawn inside, from a fresh salt; the code-to-render map stays in the sealed folder map (`sealed/blind/`).
  - `items.txt` is shuffled by a seed logged in the ledger.
- **The record:** `blind.record_rater` writes the checked answers to `sealed/machine-rater/<code>.json`, since they hold Q2 labels. The ledger gets the read log for addendum A3.
- **Reporting:** the probe and draft findings that go into STATUS before a round give pass counts only, never a label.
- **The study:** the baseline and the clips are two separate calls, baseline first. The clips call has no memory of the baseline call: it is a fresh session that has never seen the stills' answers. Human raters see both parts in one sitting, so the machine rater is reported separately.
