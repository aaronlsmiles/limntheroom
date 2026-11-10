# P47 creature — Phase 1.1 design round (prompt pack)

Round 1.1, 31 Oct 2026. Design candidates for the one small creature Aaron makes by hand three
times (pen, gold paint, cut paper, each about 4–6 cm).

## Engine and workflow

- **Engine:** local ComfyUI 0.31.0 (`~/tools/ComfyUI`, its existing venv, started with
  `./.venv/bin/python main.py --listen 127.0.0.1 --port 8188`; nothing installed). £0, no hosted call.
- **Checkpoint:** `Illustrious-XL-v0.1.safetensors` (SDXL family; responds to tag-form prompts, which
  is why the prompts below are tags, not prose).
- **Workflow:** TFF's `scripts/comfy_workflows/txt2img.json`, driven read-only by
  `~/projects/TFF/scripts/comfy_gen.py gen` (Checkpoint → CLIPTextEncode ×2 → EmptyLatent 1024×1024 →
  KSampler euler_ancestral / normal, 28 steps, cfg 5.5 → VAEDecode → Save). Nothing in TFF was edited.
- **Command (per shot):**
  `python3 ~/projects/TFF/scripts/comfy_gen.py gen --prompt-file creature/prompt.md --shot C01 --seed 4701 --ratio 1024x1024 --out creature/raw/C01-4701.png`
- **Seeds:** two per shot, `47NN` and `47NN+100` (C01 → 4701, 4801; C12 → 4712, 4812). The kept
  seed for each candidate is recorded in the table at the end.

## Register, qualities only

Taken from TFF's ink treatment as a quality, nothing else: the *open linework* register (bold closed
outline, outline only, no screentone, no hatching, no solid blacks, white paper). No TFF name, character,
mark or canon enters any prompt. Each creature is new.

Brief constraints the prompts aim at: one compact closed silhouette that reads at 30 px; few interior
lines; a walking pose; no thin detached parts or hair-fine spikes (scissors must follow the outline);
wry, not cute-mascot, not monster; no text. `pokemon` and `mascot` sit in the negative to push away
from known-character and brand-mascot looks.

## Round history

- **v1 (abandoned after 2 images):** long tag lists with prose-like phrases (`flat, minimalist, one smooth
  domed shell…`) and no `greyscale`. Illustrious drew coloured grounds (red and brown on tan) and
  spindly insect legs. Same lesson as TFF's R1: this checkpoint wants short booru tags.
- **Tuning (2 images, scratch):** `monochrome, greyscale, lineart` lead restored. A fat bird came back
  monochrome and wry; an armadillo came back busy, with grey tone and ink splatter. Hence `simple,
  cartoon, wide shot` added and `grey, shadow, splatter, detailed, fur texture, feathers` negated.
- **v2 (C01–C12, 24 images):** monochrome held, but most creatures came back with ink drips and
  splatter ground lines, and several with spindly legs, wings or antennae (C01, C07, C10, C11, C12). C05-4705
  drew a recognisable video-game hedgehog, a known character: dropped, and that character's tag negated in v3.
- **v3 (C13–C20, 16 images):** the eight most makeable directions again, with `chubby`, `short thick legs`,
  and `ink drip, ground, floor, thin legs, long legs, antennae, claws` negated. The v3 shots carry their own
  negative (below); the v2 shared negative above applies to C01–C12 only.

## Shared tags

**Positive head (every shot):** `monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot`

**Negative (every shot):** `color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, black fill, fur texture, feathers, detailed, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, worst quality, lowres, blurry`

## Shots

**C01 — the stamp-footed beetle**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, beetle, round shell, stubby legs, tiny head, half-closed eyes, smug

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, black fill, fur texture, feathers, detailed, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, worst quality, lowres, blurry

**C02 — the teapot bird**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, bird, round body, fat, stubby legs, short beak, chest out, half-closed eyes, smug

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, black fill, fur texture, feathers, detailed, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, worst quality, lowres, blurry

**C03 — the stout newt**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, newt, salamander, thick tail, wide head, stubby legs, raised eyebrow, smirk

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, black fill, fur texture, feathers, detailed, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, worst quality, lowres, blurry

