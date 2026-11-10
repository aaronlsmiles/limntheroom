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

Check a clone: `shasum -a 256 -c --ignore-missing MANIFEST.sha256` passes on every published row. Media and sealed files are hashed but not published before the rating window closes.
