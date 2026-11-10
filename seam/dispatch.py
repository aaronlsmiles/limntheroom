#!/usr/bin/env python3
"""Run one blind call as a bare `claude -p` session, then record it (PREREGISTRATION §7, §17).

    python seam/dispatch.py run --code bXXXXXXXXXX [--q2 sealed/q2-options.json]   # rater folders need --q2
    python seam/dispatch.py adjudicate --code bXXXXXXXXXX                        # an attempt stuck at dispatched
    python seam/dispatch.py addendum --render t01-ink                            # A1 manifest rows

Why a bare session and not a subagent: a subagent dispatched from a project session inherits that
session's context (the studio CLAUDE.md, AGENTS.md and memory, which name the project). This runs
`claude -p` with the folder itself as the working directory (directly under ~/.blind) and:
  --agents/--agent    the vendored agent file as the session's only system prompt;
  --tools Read        the only tool; `--restricted` confines it to the working directory and ignores the
                      user, project and local settings (no hooks, no plugins); `--strict-mcp-config` drops
                      every MCP server; `--disable-slash-commands` every skill; no `--allowedTools`;
  --model, --effort   pinned from the agent file; `--max-turns` its maxTurns (the record also counts turns);
  --session-id        a fresh UUID, logged in the ledger before the call (`dispatched`);
  --output-format stream-json --verbose   the event stream, which this process writes itself, by
                      exclusive create, as the audit transcript (`blind/transcripts/<code>.jsonl`).

Claude Code's own session store (under ~/.claude/projects, written while the call runs) is the
cross-check: it alone holds the dispatch text, the agent and the system prompt. It is copied (exclusive
create, `<code>.store.jsonl`) and then removed in a `finally`, since the Mem indexer walks that folder and a
rater session's reads hold the sealed Q2 options.

Before the call, the ledger and the registry must be committed at HEAD with this code `prepared` (prepare
commits them). After it, in a `finally`, the dispatcher commits the ledger and the registry, and only them,
with a fixed message ("blind ledger: <kind> <code> <status>"), so a recorded, failed or lost attempt is in
git history before anyone can delete or rewind the file. The stream is read through a pipe and kept in
memory while it is written to the audit file; the outcome is decided from those bytes, never by
re-reading a file that could have been unlinked or replaced.

The outcome of a call is one of:
  recorded             the folder's `record` checked it (valid or invalid; an invalid attempt frees the
                       second attempt);
  dispatch_failed      nothing reached the API: the in-memory stream holds no init, model or result event,
                       and the process exited non-zero. It counts against the two attempts;
  lost_after_dispatch  anything else: the call reached the API but the store is missing, duplicated or
                       does not match the stream, or the stream is unbound. The step closes as failed, with
                       no fresh attempt, and the attempt is flagged for disclosure in A1. So deleting or
                       copying a store after reading the answer gains nothing.
`adjudicate` settles an attempt left at `dispatched` (a crashed or killed dispatcher) as lost, always: the
files it could look at are erasable, so they never earn a fresh attempt. The answer is never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seam import blind  # noqa: E402

PROJECTS = Path.home() / ".claude" / "projects"
TIMEOUT_S = 1800
RUN_KEEP = ("num_turns", "subtype", "is_error", "terminal_reason", "duration_ms", "total_cost_usd", "stop_reason")


def command(st: dict, agent: dict, session_id: str) -> list[str]:
    spec = {agent["name"]: {"description": agent["description"], "prompt": agent["prompt"], "tools": ["Read"],
                            "model": agent["model"]}}
    return ["claude", "-p", st["dispatch"], "--agents", json.dumps(spec, sort_keys=True), "--agent", agent["name"],
            "--model", agent["model"], "--effort", agent["effort"], "--max-turns", str(agent["max_turns"]),
            "--tools", "Read", "--restricted", "--strict-mcp-config", "--disable-slash-commands",
            "--permission-mode", "dontAsk", "--session-id", session_id, "--output-format", "stream-json", "--verbose"]


def clean_env() -> dict:
    """The caller's environment minus anything that ties the child to the calling session."""
    return {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}