**C04 — the walking shell**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, snail, spiral shell, no antennae, two stubby legs, striding, determined

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, black fill, fur texture, feathers, detailed, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, worst quality, lowres, blurry

**C05 — the scalloped lump**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, hedgehog, rounded back, scalloped back, no spikes, pointed snout, stubby legs, half-closed eyes

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, black fill, fur texture, feathers, detailed, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, worst quality, lowres, blurry

**C06 — the mitten**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, creature, mitten-shaped body, floppy ear, stubby legs, stubby arms, deadpan, expressionless

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, black fill, fur texture, feathers, detailed, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, worst quality, lowres, blurry

**C07 — the pebble with a beak**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, bird, egg-shaped body, no wings, short beak, thick legs, round feet, leaning forward, narrowed eyes

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, black fill, fur texture, feathers, detailed, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, worst quality, lowres, blurry

**C08 — the plated walker**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, armadillo, three rounded plates, few lines, stubby legs, long snout, head up, smug

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, black fill, fur texture, feathers, detailed, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, worst quality, lowres, blurry

**C09 — the acorn on legs**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, acorn creature, acorn cap, cap over eyes, stubby legs, striding

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, black fill, fur texture, feathers, detailed, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, worst quality, lowres, blurry

**C10 — the big-footed fox**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, fox, chubby, big feet, big tail, short ears, half-closed eyes, smirk

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, black fill, fur texture, feathers, detailed, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, worst quality, lowres, blurry

**C11 — the folded moth**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, moth, folded wings, wings down, round head, no antennae, stubby legs, walking on ground, half-closed eyes

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, black fill, fur texture, feathers, detailed, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, worst quality, lowres, blurry

**C12 — the loaf**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, creature, loaf-shaped body, long body, very short legs, one round ear, short tail, half-closed eyes, tired

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, black fill, fur texture, feathers, detailed, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, worst quality, lowres, blurry

## Shots, v3

**Negative (every v3 shot):** `color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, ink drip, dripping, ground, floor, black fill, fur texture, feathers, detailed, thin legs, long legs, antennae, claws, spikes, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, sonic the hedgehog, worst quality, lowres, blurry`

**C13 — the teapot bird, v3**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, bird, chubby, round body, egg-shaped body, short thick legs, short beak, tail stub, half-closed eyes, smug

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, ink drip, dripping, ground, floor, black fill, fur texture, feathers, detailed, thin legs, long legs, antennae, claws, spikes, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, sonic the hedgehog, worst quality, lowres, blurry

**C14 — the acorn on legs, v3**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, acorn creature, acorn cap, cap over eyes, round body, short thick legs, striding, peeking

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, ink drip, dripping, ground, floor, black fill, fur texture, feathers, detailed, thin legs, long legs, antennae, claws, spikes, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, sonic the hedgehog, worst quality, lowres, blurry

**C15 — the walking shell, v3**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, snail, chubby, round spiral shell, short thick legs, no antennae, stubby head, determined, striding

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, ink drip, dripping, ground, floor, black fill, fur texture, feathers, detailed, thin legs, long legs, antennae, claws, spikes, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, sonic the hedgehog, worst quality, lowres, blurry

**C16 — the loaf, v3**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, creature, chubby, rectangular body, loaf, very short thick legs, round head, one ear, stubby tail, half-closed eyes, tired

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, ink drip, dripping, ground, floor, black fill, fur texture, feathers, detailed, thin legs, long legs, antennae, claws, spikes, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, sonic the hedgehog, worst quality, lowres, blurry

**C17 — the plated lump, v3**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, pangolin, chubby, round body, few large plates, short thick legs, short snout, half-closed eyes, smug

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, ink drip, dripping, ground, floor, black fill, fur texture, feathers, detailed, thin legs, long legs, antennae, claws, spikes, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, sonic the hedgehog, worst quality, lowres, blurry

**C18 — the beetle, v3**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, beetle, chubby, round shell, short thick legs, no antennae, tiny head, half-closed eyes

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, ink drip, dripping, ground, floor, black fill, fur texture, feathers, detailed, thin legs, long legs, antennae, claws, spikes, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, sonic the hedgehog, worst quality, lowres, blurry

