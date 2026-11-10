# Brief: rating clips (the study's second part)

Frozen brief (machine rater, study clips, version 2). Its SHA-256 is registered; it is never edited afterwards.

## Your folder

- `rater-brief.md`: this brief.
- `items.txt`: one line per clip: its code, a colon, its reference picture, then its contact sheets in order, for example `c8m2q: c8m2q.ref.png c8m2q-1.png c8m2q-2.png`.
- The reference pictures: one per clip, the still frame the clip is shown beside, with a thin grey ring around one drawing (the drawing the clip is about).
- The contact sheets. Each holds up to nine frames of one clip, in reading order (left to right, then top to bottom), two frames for each second of the clip. Each frame is labelled with its time in seconds from the start of the clip. A clip with more frames continues on its next sheet. Empty places on a last sheet are plain grey.

Read this brief, then `items.txt`, then for each clip its reference picture and every one of its sheets. Read nothing else. To save turns, read the files in batches: up to ten at once, in parallel.

## Two questions for each clip

Answer from what you see in the clip's frames, with its reference picture beside them. Choose exactly one option for each question, copied exactly as written here.

**`q1`: What did the creature react to?**
- The glass of water
- The torch's light
- The pen
- A breath
- The handwritten note
- The hand
- Nothing in particular
- Can't tell

**`q2`: What did it do?**
{{Q2_OPTIONS}}

- "The creature" is whichever drawing comes to life. If none does, answer about the drawings as they are.
- If none of the options fits, choose "Nothing in particular". If you can't decide between options, choose "Can't tell".
- Judge each clip on its own. Don't compare clips, and don't guess at how they were made.

## Output

Only this JSON, with nothing before or after it, with every code in `items.txt` once:

```json
{"items": {"c8m2q": {"q1": "The pen", "q2": "Can't tell"}}, "notes": ""}
```

`notes` stays empty unless an image can't be read; then give its file name there, and nothing else.