def store_dirs(code: str, projects=PROJECTS) -> list[Path]:
    """Claude Code's store folders for this folder's working directory (its encoded path ends in the code)."""
    p = Path(projects)
    return sorted(d for d in p.iterdir() if d.is_dir() and d.name.endswith(code)) if p.exists() else []


def store_hits(session_id: str, projects=PROJECTS) -> list[Path]:
    return sorted(Path(projects).glob(f"*/{session_id}.jsonl"))


def stream_info(data: bytes) -> tuple[dict, bool]:
    """From the in-memory stream: (the result event's kept fields, whether any init, model or result event
    reached it)."""
    info, reached = {}, False
    for line in data.decode("utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(e, dict):
            continue
        if e.get("type") in ("assistant", "result") or (e.get("type") == "system" and e.get("subtype") == "init"):
            reached = True
        if e.get("type") == "result":
            info = {k: e.get(k) for k in RUN_KEEP if k in e}
    return info, reached


def pump(cmd, *, cwd, out_file, popen=subprocess.Popen, timeout=TIMEOUT_S) -> tuple[bytes, int | None]:
    """Run the call with its stdout on a pipe; every chunk goes to memory and to the open audit file."""
    import threading
    proc = popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                 env=clean_env())
    timer = threading.Timer(timeout, proc.kill)
    timer.start()
    buf = bytearray()
    try:
        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                break
            buf += chunk
            out_file.write(chunk)
            out_file.flush()
        code = proc.wait()
    finally:
        timer.cancel()
    return bytes(buf), code


def purge(code: str, projects=PROJECTS) -> None:
    for d in store_dirs(code, projects):
        if d.parent.resolve() == Path(projects).resolve():
            shutil.rmtree(d)


def _record(st, stream, store, q2):
    kind = st["kind"]
    if kind == "prompt-frame":
        from seam import frame_pick
        return frame_pick.record(st["code"], stream, store)
    if kind.startswith(("take-", "render-")):
        from seam import points
        return points.record(st["code"], stream, store)
    if kind.startswith("rater-"):
        if not q2:
            raise blind.BlindError("a rater folder needs --q2 (the sealed Q2 options)")
        return blind.record_rater(st["code"], stream, store, q2_path=q2)
    raise blind.BlindError(f"unknown folder kind {kind}")


def _status(st) -> str:
    log, step = blind.ledger_load(st)
    return next(a["status"] for a in step["attempts"] if a["code"] == st["code"])


def run(code: str, *, q2=None, popen=subprocess.Popen, projects=PROJECTS, record=_record, timeout=TIMEOUT_S) -> dict:
    st, _ = blind.find_state(code)
    if q2 is None and st["kind"].startswith("rater-"):
        raise blind.BlindError("a rater folder needs --q2 (the sealed Q2 options)")
    blind.require_prepared_at_head(st)
    agent = blind.agent_spec(st["agent"])
    sid = str(uuid.uuid4())
    cmd = command(st, agent, sid)
    out_dir = Path(st["transcripts"])
    out_dir.mkdir(parents=True, exist_ok=True)
    stream = out_dir / f"{code}.jsonl"
    if stream.exists():
        raise blind.BlindError(f"{stream.name} exists: a folder is dispatched once")
    blind.mark_dispatched(st, session_id=sid, command_sha256=blind.sha256_json(cmd), agent=agent)
    exit_code, info, out = None, {}, None
    try:
        with open(stream, "xb") as f:
            data, exit_code = pump(cmd, cwd=st["folder"], out_file=f, popen=popen, timeout=timeout)
        info, reached = stream_info(data)
        run_info = {**info, "exit_code": exit_code}
        if not reached and exit_code != 0:
            blind.mark_dispatch_failed(st, "nothing-reached-api", exit_code, info)
            out = {"code": code, "status": "dispatch_failed", "run": info}
            return out
        if not stream.exists() or blind.sha256_path(stream) != blind.sha256_bytes(data):
            blind.mark_lost(st, "stream-replaced", run_info)
            out = {"code": code, "status": "lost_after_dispatch", "reason": "stream-replaced", "run": info}
            return out
        hits = store_hits(sid, projects)
        if not reached or len(hits) != 1:
            blind.mark_lost(st, "no-result" if not reached else ("store-duplicate" if hits else "store-missing"), run_info)
            out = {"code": code, "status": "lost_after_dispatch", "run": info}
            return out
        store = blind.keep_transcript(hits[0], code, out_dir, ".store.jsonl")
        try:
            record(st, stream, store, q2)
        except blind.Lost as e:
            blind.mark_lost(st, e.reason, run_info)
            out = {"code": code, "status": "lost_after_dispatch", "reason": e.reason, "run": info}
            return out
        log, step = blind.ledger_load(st)
        att = blind.find_attempt(step, code, ("recorded",))
        att["run"] = run_info
        blind.ledger_save(st, log)
        out = {"code": code, "status": "recorded", "valid": att["valid"], "problems": att["problems"],
               "run": att["run"], "result_status": (step.get("result") or {}).get("status")}
        return out
    finally:
        purge(code, projects)
        blind.commit_ledger(st["ledger"]["path"], st["kind"], code, _status(st))


