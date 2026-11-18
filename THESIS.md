# Limn the Room: the drawing that would not keep time

*Thesis, 17–18 November 2026. Every number is exploratory and comes from the files of record (`analysis/out/`, `runs/gate/`, `runs/probe/`, `runs/rescue/`). The full account is `docs/write-up.md`.*

## What it explores

I drew one small creature, picked from sketches a local image model made, three times on a real page: in ink, in gold paint and in cut paper. A phone filmed the page on a speckled desk while a hand set a glass of water down beside it. The question was whether a video model, given that take, could bring one drawing to life, make it answer the glass by the law of its own material, and leave everything else in the room as it was filmed. The ink one should back away, because wet ink runs. The gold one should admire its reflection. The paper one should wilt.

Before any generation, I registered the whole study in public: the renders, a probe of the candidate models on a short cut of one take, one rescue if the probe failed, an alignment gate that a render must pass before anything else is measured, a hypothesis about where the room drifts, a cold rating study, and the rules for stopping. Those behaviours, the creatures' laws, stayed sealed until the raters were done. The repository is tagged and archived by Software Heritage, so any change after the fact would show.

The plan was a seam view: the take under the render, with a wipe between them, and every cell of the room marked kept or redrawn. It never got its measurements. The one render that passed the gate kept the drawing in its place on the page, and none that brought it to life passed.

## Why it matters

Video models are moving from making footage to editing it. Every edit of real footage makes the same promise: change what was asked, keep the rest. That promise is cheap to state and hard to check by eye, and it gets harder when what was asked is a performance rather than a colour.

The result splits cleanly. Aleph 2 kept the room exactly (lag 0, every frame aligned) and set the ink creature moving where it lay, but never out of its place. Seedance 2.5 brought the drawing to life, and the blind rater agent (a Claude model reading a contact sheet) named the glass as what it answered, but the probe clip came back 0.29 s short of its 10 s input. The registered rescue, Aleph 2 steered by two keyframes, came to life as well, and lagged two analysis frames where the gate allows one, with 89.3 % of frames aligned where it needs 90 %. **At the probe and the rescue, every render that brought the drawing to life drifted just outside the timing gate, and the one that kept time moved it only where it lay, never out of its place.**

The study was registered to explain "why the model ignores the cues". The models did not ignore the cues. They answered them, and none kept the room's time and place while it did.

The failure path made it sharper. Seedance rendered the glass take once for each creature, and once more with a second seed as the registration requires. All six of these clips came back 12.708 s from a 12.767 s take, about 0.06 s short. Three of the six held the room in every frame they had: gold on both seeds, and paper on its first. The other three ranged from 21.9 % of frames aligned to none, and the paper re-render, the one the raters saw, lagged five frames. Alignment moved with the seed.

Five cold raters then watched the three rated clips, after first guessing from a still. From the stills, none named any creature's behaviour (0/5 each). From the clips, two of five named the ink creature's ("Backed away from it") and two of five the paper creature's ("Wilted"; the same two raters both times, an unregistered observation), with Wilson 95 % intervals of 0.12 to 0.77. None named the gold creature's (0/5, 0 to 0.43). The render that kept the room best is the one whose performance none of the five raters named.

## What it suggests

First, **time is a first-class property of a video edit.** A clip a few frames short looks fine to the eye, but it no longer matches the take frame for frame, and nothing measured on it can be trusted until that is settled. A gate that checks lag and duration before anything else is cheap, and it caught every failure here before any drift was measured. Any tool that edits real footage should report it.

Second, **keeping the room and performing in it seemed to pull against each other** on this take. At the probe and the rescue, the one render that kept time never left its place, and every render that acted drifted; on the glass take, the clip that held the room best is the one whose performance no rater named. Ten renders of one take, three of them rated, and five raters cannot say that this holds in general. They can say it is worth testing on purpose, with more takes and more seeds.

Third, **registering first turns a failure into a finding.** Without the gate written down in advance, I would have trimmed a 0.29 s shortfall and nudged a two-frame lag, and the seam view would have shown a success it had not earned. Here the misses are on the record: the gate records, each render's hash and every rating are in the repository, and anyone can check the numbers from a clone. The six glass renders play in the seam view.

The seam view still exists, for display only: the take under each render, the creature switch, a strip of which frames aligned and which did not, and the ratings beside them. It is labelled "not aligned, not measured", because that is what it is.

## Limitations

The sample is tiny: one take, three rated renders, five raters, so every interval spans at least 0.43 and no paired test of clip against still could reach significance. All five raters rated remotely, though two were planned in person. Line structure is a proxy for the room, not the room itself, and on this path nothing was measured with it. The full list of departures from the registration is in the write-up.

## Prior art

Simulon's Reality-Aware Rendering (announced 28 October 2026) is the nearest work; it is credited here, and nothing is copied from it.
