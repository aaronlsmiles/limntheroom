# Registration record

Limn the Room's preregistration was registered on **10 November 2026** (Gate R), before any generation call of any kind.

| | |
|---|---|
| Registration commit | `945c54d206be3b9cbbddda4000cd3e1ee1caa99f`, this repository's first commit, which carries the annotated tag `registered` (tag object `ee306e64cdee0135afb668e4f483e2f1227c2abe`) |
| What it registers | `PREREGISTRATION.md`, and `MANIFEST.sha256` with SHA-256 `148c3ce841af8bfba514df28f7dac997782eeb1af1905add9c5230d457a33f11` (360 rows) |
| The private history | head `045efe8e2d0b388360781634ade38552610740c9` at registration. It holds every blind-agent ledger commit, media and an early wording leak; it is published as a git bundle when the rating window closes (PREREGISTRATION §18) |
| Software Heritage | "save code now" request 2635273; visit of 2026-11-10 03:51:13 UTC, status full. Snapshot `swh:1:snp:7e9cb48129b03a2ea74d9357f18d9ed0c8de6953`: `refs/heads/main` → the registration commit, `refs/tags/registered` → release `swh:1:rel:ee306e64cdee0135afb668e4f483e2f1227c2abe` |
| Reviews before registration | an adversarial review and an independent gate review in two rounds; every finding and its decision is in `LOG.md` (10 Nov 2026, night) |
| First paid or hosted call | after all of the above; it is the first row of `runs/runway-calls.jsonl` |
| Close (17 Nov 2026) | the rating window closed on 17 Nov; the sealed files were published in commit `33efcb9081cbf85ee31f820d24e958d4d1222c4c` (addendum A4). The private history is the git bundle `limntheroom-private-history.bundle` on the GitHub release `close` (tag on `33efcb9`), sha256 `45ba71a0095ececdc6171ee32ad4852ebc46af81df6d431b6cddb0eec58a7c08`, 241,628,825 bytes, with refs `main` → `6f001247155eb35f62a99c78a64377ca3d9abcd5` (its ancestors include the registration's private head `045efe8`), `public` → `33efcb9` and the tag `registered`. This row is recorded in the commit after those heads, so it is not in the bundle. Software Heritage: "save code now" request 2660006; visit of 2026-11-17 16:14:43 UTC, status full. Snapshot `swh:1:snp:a2afe63858f3aeed3a4aa6b58881e722b1f0d7e7`: `refs/heads/main` → `e436fca` (the commit that recorded this row's bundle), `refs/tags/close` → `33efcb9`, `refs/tags/registered` → release `swh:1:rel:ee306e64cdee0135afb668e4f483e2f1227c2abe`. Release assets are not archived, so the bundle's copy of record is the GitHub release |

Check a clone: `shasum -a 256 -c --ignore-missing MANIFEST.sha256` passes on every published row. Media and sealed files are hashed but not published before the rating window closes. Since 17 Nov 2026 the sealed files are published, so a clone's check covers them too (415 rows; the 47 others are media, models and session transcripts, hashed only).