def adjudicate(code: str, *, projects=PROJECTS) -> dict:
    """Settle an attempt left at `dispatched` (a crashed or killed dispatcher): always lost after dispatch.
    The stream and the store are erasable, so their absence proves nothing and never earns a fresh attempt."""
    st, _ = blind.find_state(code)
    log, step = blind.ledger_load(st)
    blind.find_attempt(step, code, ("dispatched",))
    try:
        blind.mark_lost(st, "adjudicated", None)
        log, step = blind.ledger_load(st)
        a = blind.find_attempt(step, code, ("lost_after_dispatch",))
        a["adjudicated_utc"] = blind.now()
        blind.ledger_save(st, log)
    finally:
        purge(code, projects)
        blind.commit_ledger(st["ledger"]["path"], st["kind"], code, _status(st))
    return {"code": code, "status": "lost_after_dispatch"}


def addendum_rows(render: str, *, root=ROOT) -> list[str]:
    """`shasum -a 256` rows for addendum A1: the render's ledgers, the registry, its prompt files, and the
    folder maps and transcripts of every attempt (gitignored, so hashed here)."""
    from seam import frame_pick, points
    paths = [frame_pick.log_path(render), points._log_path("render", render), blind.registry_path(),
             Path(points.PROMPTS) / "render" / f"{render}.p1.json", Path(points.PROMPTS) / "render" / f"{render}.json"]
    for lp in paths[:2]:
        if lp.exists():
            log = json.loads(lp.read_text(encoding="utf-8"))
            steps = [log] if "attempts" in log else [s for s in log.get("steps", {}).values() if "attempts" in s]
            for s in steps:
                for a in s.get("attempts", []):
                    paths += [Path(blind.STATE) / f"{a['code']}.json", Path(blind.TRANSCRIPTS) / f"{a['code']}.jsonl",
                              Path(blind.TRANSCRIPTS) / f"{a['code']}.store.jsonl"]
    rows = []
    for p in paths:
        if Path(p).exists():
            rows.append(f"{blind.sha256_path(p)}  {Path(p).resolve().relative_to(Path(root).resolve())}")
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python seam/dispatch.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--code", required=True)
    r.add_argument("--q2", help="sealed/q2-options.json, for a rater folder")
    j = sub.add_parser("adjudicate")
    j.add_argument("--code", required=True)
    ad = sub.add_parser("addendum")
    ad.add_argument("--render", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "run":
            print(json.dumps(run(a.code, q2=a.q2), indent=1))
        elif a.cmd == "adjudicate":
            print(json.dumps(adjudicate(a.code), indent=1))
        else:
            print("\n".join(addendum_rows(a.render)))
    except (blind.BlindError, OSError, ValueError) as e:
        print(f"dispatch: refuse: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