**C19 — the stout newt, v3**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, newt, chubby, short thick tail, short thick legs, wide head, raised eyebrow, smirk

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, ink drip, dripping, ground, floor, black fill, fur texture, feathers, detailed, thin legs, long legs, antennae, claws, spikes, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, sonic the hedgehog, worst quality, lowres, blurry

**C20 — the bean**
> monochrome, greyscale, lineart, ink, thick outlines, simple, cartoon, white background, simple background, masterpiece, best quality, no humans, animal focus, solo, full body, side view, walking, wide shot, creature, bean-shaped body, one floppy ear, short thick legs, no arms, deadpan, half-closed eyes, striding

**Negative:**
> color, screentone, halftone, shading, hatching, cross-hatching, grey, gradient, shadow, drop shadow, ink splatter, splatter, ink drip, dripping, ground, floor, black fill, fur texture, feathers, detailed, thin legs, long legs, antennae, claws, spikes, sketch, realistic, 3d, text, watermark, signature, multiple views, pokemon, mascot, sonic the hedgehog, worst quality, lowres, blurry

## Kept candidates (self-review, 31 Oct)

40 images were generated (2 v1, 2 scratch tuning, 24 v2, 16 v3; all local, £0). Raw files stay in
`creature/raw/` (gitignored). Kept candidates are copied to `candidates/cNN.png`; the contact sheet
`candidates/contact-sheet.png` adds a 30 px thumbnail per tile, which is the brief's read test.

| Kept | Shot-seed | What it is | Pen / gold paint / cut paper (4–6 cm) |
|---|---|---|---|
| c01 | C13-4813 | strutting round bird, chest out, mid-step | All three: closed egg body, lobed tail; thicken the toes to stubs; the black head mask becomes an outline (no solid black) |
| c02 | C17-4817 | dome-shelled lump with a smug head tucked in | All three, easily: one closed outline, the shell bands are pen-only interior lines; legs are stubs |
| c03 | C20-4820 | stubby bean-rabbit, eyes shut, trotting | All three: compact closed shape; widen the ears' base for scissors; drop the black feet and the motion dots |
| c04 | C15-4715 | snail with a bold spiral shell and a round eye | All three: big closed silhouette, the spiral is the one interior line; no visible legs, so "walking" must come from the video |
| c05 | C16-4716 | loaf-bodied blob on four stub legs | All three: simplest cut; the dashed lines and ink smear go; low character until a face is added |
| c06 | C13-4713 | small round bird with a streaming tail | Pen and gold fine; cut paper only if the streak tail becomes one solid wedge (as drawn it is detached lines) |
| c07 | C14-4714 | acorn-pot body, cap tipped back, no visible legs | All three: two closed shapes joined; needs legs added to walk |
| c08 | C14-4814 | acorn lump, cap pulled over its eyes | All three; the cap's hatching goes; legs need adding; the scattered husks are detached and are dropped |
| c09 | C02-4702 | heavy-lidded fat bird, stomping | Pen and gold yes once the ink drips and feather strokes go; cut paper OK, the feet are fiddly |
| c10 | C09-4709 | acorn ball with a tipped cap, two stub legs | All three: two circles and a cap; the grey band is tone and goes |
| c11 | C02-4802 | outline-only crouching bird, crested head | Pen yes (closest to the open-linework register as generated); gold and cut paper need the crest and beak thickened |

**Dropped:** C05-4705 (a recognisable video-game hedgehog: a known character); C01 both seeds, C18 both
(antennae and spindly legs); C07 both (ink blobs, or a stork with stick legs); C10 both and C19-4719
(thin legs); C11 both (thin veined wings); C12 both (thin legs and tail); C03-4803 and C19-4819 (busy,
monster-leaning); C17-4717 (hair-fine fur fringe, uncuttable); C08 both (many plate lines, splatter);
C03-4703, C04-4704 and C04-4804, C05-4805, C06 both, C09-4809, C15-4815, C16-4816 and C20-4720 (too small,
too faint, too busy, tone, or no creature). Tuning images and v1 are not kept.

**Common faults across the round (for the hand versions, not fixed by regeneration):** the checkpoint
adds a toned paper ground, ink drips and a smeared ground line. All of these go when Aaron draws it.
No text appeared in any kept candidate.
