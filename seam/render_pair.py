#!/usr/bin/env python3
"""The render pair writer (Phase 8): a gated render, warped onto its take, in the npz the lines job measures.

    python seam/render_pair.py render --render t01-ink --take takes/t01a.analysis.mp4 --video renders/t01-ink.mp4 \
        --take-masks masks/t01a.npz --track masks/render/t01-ink.npz --prompts masks/prompts/render/t01-ink.json \
        --gate runs/gate/t01-ink.json --m 32 [--crops creature/scan/crops.json] --out runs/pairs/t01-ink.npz
    python seam/render_pair.py null --take takes/t01a.analysis.mp4 --render-input takes/t01a.render.mp4 \
        --height 720 --out runs/pairs/t01a.null720.npz

`render` reads every video onto the 1280x720 grid at 15 fps as the masks, the blind pick and the points were
made (seam.masks.analysis_frames), so render frame i is the frame the creature track holds at i. It refuses
unless the whole chain holds:
  - the blind pick is valid and its video is this video (frame_pick.verify); "none" has no render mask;
  - the gate (seam/align.py gate) is this render's on this take, these take masks and this video, agrees with
    its own numbers (seam.assemble.check_gate) and passed;
  - the track's own meta names the final prompt file and this video; and
  - seam.points.custody passes on the pair it is about to write (ledgers committed, the logged final track).
The render-mask digest and the track file's hash are computed here from the track file itself.

What it writes (seam/pairs.py): take; render (each frame warped onto the take by the gate's transform, as is
where the frame has no fit: such a frame failed the gate and is not scored); valid = gate ok AND the mask
quality rule from the prompt frame (seam.assemble.scored_frames); R(t) = ~dilate(creature(t) ∪ home, m), the
home alone before the prompt frame (seam.assemble.region_series), minus the pixels the warp did not cover;
cover (those pixels, align.cover: the border strip the warp fills by replicating the render's edge leaves R(t)
and its cells get no verdict, call 126); t = i / 15; creature (the final track,
warped by nearest neighbour); homes (the three static home masks, majority vote of their take tracks); scan
(the acting creature's crop over white, when --crops is given); and meta:
  render, take, home (the acting creature's home), m, prompt_frame, video_sha256, take_sha256,
  take_masks_sha256, prompts_sha256, render_mask_digest, render_mask_file_sha256, creature_digest (of the
  warped mask as stored), gate {sha256 (canonical JSON of the gate file), pass, frames_ok, rho, lag}.

`noop` writes the no-op null's pair (§9, call 135): R_noop(t) = ~dilate(all three homes, m) ∩ cover(t), valid =
the gate's per-frame ok, over the gate's span (the no-op input is the first 10 s); the lines job's κ_render_p1 on
it is κ_keep. `null --start --seconds` cuts the null to the same span.

`null` writes the codec null pair for D0: the take against its render input re-encoded at --height and
decoded onto the grid (seam.controls_inputs.null_frames), every frame valid, R all-true (the lines job scores
the null under the render pair's own R(t)). Its take is the render pair's take, frame for frame.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from seam import align, blind, controls_inputs, frame_pick, masks, pairs, points  # noqa: E402
from seam.util import sha256_file  # noqa: E402

SCHEMA = "p47-render-pair/1"
NULL_SCHEMA = "p47-null-pair/1"
FPS = 15
HOMES = ("home_ink", "home_gold", "home_paper")
M_CHOICES = (32, 48, 64)


class PairError(ValueError):
    pass


def _scan(crops, material):
    """The acting creature's flat-scan crop as RGB over white (its alpha is the cut-out)."""
    rgba = controls_inputs.load_crop(crops, material).astype(np.float32)
    a = rgba[..., 3:] / 255.0
    return np.clip(np.rint(rgba[..., :3] * a + 255.0 * (1 - a)), 0, 255).astype(np.uint8)


def _warp_all(frames, creature, transforms, size):
    """(frames, creature, cover) on the take grid. cover marks the pixels the warp reached inside the render
    frame (align.cover); a frame with no fit is stored as is, all covered, and is not scored anyway."""
    out_f = np.empty_like(frames)
    out_c = np.empty_like(creature)
    cov = np.ones(creature.shape, bool)
    src = (frames.shape[2], frames.shape[1])
    for i, M in enumerate(transforms):
        if M is None:
            out_f[i], out_c[i] = frames[i], creature[i]
        else:
            out_f[i] = align.warp(frames[i], M, size)
            out_c[i] = align.warp_mask(creature[i], M, size)
            cov[i] = align.cover(M, src, size)
    return out_f, out_c, cov


