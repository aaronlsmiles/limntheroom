# Brief: the first still with the drawing clear of its home

Frozen brief (prompt frame, version 2). Its SHA-256 is registered; it is never edited afterwards.

## Your folder

- `agent-brief.md`: this brief.
- `stills.txt`: the names of the stills, one per line, in time order.
- The stills, `001.png`, `002.png` and so on: frames of one short video, evenly spaced in time and numbered in time order.

Read this brief, then `stills.txt`, then the stills in number order. Read nothing else. To save turns, read the stills in batches: up to ten files at once, in parallel, then the next ten.

## The scene

A page lies on a desk, with small drawings on it. In every still, a thin grey dashed outline marks one spot on the page: **the home**, the place where one drawing was drawn. That drawing, the one inside the outline in still `001.png`, is the marked drawing. During the video it may come to life and move.

## The rule

Find the first still in which **no part of the marked drawing overlaps its home**: the drawing lies entirely outside the dashed outline, as you see it in the image.

- Follow the marked drawing only. Ignore the other drawings and everything else in the scene.
- Touching the outline from outside counts as clear. Overlapping the area inside the outline by any amount does not.
- A still where you can't find the marked drawing, or can't see all of it, does not count as clear.
- Count a still as clear only if you are sure. If you are unsure, treat it as not clear and go on to the next still.
- If the marked drawing is never entirely clear of its home in any still, the answer is "none".
- Say nothing about what the drawing does, or why.

## Output

Only this JSON, with nothing before or after it:

```json
{"pick": 37}
```

- `pick`: the number of the first still that meets the rule, as an integer (the number in its file name), or the string `"none"`.
- If a still can't be read, add `"unreadable": [12, 13]`, listing their numbers. Add no other fields and no notes.
