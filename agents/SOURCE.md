# agents: provenance of the agent definitions

Byte-for-byte copies of the studio hub's agent definitions (`~/projects/studio/.claude/agents/`), which Claude Code loads at session start. The briefs in `briefs/` are this repo's own. A change to a hub definition after Gate R needs a new copy, a new row here and a dated deviation entry.

| File | Hub path | Hub commit | SHA-256 |
|---|---|---|---|
| `blind-cue-rater.md` | `.claude/agents/blind-cue-rater.md` | `3929bf03d46edae7faf178054f5ce7f5a0558e45` | `20e9451f3018feb1486ea77b0d9b80093fcb0a381f0d566936ea235124b48b5b` |
| `blind-frame-picker.md` | `.claude/agents/blind-frame-picker.md` | `4397245329cd60d9d049fe84e0a147beb4e1e9e4` | `d48ccb0b3e7f8db7531ac959c90ece6a79f0183a7a2ac51b16f50a57940beb8a` |

Copied 3 Nov 2026 with `cp`. The commit is `git -C ~/projects/studio log -1 --format=%H -- <hub path>`; `uncommitted` means the hub file was new and not yet committed when it was copied, and the commit is filled in once the hub commits it (before Gate R). `tests/test_vendor.py` checks each hash, and, where the hub is present, that the hub file still matches.