def build_render_pair(out, *, render, take_video, video, take_masks, track, prompts, gate, m, crops=None,
                      take_frames=None, render_frames=None, exclude=None):
    """Write the render pair; returns its meta. `gate` is the path of the render's p47-gate/1 file.
    `take_frames` / `render_frames`, if given, must be the videos' analysis frames (they are re-read otherwise).
    `exclude` (n, H, W) bool, the touched object's take mask: R(t) also leaves it out, for the registered
    secondary "the touched object's interior excluded" (§13; meta variant "interior_excluded"; call 135)."""
    from seam import assemble
    if m not in M_CHOICES:
        raise PairError(f"m must be one of {M_CHOICES}, got {m!r}")
    home_name = frame_pick.home_name(render)
    material = home_name.split("_", 1)[1]
    video_sha, take_sha, tm_sha = sha256_file(video), sha256_file(take_video), sha256_file(take_masks)
    pf = frame_pick.verify(render, prompts=prompts, video=video)
    if pf is None:
        raise PairError(f"{render}: the blind pick was none: no render mask, so no pair (not testable for H)")

    g = json.loads(Path(gate).read_text(encoding="utf-8"))
    if g.get("schema") != align.GATE_SCHEMA or g.get("render") != render:
        raise PairError(f"{Path(gate).name} is not {render}'s p47-gate/1 record")
    want = {"take_sha256": take_sha, "video_sha256": video_sha, "take_masks_sha256": tm_sha}
    got = {k: (g.get("inputs") or {}).get(k) for k in want}
    if got != want:
        bad = sorted(k for k in want if got[k] != want[k])
        raise PairError(f"{render}: the gate was run on other inputs ({', '.join(bad)})")

    take = masks.analysis_frames(take_video) if take_frames is None else np.asarray(take_frames)
    n, size = len(take), (take.shape[2], take.shape[1])
    assemble.check_gate(g, n)
    if not g["pass"]:
        raise PairError(f"{render}: the render failed the alignment gate ({g.get('reason')})")
    if len(g.get("transforms") or []) != n:
        raise PairError(f"{render}: the gate holds {len(g.get('transforms') or [])} transforms, the take {n} frames")

    tmm, tm = masks.load_masks(take_masks)
    if any(len(v) != n for v in tm.values()):
        raise PairError(f"{render}: the take masks are not on the take's {n} analysis frames")
    if home_name not in tm:
        raise PairError(f"{render}: the take masks have no {home_name}")
    home = controls_inputs.static_mask(tm[home_name])
    if blind.mask_digest(home) != frame_pick.load_log(render)["home_digest"]:
        raise PairError(f"{render}: the home is not the one the pick outlined")

    tmeta, trk = masks.load_masks(track)
    if "creature" not in trk:
        raise PairError(f"{render}: the track has no creature mask")
    if tmeta.get("video_sha256") != video_sha:
        raise PairError(f"{render}: the track was not made on this video")
    if tmeta.get("prompts_sha256") != sha256_file(prompts):
        raise PairError(f"{render}: the track was not made from this prompt file")
    track_digest = masks.mask_digest({"creature": trk["creature"]})
    track_sha = sha256_file(track)
    c = trk["creature"]
    if len(c) < n:
        raise PairError(f"{render}: the track has {len(c)} frames, the take {n}")
    rend = masks.analysis_frames(video) if render_frames is None else np.asarray(render_frames)
    if len(rend) < n:
        raise PairError(f"{render}: the render has {len(rend)} analysis frames, the take {n}")
    if rend.shape[1:3] != take.shape[1:3] or c.shape[1:] != take.shape[1:3]:
        raise PairError(f"{render}: the render, its track and the take are not on one grid")

    warped, creature, cover = _warp_all(rend[:n], c[:n], g["transforms"], size)
    valid = np.array(assemble.scored_frames(g["ok"], creature, start=pf), bool)
    R = assemble.region_series(creature, home, m, pf, cover)
    if exclude is not None:
        exclude = np.asarray(exclude, bool)
        if len(exclude) < n or exclude.shape[1:] != take.shape[1:3]:
            raise PairError(f"{render}: the excluded mask is not on the take's {n} analysis frames")
        R = np.asarray(R) & ~exclude[:n]
    homes = {k: controls_inputs.static_mask(tm[k]) for k in HOMES if k in tm}
    scan = _scan(crops, material) if crops else None
    meta = {"schema": SCHEMA, "render": render, "take": tmm.get("take"),
            "home": home_name, "m": int(m), "prompt_frame": int(pf), "video_sha256": video_sha,
            "take_sha256": take_sha, "take_masks_sha256": tm_sha, "prompts_sha256": sha256_file(prompts),
            "render_mask_digest": track_digest, "render_mask_file_sha256": track_sha,
            "creature_digest": masks.mask_digest({"creature": creature}),
            "gate": {"sha256": blind.sha256_json(g), "pass": bool(g["pass"]), "frames_ok": g["frames_ok"],
                     "rho": g["rho"], "lag": g["lag"]},
            "scan_sha256": blind.sha256_bytes(np.ascontiguousarray(scan).tobytes()) if scan is not None else None}
    if exclude is not None:
        meta["variant"] = "interior_excluded"
    try:
        points.custody(render, prompts=prompts, pair_meta=meta, creature=creature)
    except blind.BlindError as e:
        raise PairError(str(e)) from None
    pairs.write_pair(out, take=take, render=warped, valid=valid, R=R, t=np.arange(n) / FPS, creature=creature,
                     cover=cover, homes=homes, scan=scan, meta=meta)
    return meta


