# vendor/runway: provenance

Byte-for-byte copies of the studio hub's Runway client and its tests, so a reader of the registration can check the client every paid call went through. The hub is Aaron's private repo `~/projects/studio`; these copies are what the registration freezes. The prototype never imports them (calls go through the hub's `tools/runway/runway.sh`); a change to the hub client after Gate R needs a new copy, a new row here and a dated deviation entry.

| File | Hub path | Hub commit | SHA-256 |
|---|---|---|---|
| `runway_gen.py` | `tools/runway/runway_gen.py` | `a631e723fb5dd82b36e5699c6970962f1dfa1b6a` | `555969bc779d78e34f062504b48520cd52c89a9969e4f6cd135815a97fac8e6e` |
| `test_runway_gen.py` | `tools/runway/test_runway_gen.py` | `a631e723fb5dd82b36e5699c6970962f1dfa1b6a` | `dae15c5e9807065703751d17f2cf12bc7ce8c4f497507b8776cbf8af334874cb` |

Copied 3 Nov 2026 with `cp`. The commit is `git -C ~/projects/studio log -1 --format=%H -- <hub path>`. `tests/test_vendor.py` checks each hash, and, where the hub is present, that the hub file still matches.
