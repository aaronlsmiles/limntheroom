# Brief: points on the objects in a filmed scene

Frozen brief (take-mask points, version 2). Its SHA-256 is registered; it is never edited afterwards.

## Your folder

- `agent-brief.md`: this brief.
- `objects.txt`: the objects to mark, one per line, as `<letter>: <description>`.
- `stills.txt`: the names of the stills, one per line, in time order.
- The stills, `001.png`, `002.png` and so on: frames of one short video of a desk, evenly spaced in time and numbered in time order. Each carries a pixel grid: thin magenta lines every 64 px, with the x coordinate printed along the top and the y coordinate down the left edge. Coordinates are pixels of a 1280 × 720 frame, x from the left edge and y from the top edge.

Read this brief, then `objects.txt`, then `stills.txt`, then every still in number order. Read nothing else. To save turns, read the stills in batches: up to ten files at once, in parallel, then the next ten.

## What the points are for

A tracking program will follow each object forward in time from the points you place. It starts each object at the first still you give it a point on, and the object counts as absent before that still. A point placed on the wrong thing makes the program follow the wrong thing, so place only points you are sure of.

## The rule, for each object in `objects.txt`

1. **First point.** Find the first still in which the object is clearly in view: not cut off by the frame's edge, and not hidden behind a hand or another object. Place one positive point there, on the object itself, near its middle.
2. **Where on the object.** On a part that belongs only to that object: not on its outline, not on a shadow, reflection or highlight, and not on anything seen through it or lying on it. For a hand, on the back of the hand or the palm, away from anything it holds.
3. **Coming back.** If the object later leaves the frame, or is hidden completely, and then comes back, place one more positive point at the first still where it is clearly in view again.
4. **Neighbours.** If something touches or overlaps the object in a still where you place a positive point, you may add up to two negative points in that same still, on the neighbour, to keep it out.
5. **Limits.** At most six points per object, each in a still you have read.
6. **Not found.** If an object is never clearly in view, put its letter in `not_found` and give it no points.

Mark only the objects in `objects.txt`, each separately, even where two of them touch.

## Output

Only this JSON, with nothing before or after it:

```json
{"objects": {"a": [{"still": 1, "x": 642, "y": 388, "positive": true}],
             "b": [{"still": 9, "x": 300, "y": 512, "positive": true},
                   {"still": 9, "x": 352, "y": 540, "positive": false}]},
 "not_found": ["c"]}
```

- Every letter in `objects.txt` appears exactly once: in `objects` with at least one positive point, or in `not_found`.
- `still` is the still's number, as an integer. `x` and `y` are pixels read off the grid; decimals are allowed. `positive` is `true` for a point on the object and `false` for a point on a neighbour you want kept out.
- Add no other fields and no notes.