def build_null_pair(out, *, take_video, render_input, height, take_frames=None, span=None):
    """The codec null pair at `height` (720 or 1080) for the lines job's --null. With `span` (first frame, count),
    the take and its null are cut to that span, so the null's take is a trimmed render pair's, frame for frame."""
    take = masks.analysis_frames(take_video) if take_frames is None else np.asarray(take_frames)
    n_all = len(take)
    null = controls_inputs.null_frames(render_input, (int(height),), n_frames=n_all,
                                       size=(take.shape[2], take.shape[1]))[int(height)]
    i0, n = (0, n_all) if span is None else (int(span[0]), int(span[1]))
    if i0 < 0 or n <= 0 or i0 + n > n_all:
        raise PairError(f"span {i0}+{n} frames does not fit the take's {n_all} frames")
    take, null = take[i0:i0 + n], null[i0:i0 + n]
    meta = {"schema": NULL_SCHEMA, "take_sha256": sha256_file(take_video), "render_input_sha256": sha256_file(render_input),
            "height": int(height), "span": {"start_frame": i0, "frames": n}}
    pairs.write_pair(out, take=take, render=null, valid=np.ones(n, bool), R=np.ones(take.shape[:3], bool),
                     t=(i0 + np.arange(n)) / FPS, meta=meta)
    return meta


