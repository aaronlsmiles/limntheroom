# The 18-cell table: draft of the 10 unrated cells. APPROVED 3 Nov 2026 (cell 15 reworded); the table of record is `LAWS.md`

SEALED: never commit before the rating window closes. Drafted 31 Oct 2026 overnight by the sub-plan B worker (Opus 5.5), from the Gate L table (`laws-gate-L.md`), the two decoys and the curtain call. Nothing here is approved.

Materials × cues = 3 × 6 = 18 cells. The 8 rated cells passed Gate L and are in `sealed/laws.json`. The other 10 are below. Two of them are already fixed by Gate L: they are the sources of the decoys (gold.light → "Turned towards it", paper.breath → "Was blown along"). Two more are fixed in outline by the curtain call (gold turns to the light, paper glows).

Each row is written as the `p47-laws/1` fields would be: a behaviour, a rater label, a prompt clause (one phrase completing "At <t> s, when <what>, it …") and the touched object. All are `rated: false`.

| # | Cell | Behaviour (the law) | Label (Q2 wording) | Clause for the prompt | Touches | Source |
|---|---|---|---|---|---|---|
| 9 | gold.light | Turns towards the beam and basks in it, its gold catching the light | Turned towards it | turns towards the beam and basks in it, its gold catching the light | none | Gate L decoy; curtain call |
| 10 | paper.light | Glows as the light shines through it, like a paper lantern | Glowed | glows softly as the light shines through it, like a paper lantern | none | curtain call |
| 11 | paper.breath | Is blown along the desk, skittering, then comes to rest | Was blown along | is blown along the desk, skittering on its edges, then comes to rest | none | Gate L decoy |
| 12 | gold.breath | Stands firm, too heavy to be moved; its gold shimmers | Stood firm | stands firm against it, too heavy to be moved, while its gold shimmers | none | new |
| 13 | gold.pen | Rubs itself against the pen's barrel to polish its shine | Polished itself on it | rubs itself against the pen's barrel to polish its shine | pen | new |
| 14 | paper.pen | Lies down flat in front of the nib, waiting to be written on | Lay down in front of it | lies down flat in front of the nib, as if waiting to be written on | pen | new |
| 15 | gold.note | Reads the note and refuses: folds its arms and stays put | Refused it | reads the note and refuses: it folds its arms and stays put | note | new |
| 16 | paper.note | Reads the note and folds itself in half, like the note | Folded itself up | reads the note, then folds itself in half, just like the note | note | new |
| 17 | gold.hand | Steps onto the palm and stands tall, like a statue on a plinth | Posed on it | steps onto the offered palm and stands tall, like a statue on a plinth | hand | new |
| 18 | paper.hand | Slides onto the palm and curls up like a leaf | Curled up on it | slides onto the offered palm and curls up like a leaf | hand | new |

## Notes for the decision

- **Why it matters before Gate R.** The 18-cell table is registered (hashed, salted) with R0. Only the two decoys reach raters, as Q2 options. The other 8 unrated cells never reach a prompt or a rater unless a later card renders them.
- **Label clashes.** No draft label repeats a rated label or a decoy except the two decoy cells themselves. Rows 13 and 17 were kept distinct ("Polished itself on it", "Posed on it") on purpose.
- **Fixtures.** The public test fixtures use deliberately absurd fictional laws (spinning like a top, juggling dots, standing on its head, tipping a hat, counting to three). None of these drafts reuses one, so the public fixtures hint at nothing.
- **The torch clause in `laws.json`** says "the object standing upright on the desk beside it", so it holds for either hiding object (the paperback or the Outbox 8). If Aaron wants the object named in the prompt, change the clause after the shoot (before Gate R, a free change).
- **The curtain call** fires gold.light and paper.light alongside ink.light. The compiler handles one acting creature, so the curtain call's request is written by hand or by a small extension after these cells are approved.

Salt (Gate R, 10 Nov 2026): 7ebc3d91c4a464c6523ebef9fed93ab5
