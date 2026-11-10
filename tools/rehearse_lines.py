#!/usr/bin/env python3
"""The rehearsal's lines job: seam/lines_job.py, unchanged, with the blind roots pointed at the rehearsal's
throwaway repo (as tests/conftest.py does), so its custody reads the rehearsal's ledgers. Run it only from
tools/rehearse.py, under ~/tools/ComfyUI/.venv/bin/python (read-only; nothing is installed there):

    python tools/rehearse_lines.py --repo blind/rehearsal --neutral <dir> -- measure --pair ... --render ...
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" not in argv:
        raise SystemExit("usage: rehearse_lines.py --repo DIR --neutral DIR -- <lines_job arguments>")
    k = argv.index("--")
    own, rest = argv[:k], argv[k + 1:]
    opts = dict(zip(own[::2], own[1::2]))
    from seam import blind, lines_job, points
    repo, neutral = Path(opts["--repo"]), Path(opts["--neutral"])
    blind.NEUTRAL_ROOT, blind.GIT_ROOT = neutral, repo
    blind.LOGS, blind.STATE, blind.TRANSCRIPTS = repo / "agents" / "logs", repo / "blind", repo / "blind" / "transcripts"
    blind.SEALED = repo / "sealed"
    blind.SEALED_STATE, blind.SEALED_TRANSCRIPTS = repo / "sealed" / "blind", repo / "sealed" / "blind" / "transcripts"
    points.PROMPTS = repo / "masks" / "prompts"
    return lines_job.main(rest)


if __name__ == "__main__":
    sys.exit(main())