def build_noop_pair(out, *, take_video, video, take_masks, gate, m, take_frames=None, render_frames=None):
    """The no-op null's pair (§9; review finding 2, call 135): the glass take's render made with the fixed
    "change nothing" prompt, warped onto its span of the take by the gate's transforms. valid = the gate's per-frame
    ok (its aligned frames); R(t) = R_noop(t) ∩ cover(t), where R_noop = ~dilate(ink home ∪ gold home ∪ paper home, m)
    and cover is what the warp reached (call 126). No creature and no blind pick: the no-op is the custody
    exemption (lines_job.NOOP_ID, its video hashed in a manifest addendum). A failed gate writes nothing: κ_keep
    then falls back to κ_codec, as registered."""
    from seam import assemble, lines_job, regions
    if m not in M_CHOICES:
        raise PairError(f"m must be one of {M_CHOICES}, got {m!r}")
    render = lines_job.NOOP_ID
    video_sha, take_sha, tm_sha = sha256_file(video), sha256_file(take_video), sha256_file(take_masks)
    g = json.loads(Path(gate).read_text(encoding="utf-8"))
    if g.get("schema") != align.GATE_SCHEMA or g.get("render") != render:
        raise PairError(f"{Path(gate).name} is not {render}'s p47-gate/1 record")
    want = {"take_sha256": take_sha, "video_sha256": video_sha, "take_masks_sha256": tm_sha}
    got = {k: (g.get("inputs") or {}).get(k) for k in want}
    if got != want:
        raise PairError(f"{render}: the gate was run on other inputs ({', '.join(sorted(k for k in want if got[k] != want[k]))})")
    take_all = masks.analysis_frames(take_video) if take_frames is None else np.asarray(take_frames)
    sp = g.get("span") or {"start_frame": 0, "frames": len(take_all)}
    i0, n = int(sp["start_frame"]), int(sp["frames"])
    if i0 < 0 or n <= 0 or i0 + n > len(take_all):
        raise PairError(f"{render}: the gate's span {i0}+{n} does not fit the take's {len(take_all)} frames")
    take = take_all[i0:i0 + n]
    assemble.check_gate(g, n)
    if not g["pass"]:
        raise PairError(f"{render}: the no-op render failed the alignment gate ({g.get('reason')}); "
                        "κ_keep falls back to κ_codec")
    tmm, tm = masks.load_masks(take_masks)
    missing = [k for k in HOMES if k not in tm]
    if missing:
        raise PairError(f"{render}: the take masks have no {', '.join(missing)}")
    homes = {k: controls_inputs.static_mask(tm[k]) for k in HOMES}
    union = np.zeros(take.shape[1:3], bool)
    for h in homes.values():
        union |= h
    r_noop = ~regions.dilate(union, m)
    rend = masks.analysis_frames(video) if render_frames is None else np.asarray(render_frames)
    if len(rend) < n:
        raise PairError(f"{render}: the render has {len(rend)} analysis frames, its span {n}")
    if rend.shape[1:3] != take.shape[1:3]:
        raise PairError(f"{render}: the render and the take are not on one grid")
    none = np.zeros((n,) + take.shape[1:3], bool)
    warped, _, cover = _warp_all(rend[:n], none, g["transforms"], (take.shape[2], take.shape[1]))
    R = r_noop[None] & cover
    valid = np.array([bool(v) for v in g["ok"]], bool)
    meta = {"schema": SCHEMA, "render": render, "take": tmm.get("take"), "home": None, "m": int(m),
            "span": {"start_frame": i0, "frames": n}, "region": "R_noop: ~dilate(all three homes, m) ∩ cover",
            "video_sha256": video_sha, "take_sha256": take_sha, "take_masks_sha256": tm_sha,
            "gate": {"sha256": blind.sha256_json(g), "pass": bool(g["pass"]), "frames_ok": g["frames_ok"],
                     "rho": g["rho"], "lag": g["lag"]}}
    pairs.write_pair(out, take=take, render=warped, valid=valid, R=R, t=(i0 + np.arange(n)) / FPS,
                     cover=cover, homes=homes, meta=meta)
    return meta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python seam/render_pair.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--render", required=True)
    r.add_argument("--take", required=True, help="the take's 1280x720 analysis copy")
    r.add_argument("--video", required=True, help="the render, as the pick and the track saw it")
    r.add_argument("--take-masks", required=True)
    r.add_argument("--track", required=True, help="the final render-mask track (logged by points.py track-done)")
    r.add_argument("--prompts", required=True, help="the final render-mask prompt file")
    r.add_argument("--gate", required=True, help="the render's p47-gate/1 file (seam/align.py gate)")
    r.add_argument("--m", type=int, required=True, choices=M_CHOICES)
    r.add_argument("--crops", help="creature/scan/crops.json (the acting creature's crop goes in as the scan)")
    r.add_argument("--exclude-touched", action="store_true",
                   help="also leave the touched object's take mask (capture/takes.json) out of R: the registered "
                        "secondary 'interior excluded' (§13)")
    r.add_argument("--out", required=True)
    nl = sub.add_parser("null")
    nl.add_argument("--take", required=True)
    nl.add_argument("--render-input", required=True)
    nl.add_argument("--height", type=int, required=True, choices=(720, 1080))
    nl.add_argument("--start", type=float, help="the trimmed render's start, s (its gate's span)")
    nl.add_argument("--seconds", type=float, help="the trimmed render's length, s")
    nl.add_argument("--out", required=True)
    no = sub.add_parser("noop", help="the no-op null's pair (§9): R_noop ∩ cover over the gate's span")
    no.add_argument("--take", required=True)
    no.add_argument("--video", required=True, help="the no-op render")
    no.add_argument("--take-masks", required=True)
    no.add_argument("--gate", required=True, help="the no-op's p47-gate/1 file (render t01-noop)")
    no.add_argument("--m", type=int, required=True, choices=M_CHOICES)
    no.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "render":
            exclude = None
            if a.exclude_touched:
                from seam import assemble
                name = assemble.registered_masks(a.render)["touched"]
                if name is None:
                    raise PairError(f"{a.render} has no touched object to exclude")
                exclude = masks.load_masks(a.take_masks)[1][name]
            meta = build_render_pair(a.out, render=a.render, take_video=a.take, video=a.video, take_masks=a.take_masks,
                                     track=a.track, prompts=a.prompts, gate=a.gate, m=a.m, crops=a.crops,
                                     exclude=exclude)
        elif a.cmd == "noop":
            meta = build_noop_pair(a.out, take_video=a.take, video=a.video, take_masks=a.take_masks, gate=a.gate, m=a.m)
        else:
            if (a.start is None) != (a.seconds is None):
                raise PairError("give --start and --seconds together, or neither")
            span = None
            if a.seconds is not None:
                span = align.span_frames(a.start, a.seconds, len(masks.analysis_frames(a.take)))
            meta = build_null_pair(a.out, take_video=a.take, render_input=a.render_input, height=a.height, span=span)
    except (PairError, blind.BlindError, controls_inputs.ControlInputError, ValueError, OSError, KeyError) as e:
        print(f"render_pair: refuse: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"out": a.out, **{k: meta.get(k) for k in ("render", "prompt_frame", "height") if k in meta}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
