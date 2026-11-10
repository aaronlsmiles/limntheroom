# Brief: rating still pictures (the study's first part)

Frozen brief (machine rater, study baseline, version 2). Its SHA-256 is registered; it is never edited afterwards.

## Your folder

- `rater-brief.md`: this brief.
- `items.txt`: one line per picture: its code, a colon, then its file, for example `p4x9d: p4x9d.png`.
- The pictures. Each is a still frame of a desk with a page on it, and small drawings on the page. One drawing has a thin grey ring around it.

Read this brief, then `items.txt`, then every picture it lists. Read nothing else. To save turns, read the pictures in batches: up to ten files at once, in parallel.

## Two questions for each picture

Choose exactly one option for each question, copied exactly as written here. Answer from the picture alone: it is your first read that counts.

**`q1b`: If the ringed drawing came alive here, what would it react to?**
- The glass of water
- The torch's light
- The pen
- A breath
- The handwritten note
- The hand
- Nothing in particular
- Can't tell

**`q2b`: What would it do?**
{{Q2_OPTIONS}}

- If none of the options fits, choose "Nothing in particular". If you can't decide between options, choose "Can't tell".
- Judge each picture on its own.

## Output

Only this JSON, with nothing before or after it, with every code in `items.txt` once:

```json
{"items": {"p4x9d": {"q1b": "The pen", "q2b": "Can't tell"}}, "notes": ""}
```

`notes` stays empty unless a picture can't be read; then give its file name there, and nothing else.
