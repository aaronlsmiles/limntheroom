# Limn the Room

*ink that reads the room*

**limn** (verb): to draw or outline; from *illumine*. The limners painted the illuminated manuscripts.

## What it explores

A small creature is made by hand on a real page, three times over: in ink, in gold paint and in cut paper. A video model then regenerates a phone take of that page so that one creature comes to life, steps up out of its place on the page and reacts to something real beside it, by the laws of its own material.

The question is how much of the room survives the regeneration. A public "seam view" lays the real take and the regenerated one under a wipe. It shows in gold what the model kept of the room, and in ink hatching what it redrew.

## Why it matters

"Read the room" is what we ask of a character: notice what is there and answer it. Here the creature reads the room, and the machine ends up redrawing the room. Seeing exactly where it did so is a way to check what a generative video model keeps and what it invents, and whether a reaction a viewer names is really there.

The hypothesis, the rating protocol and the measurements are registered publicly before any generation, so the result counts whichever way it falls. Raters watch cold, without being told what to look for.

## What it suggests

If a model can bring a hand-made drawing to life on its page and make it answer the real objects around it, then the drawing and the desk share one scene, and the seam between real and redrawn becomes something you can read. If it cannot, the seam shows that too, and that is a finding.

## Status

Registered on 10 Nov 2026, before any generation (`PREREGISTRATION.md`, `MANIFEST.sha256`, the tag `registered`, and `REGISTRATION.md`).

## Prior art

Simulon's Reality-Aware Rendering (iPhone, announced 28 October 2026) is the nearest work. It is credited here as prior art; nothing is copied from it.

## Run

```bash
SAM2_BUILD_CUDA=0 uv sync
uv run pytest
```

SAM 2.1 small runs on CPU. Fetch the checkpoint first, as described in `models/MODELS.md`.
