# Brief: rating short clips from contact sheets

Frozen brief (probe and draft rounds, version 2). Its SHA-256 is registered; it is never edited afterwards.

## Your folder

- `rater-brief.md`: this brief.
- `items.txt`: one line per clip: its code, a colon, then its contact sheets in order, for example `k7q2m: k7q2m-1.png k7q2m-2.png`.
- The contact sheets. Each holds up to nine frames of one clip, in reading order (left to right, then top to bottom), two frames for each second of the clip. Each frame is labelled with its time in seconds from the start of the clip. A clip with more frames continues on its next sheet. Empty places on a last sheet are plain grey.

Read this brief, then `items.txt`, then every sheet it lists, clip by clip. Read nothing else. To save turns, read the sheets in batches: up to ten files at once, in parallel.

## The clips

Each clip shows a desk with a page on it, and small drawings on the page. Things may be placed on the desk, or brought near the page.

## Three questions for each clip

Answer from what you see in the clip's frames only. Choose exactly one option for each question, copied exactly as written here.

**`leaves_place`: Does a drawn figure come to life and move out of its place on the page?**
- Yes
- No
- Can't tell

**`reacted_to`: What did the creature react to?**
- The glass of water
- The torch's light
- The pen
- A breath
- The handwritten note
- The hand
- Nothing in particular
- Can't tell

**`did`: What did it do?**
{{Q2_OPTIONS}}

- "The creature" is whichever drawing comes to life. If none does, answer the last two questions about the drawings as they are.
- If none of the options fits, choose "Nothing in particular". If you can't decide between options, choose "Can't tell".
- Judge each clip on its own. Don't compare clips, and don't guess at how they were made.

## Output

Only this JSON, with nothing before or after it, with every code in `items.txt` once:

```json
{"items": {"k7q2m": {"leaves_place": "Yes", "reacted_to": "The pen", "did": "Can't tell"}},
 "notes": ""}
```

`notes` stays empty unless a sheet can't be read; then give its file name there, and nothing else.
