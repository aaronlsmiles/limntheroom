# Brief: one point on the drawing that has left its home

Frozen brief (render-mask points, version 2). Its SHA-256 is registered; it is never edited afterwards.

## Your folder

- `agent-brief.md`: this brief.
- `task.txt`: one word, `place` or `check`. Do the task of that name below.
- `frame.png`: one frame of a short video of a desk.
- `frame.grid.png`: the same frame with a pixel grid: thin magenta lines every 64 px, with the x coordinate printed along the top and the y coordinate down the left edge. Coordinates are pixels of a 1280 × 720 frame, x from the left edge and y from the top edge.
- For `check` only, `mask.grid.png`: the same frame and grid, with a cyan outline around a region and a yellow cross at a point.

Read this brief, then `task.txt`, then the images, in parallel if you like. Read nothing else.

## The scene

A page lies on a desk with small drawings on it. A thin grey dashed outline marks one spot on the page: **the home**, the place where one drawing was drawn. In this frame that drawing, the target, has come to life and is outside its home. The other drawings should still sit where they were drawn.

## Task `place`

Place one point on the target drawing, for a tracking program that will outline it and follow it through the video.

- The target is the drawing that has left the dashed outline. If you can't tell which drawing that is, or you can't find it, give `null` for both coordinates.
- Put the point inside the drawing's body, near its middle and away from its edge: on the drawing itself, not on a shadow or reflection, and not on anything it touches or stands on.
- Read the coordinates off `frame.grid.png`; use `frame.png` to see the details under the grid lines.

Output only this JSON, with nothing before or after it:

```json
{"x": 702, "y": 431}
```

## Task `check`

The cyan outline in `mask.grid.png` is what the tracking program found from the point at the yellow cross. Judge whether **the outline covers the whole target drawing and nothing else.** Slips of a few pixels along its edge don't count. The grey dashed outline is only the home; it is not part of the region.

- If it does, output `{"covers": true}`.
- If it doesn't, give one more point, at whichever error is bigger: a positive point on a part of the target drawing that the outline misses, or a negative point on something the outline wrongly includes (a shadow, the desk, an object, another drawing). Place it well inside that part, away from the outline.

Output only one of these, with nothing before or after it:

```json
{"covers": true}
```

```json
{"covers": false, "x": 715, "y": 452, "positive": true}
```

`x` and `y` are pixels read off the grid; decimals are allowed. Add no other fields and no notes.
