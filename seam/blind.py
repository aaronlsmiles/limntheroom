"""The blind agents' side of P47: folders, ledgers, transcripts, read logs and frozen briefs.

Two read-only agents work from a folder of opaque-named files and a frozen brief:
- `blind-frame-picker` (agents/blind-frame-picker.md): the render mask's prompt frame
  (seam/frame_pick.py) and the mask point prompts (seam/points.py);
- `blind-cue-rater` (agents/blind-cue-rater.md): the probe, draft and machine-rater ratings, from
  briefs rendered into sealed/briefs/ (they carry the Q2 options).

Every call goes through seam/dispatch.py: a bare `claude -p` session run from the folder itself, with
the agent file as its only system prompt, Read as its only tool, the model pinned and no project
context. What this module guarantees around that call:

- **A ledger per call site** (a committed JSON log). Preparing a folder appends a `prepared` attempt
  (code, dispatch hash, inventory hash, time) before anything is dispatched; a new folder is refused
  while any attempt is unrecorded, and every prepared folder counts against MAX_ATTEMPTS. So no one can
  prepare several folders and keep the answer they like.
- **A transcript is bound to its dispatch.** Its first message must be the stored dispatch text, its
  session id the one dispatch.py logged, its agent the expected one (the `agent-setting` events and the
  system prompt's hash), every message from the pinned model, and Read the only tool. An empty, unparseable
  or unbound transcript is refused outright: it is not an attempt and does not free a fresh one.
- **Nothing an agent writes reaches a committed file as text.** Reads of files outside the folder's
  inventory, reads outside the folder and unknown tool names are stored as hashes and counts; problems
  name fields by count or position; free-text answers are kept only as a hash. The full transcript is
  copied to a gitignored folder (`blind/transcripts/`, or `sealed/blind/transcripts/` for the rater),
  its hash in the ledger, so an invalid attempt can be audited.
- **Context is allowlisted.** Only the user's global CLAUDE.md may load (a bare session loads none).
- **Folders live directly under one persistent neutral root** (`~/.blind`), under a random code, with no
  project name, take id or material word anywhere in the path.

    python seam/blind.py render-brief --template agents/briefs/rater-probe-draft.md \
        --q2 sealed/q2-options.json --out sealed/briefs/probe-draft-rater.md
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BRIEFS = ROOT / "agents" / "briefs"
LOGS = ROOT / "agents" / "logs"
STATE = ROOT / "blind"                            # gitignored: folder maps (picker)
TRANSCRIPTS = ROOT / "blind" / "transcripts"      # gitignored: every picker transcript, for audit
SEALED_STATE = ROOT / "sealed" / "blind"          # rater folder maps (codes keyed to renders)
SEALED_TRANSCRIPTS = ROOT / "sealed" / "blind" / "transcripts"
SEALED = ROOT / "sealed"
PICKER = ROOT / "agents" / "blind-frame-picker.md"
RATER = ROOT / "agents" / "blind-cue-rater.md"
NEUTRAL_ROOT = Path.home() / ".blind"            # persistent; not /var/folders/.../T, which macOS purges
GIT_ROOT = ROOT                                   # ledgers count only when committed here
MANIFEST = ROOT / "MANIFEST.sha256"
# These roots are fixed: no command takes another ledger, state or transcript directory (a second ledger
# would let the controller keep the answer it likes). Tests set the constants.
BRIEF_NAME = "agent-brief.md"
RATER_BRIEF_NAME = "rater-brief.md"
DISPATCH = "Your folder is {folder}. Read {brief} in it first, then follow it exactly."
MODEL = "claude-opus-5-5"
MAX_ATTEMPTS = 2
# What a session can hold of a folder's images (hub call 129). Claude Code sends every image the agent
# reads as a quality-90 JPEG, in base64. The plain-desk take folders (65 stills, 15.2 MB) were answered
# in 10 turns; the first textured one (65 stills, about 29 MB) lost earlier stills from the session and
# ran out of turns, twice. A folder over the budget is refused before anything is written or logged.
PAYLOAD_BUDGET = 16 * 2**20
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")
OPEN = ("prepared", "dispatched")
PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
FORBIDDEN_IN_PATH = re.compile(r"(^|[^a-z])(ink|gold|paper|limn)|t0\d")
KNOWN_TOOLS = {"Read", "Bash", "Edit", "Write", "Glob", "Grep", "WebFetch", "WebSearch", "Agent", "Task",
               "NotebookEdit", "TodoWrite", "SubagentHandback", "Skill", "ToolSearch"}
CONTEXT_ALLOW = ("<home>/.claude/CLAUDE.md",)
Q2_SCHEMA = "p47-q2-options/1"
NOTHING = "Nothing in particular"
CANT_TELL = "Can't tell"
SHEET_GREY = 128
HOME_OUTLINE = (150, 150, 150)


class BlindError(ValueError):
    pass


# --- small helpers ------------------------------------------------------------------------------
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_path(p) -> str:
    return sha256_bytes(Path(p).read_bytes())


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_json(obj) -> str:
    return sha256_bytes(canonical(obj))


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def loads_strict(text: str):
    """JSON with no duplicate keys and no NaN or Infinity."""
    def pairs(kv):
        d = {}
        for k, v in kv:
            if k in d:
                raise BlindError("a JSON object repeats a key")
            d[k] = v
        return d

    def no_constants(c):
        raise BlindError("a non-finite number in the JSON")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=no_constants)
    except json.JSONDecodeError as e:
        raise BlindError(f"not valid JSON ({e.msg})") from None


def save_json(path, obj) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def default_root() -> Path:
    return NEUTRAL_ROOT


def new_code() -> str:
    return "b" + secrets.token_hex(5)


def dispatch_prompt(folder, brief=BRIEF_NAME) -> str:
    return DISPATCH.format(folder=folder, brief=brief)


def mask_digest(mask) -> str:
    a = np.asarray(mask, bool)
    return sha256_bytes(f"{a.shape}\n".encode() + np.packbits(a.reshape(-1)).tobytes())


# --- folders ------------------------------------------------------------------------------------
def check_path_words(path) -> None:
    for part in Path(path).parts:
        if FORBIDDEN_IN_PATH.search(part.lower()):
            raise BlindError("the path holds the project name, a take id or a material word")


def check_folder_path(folder) -> Path:
    folder = Path(folder).resolve()
    if folder.parent != Path(NEUTRAL_ROOT).resolve():
        raise BlindError(f"a folder must sit directly under the neutral root {NEUTRAL_ROOT}")
    check_path_words(folder)
    try:
        folder.relative_to(ROOT.resolve())
    except ValueError:
        return folder
    raise BlindError("the folder is inside the project repo")


def payload_bytes(files: dict) -> int:
    """Bytes of base64 a session is sent for the folder's images: each image re-encoded as a quality-90
    JPEG, as Claude Code sends it (matched to the byte on the t01d and t01e take folders, call 129). An
    image that does not decode counts at its own size."""
    import cv2
    total = 0
    for name, data in files.items():
        if Path(name).suffix.lower() not in IMAGE_SUFFIXES:
            continue
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        n = len(data)
        if img is not None:
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if ok:
                n = len(buf)
        total += 4 * ((n + 2) // 3)
    return total


def write_folder(folder, files: dict, budget: int | None = None) -> list[dict]:
    """Write `files` ({plain name: bytes}) into a new folder; [{name, sha256}] sorted by name. Refused,
    with nothing written, when the images exceed `budget` (default PAYLOAD_BUDGET) as a session sees
    them: callers write the folder before they log an attempt, so a refusal uses none."""
    folder = check_folder_path(folder)
    if folder.exists():
        raise BlindError(f"{folder.name} exists: a folder is written once")
    for name in files:
        if Path(name).name != name or name in ("", ".", ".."):
            raise BlindError("want plain file names")
        check_path_words(name)
    budget = PAYLOAD_BUDGET if budget is None else budget
    size = payload_bytes(files)
    if size > budget:
        raise BlindError(f"the folder's images come to {size / 2**20:.1f} MB as the session receives them, "
                         f"over the {budget / 2**20:.1f} MB budget: fewer or smaller stills (call 129)")
    folder.mkdir(parents=True)
    for name, data in files.items():
        (folder / name).write_bytes(data)
    return [{"name": n, "sha256": sha256_bytes(files[n])} for n in sorted(files)]


def inventory(folder) -> list[dict]:
    return [{"name": p.name, "sha256": sha256_path(p)} for p in sorted(Path(folder).iterdir()) if p.is_file()]


def png_bytes(rgb) -> bytes:
    import cv2
    ok, buf = cv2.imencode(".png", cv2.cvtColor(np.asarray(rgb, np.uint8), cv2.COLOR_RGB2BGR))
    if not ok:
        raise BlindError("PNG encoding failed")
    return buf.tobytes()


def resize(rgb, size):
    """`size` = (height, width); area interpolation."""
    import cv2
    return cv2.resize(np.asarray(rgb, np.uint8), (size[1], size[0]), interpolation=cv2.INTER_AREA)


def dashed_outline(rgb, mask, *, colour=HOME_OUTLINE, dash=8, gap=6, thickness=2):
    """A copy of `rgb` with the outline of `mask` drawn as a thin dashed line (it marks a place)."""
    import cv2
    img = np.ascontiguousarray(np.asarray(rgb, np.uint8).copy())
    cs, _ = cv2.findContours(np.asarray(mask, np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    period = dash + gap
    for c in cs:
        pts = c[:, 0, :]
        if len(pts) < 2:
            continue
        pts = np.vstack([pts, pts[:1]])
        run = 0.0
        for p, q in zip(pts[:-1], pts[1:]):
            if run % period < dash:
                cv2.line(img, (int(p[0]), int(p[1])), (int(q[0]), int(q[1])), colour, thickness, cv2.LINE_AA)
            run += float(np.hypot(*(q - p)))
    return img


def write_state(state_dir, code: str, record: dict) -> Path:
    p = Path(state_dir) / f"{code}.json"
    if p.exists():
        raise BlindError(f"{p.name} exists")
    save_json(p, record)
    return p


def read_state(state_dir, code: str) -> dict:
    p = Path(state_dir) / f"{code}.json"
    if not p.exists():
        raise BlindError(f"no folder map {p.name} in {state_dir}")
    return json.loads(p.read_text(encoding="utf-8"))


def find_state(code: str, dirs=None) -> tuple[dict, Path]:
    """(folder map, the directory it is in)."""
    for d in dirs or (STATE, SEALED_STATE):
        p = Path(d) / f"{code}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")), Path(d)
    raise BlindError(f"no folder map for {code}")


# --- the ledger ---------------------------------------------------------------------------------
def new_step() -> dict:
    return {"attempts": [], "result": None}


def ledger_load(st) -> tuple[dict, dict]:
    """(log, step) for a folder: the step is the log itself, or log['steps'][name]."""
    p = Path(st["ledger"]["path"])
    if not p.exists():
        raise BlindError(f"no ledger at {p.name}")
    log = json.loads(p.read_text(encoding="utf-8"))
    name = st["ledger"]["step"]
    step = log if name is None else log["steps"].setdefault(name, new_step())
    return log, step


def ledger_save(st, log) -> None:
    save_json(st["ledger"]["path"], log)


def open_attempts(step) -> list[dict]:
    return [a for a in step.get("attempts", []) if a["status"] in OPEN]


def check_can_prepare(step, what: str) -> None:
    if open_attempts(step):
        raise BlindError(f"{what}: an earlier folder is still unrecorded; record it (or its dispatch failure) first")
    if step.get("result") is not None or len(step.get("attempts", [])) >= MAX_ATTEMPTS:
        raise BlindError(f"{what}: closed (a result is logged, or both attempts are used)")


def prepared_attempt(code, dispatch, inv) -> dict:
    return {"code": code, "status": "prepared", "dispatch_sha256": sha256_bytes(dispatch.encode()),
            "inventory_sha256": sha256_json(inv), "prepared_utc": now()}


def find_attempt(step, code, status=("dispatched",)) -> dict:
    for a in step.get("attempts", []):
        if a["code"] == code:
            if a["status"] not in status:
                raise BlindError(f"{code} is {a['status']}, not {' or '.join(status)}")
            return a
    raise BlindError(f"{code} is not an attempt in this ledger")


def mark_dispatched(st, *, session_id: str, command_sha256: str, agent: dict) -> dict:
    log, step = ledger_load(st)
    a = find_attempt(step, st["code"], ("prepared",))
    a.update(status="dispatched", session_id=session_id, command_sha256=command_sha256, agent=agent["name"],
             agent_sha256=agent["sha256"], model=agent["model"], dispatched_utc=now())
    ledger_save(st, log)
    return a


DISPATCH_FAILURES = ("nothing-reached-api",)


def mark_dispatch_failed(st, reason: str, exit_code=None, run=None) -> dict:
    """Nothing reached the API (no result, no model turn, no session store): logged, and it counts
    against MAX_ATTEMPTS. Anything else is `mark_lost`."""
    if reason not in DISPATCH_FAILURES:
        raise BlindError(f"reason {reason!r}: want one of {DISPATCH_FAILURES}")
    log, step = ledger_load(st)
    a = find_attempt(step, st["code"], ("dispatched",))
    a.update(status="dispatch_failed", reason=reason, exit_code=exit_code, run=run, recorded_utc=now(), valid=False)
    close_if_spent(step)
    ledger_save(st, log)
    return a


LOST_REASONS = ("no-result", "store-missing", "store-duplicate", "store-mismatch", "stream-replaced", "unbound", "adjudicated")


class Lost(BlindError):
    """The call reached the API but its record cannot be trusted (a missing, duplicated or mismatched session
    store, or an unbound stream). The step closes as failed, with no fresh attempt, and is disclosed in A1."""

    def __init__(self, reason: str):
        if reason not in LOST_REASONS:
            raise ValueError(reason)
        super().__init__(f"lost after dispatch ({reason})")
        self.reason = reason


def mark_lost(st, reason: str, run=None) -> dict:
    if reason not in LOST_REASONS:
        raise BlindError(f"reason {reason!r}: want one of {LOST_REASONS}")
    log, step = ledger_load(st)
    a = find_attempt(step, st["code"], ("dispatched",))
    a.update(status="lost_after_dispatch", reason=reason, run=run, recorded_utc=now(), valid=False, disclose_in_a1=True)
    step["result"] = {"status": "failed", "still": None, "frame": None, "lost_after_dispatch": st["code"]}
    ledger_save(st, log)
    return a


def registry_path() -> Path:
    return Path(LOGS) / "registry.jsonl"


def register(kind: str, ident: str, code: str) -> None:
    """Append a prepared code to the append-only registry (committed with the ledgers)."""
    p = registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": kind, "id": ident, "code": code, "utc": now()}, sort_keys=True) + "\n")


def registry_codes(kind: str, ident: str) -> list[str]:
    p = registry_path()
    if not p.exists():
        return []
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r["code"] for r in rows if r["kind"] == kind and r["id"] == ident]


def check_registry(step, kind: str, ident: str) -> None:
    """A rewound or forked ledger lacks codes the registry holds."""
    if [a["code"] for a in step.get("attempts", [])] != registry_codes(kind, ident):
        raise BlindError(f"{ident}: the ledger's attempts are not the registry's (rewound or forked)")


COMMIT_TRAILER = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"


def _git(*args):
    return subprocess.run(["git", "-C", str(GIT_ROOT), *args], capture_output=True, text=True)


def _repo_rel(path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(GIT_ROOT).resolve()))
    except ValueError:
        raise BlindError(f"{Path(path).name} is not a ledger in the repo") from None


def require_committed(path) -> None:
    """The file is tracked in the repo and unmodified at HEAD."""
    rel = _repo_rel(path)
    if _git("ls-files", "--error-unmatch", "--", rel).returncode:
        raise BlindError(f"{rel} is not committed")
    if _git("diff", "--quiet", "HEAD", "--", rel).returncode:
        raise BlindError(f"{rel} has changes not committed at HEAD")


def require_clean_or_new(path) -> None:
    """Before a prepare: a ledger (or the registry) is either new (in neither HEAD nor the tree) or committed
    and clean. So a ledger deleted, rewound or edited since its last commit cannot be prepared over."""
    rel = _repo_rel(path)
    if _git("cat-file", "-e", f"HEAD:{rel}").returncode == 0:
        require_committed(path)
    elif Path(path).exists():
        raise BlindError(f"{rel} exists but was never committed")


def commit_ledger(ledger, kind: str, code: str, status: str) -> str | None:
    """Commit the ledger and the registry, and only them, with a fixed message (no agent text)."""
    rels = [_repo_rel(ledger), _repo_rel(registry_path())]
    if _git("add", "--", *rels).returncode:
        raise BlindError("git add of the ledger failed")
    if _git("diff", "--cached", "--quiet", "--", *rels).returncode == 0:
        return None
    msg = f"blind ledger: {kind} {code} {status}\n\n{COMMIT_TRAILER}"
    if _git("commit", "-q", "-m", msg, "--", *rels).returncode:
        raise BlindError("git commit of the ledger failed")
    return _git("rev-parse", "HEAD").stdout.strip()


def require_prepared_at_head(st) -> None:
    """Before a dispatch: the ledger and the registry are committed at HEAD with this code `prepared`."""
    p = Path(st["ledger"]["path"])
    require_committed(p)
    require_committed(registry_path())
    log, step = ledger_load(st)
    find_attempt(step, st["code"], ("prepared",))
    if st["code"] not in registry_codes(st["kind"], st["id"]):
        raise BlindError(f"{st['code']} is not in the committed registry")


def close_if_spent(step, failed=None) -> None:
    if step["result"] is None and len(step["attempts"]) >= MAX_ATTEMPTS and not open_attempts(step):
        step["result"] = failed or {"status": "failed"}


# --- agent files --------------------------------------------------------------------------------
def agent_spec(path) -> dict:
    """The agent definition: frontmatter fields and the body (its whole system prompt)."""
    text = Path(path).read_text(encoding="utf-8")
    parts = text.split("---\n")
    if len(parts) < 3 or parts[0] != "":
        raise BlindError(f"{Path(path).name}: no frontmatter")
    front = {}
    for line in parts[1].splitlines():
        k, _, v = line.partition(":")
        if k.strip():
            front[k.strip()] = v.strip()
    body = "---\n".join(parts[2:]).strip()
    tools = [t.strip() for t in front.get("tools", "").split(",") if t.strip()]
    if tools != ["Read"]:
        raise BlindError(f"{Path(path).name}: a blind agent has Read only")
    return {"name": front["name"], "description": front.get("description", ""), "prompt": body, "tools": tools,
            "model": front.get("model", MODEL), "effort": front.get("effort", "high"),
            "max_turns": int(front.get("maxTurns", 40)), "sha256": sha256_path(path),
            "prompt_sha256": sha256_bytes(body.encode())}


# --- transcripts --------------------------------------------------------------------------------
def load_transcript(path) -> list[dict]:
    data = Path(path).read_bytes()
    if not data.strip():
        raise BlindError("the transcript is empty")
    try:
        evs = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BlindError("the transcript is not JSON lines") from None
    if not evs or not all(isinstance(e, dict) for e in evs):
        raise BlindError("the transcript holds no events")
    return evs


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


def bind_transcript(evs, *, dispatch: str, session_id: str) -> None:
    """Refuse a transcript that is not this dispatch's: its first message must be the dispatch text, and
    every event must carry the session id dispatch.py logged."""
    msgs = [e for e in evs if e.get("type") in ("user", "assistant")]
    if not msgs or msgs[0]["type"] != "user" or _text((msgs[0].get("message") or {}).get("content")) != dispatch:
        raise BlindError("the transcript's first message is not this folder's dispatch")
    sids = {e.get("sessionId") for e in evs if "sessionId" in e}
    if sids != {session_id}:
        raise BlindError("the transcript's session is not the one dispatched")


def identity(evs) -> dict:
    agents, models, tools, prompts = set(), set(), set(), set()
    for e in evs:
        if e.get("type") == "agent-setting":
            agents.add(e.get("agentSetting"))
        elif e.get("type") == "assistant":
            models.add((e.get("message") or {}).get("model"))
        elif e.get("type") == "attachment" and (e.get("attachment") or {}).get("type") == "prompt_snapshot":
            a = e["attachment"]
            prompts.add(sha256_bytes("\n".join(a.get("systemPrompt") or []).encode()))
            for t in a.get("tools") or []:
                tools.add(t.get("name") if isinstance(t, dict) else str(t))
    return {"agents": sorted(map(str, agents)), "models": sorted(map(str, models)),
            "system_prompt_sha256": sorted(prompts), "tools": sorted(t if t in KNOWN_TOOLS else "unlisted" for t in tools)}


def identity_problems(ident: dict, agent: dict) -> list[str]:
    probs = []
    if ident["agents"] != [agent["name"]]:
        probs.append("the session's agent is not the expected one")
    if ident["models"] != [agent["model"]]:
        probs.append("a message is not from the pinned model")
    if ident["system_prompt_sha256"] != [agent["prompt_sha256"]]:
        probs.append("the system prompt is not the agent definition's")
    if ident["tools"] and ident["tools"] != ["Read"]:
        probs.append("the session had tools other than Read")
    return probs


def _blocks(evs):
    for e in evs:
        if e.get("type") == "assistant":
            msg = e.get("message") or {}
            for b in msg.get("content") or []:
                if isinstance(b, dict):
                    yield msg, b


def tool_calls(evs) -> list[tuple[str, dict]]:
    """(name, input) per tool call, de-duplicated by call id (one turn can span several lines)."""
    seen, calls = set(), []
    for _, b in _blocks(evs):
        if b.get("type") == "tool_use" and b.get("id") not in seen:
            seen.add(b.get("id"))
            calls.append((b.get("name"), b.get("input") or {}))
    return calls


def final_text(evs) -> str:
    """The agent's answer: the text of its last message."""
    texts = []
    for msg, b in _blocks(evs):
        if b.get("type") == "text" and (msg.get("id"), b.get("text")) not in texts:
            texts.append((msg.get("id"), b.get("text")))
    if not texts:
        return ""
    last = texts[-1][0]
    return "".join(t for mid, t in texts if mid == last)


CONTEXT = re.compile(r"Contents of (\S+?) \(")


def _home_rel(path: str) -> str:
    home = str(Path.home())
    return "<home>/" + os.path.relpath(path, home) if path.startswith(home + os.sep) else path


def context_files(evs) -> list[dict]:
    """Every context file loaded into the run (CLAUDE.md, memory), once each, with its content's hash."""
    out, seen = [], set()

    def add(kind, path, content):
        shown = _home_rel(path)
        if (kind, shown) not in seen:
            seen.add((kind, shown))
            out.append({"type": kind, "path": shown,
                        "sha256": sha256_bytes(content.encode()) if isinstance(content, str) else None})

    for e in evs:
        a = e.get("attachment") or {}
        if e.get("type") == "attachment" and a.get("type") == "instructions":
            for f in a.get("files") or []:
                if isinstance(f, dict) and f.get("path"):
                    add(str(f.get("type") or "unknown"), f["path"], f.get("content"))
        elif e.get("type") == "attachment" and a.get("type") == "nested_memory" and a.get("path"):
            add("nested", a["path"], a.get("content"))
        elif e.get("type") == "user":
            for p in CONTEXT.findall(_text((e.get("message") or {}).get("content"))):
                add("text", p, None)
    return out


def read_log(folder, evs, names=None, context_evs=None) -> dict:
    """What the agent read and did. A read of a listed file is `<folder>/<name>`; any other path (which
    the agent chose, so it may carry text) is stored only as a hash, and counted."""
    folder = Path(folder)
    names = set(names) if names is not None else {p.name for p in folder.iterdir() if p.is_file()}
    base = os.path.realpath(folder)
    reads, outside, unlisted = [], [], []
    for n, i in tool_calls(evs):
        if n != "Read":
            continue
        raw = str(i.get("file_path", ""))
        real = os.path.realpath(raw) if raw else ""
        if real.startswith(base + os.sep) and os.path.relpath(real, base) in names:
            reads.append(f"<folder>/{os.path.relpath(real, base)}")
        elif real.startswith(base + os.sep):
            unlisted.append(sha256_bytes(raw.encode()))
            reads.append("<unlisted>")
        else:
            outside.append(sha256_bytes(raw.encode()))
            reads.append("<outside>")
    others = [n if n in KNOWN_TOOLS else "unlisted" for n, _ in tool_calls(evs) if n != "Read"]
    read_set = set(reads)
    return {"reads": reads, "outside": {"count": len(outside), "sha256": outside},
            "unlisted": {"count": len(unlisted), "sha256": unlisted}, "other_tools": others,
            "context_files": context_files(evs if context_evs is None else context_evs),
            "unread": sorted(n for n in names if f"<folder>/{n}" not in read_set)}


def attempt_problems(log: dict, brief=BRIEF_NAME) -> list[str]:
    probs = []
    if log["outside"]["count"]:
        probs.append(f"{log['outside']['count']} read(s) outside the folder")
    if log["unlisted"]["count"]:
        probs.append(f"{log['unlisted']['count']} read(s) of files not in the folder's list")
    if log["other_tools"]:
        probs.append(f"{len(log['other_tools'])} call(s) to tools other than Read")
    if not log["reads"] or log["reads"][0] != f"<folder>/{brief}":
        probs.append(f"the brief ({brief}) was not the first file read")
    bad = [c for c in log["context_files"] if c["path"] not in CONTEXT_ALLOW]
    if bad:
        probs.append(f"{len(bad)} context file(s) outside the allowlist were loaded")
    return probs


def keep_transcript(path, code: str, out_dir, suffix=".jsonl") -> Path:
    """The audit copy, created exclusively (an existing copy is never overwritten)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{code}{suffix}"
    if Path(path).resolve() == dst.resolve():
        return dst
    try:
        with open(dst, "xb") as f:
            f.write(Path(path).read_bytes())
    except FileExistsError:
        raise BlindError(f"{dst.name} exists: an audit copy is written once") from None
    return dst


def bound_session(st, att, stream, store, agent) -> tuple[list, list, dict, list]:
    """Bind a call's two records: the stream the dispatcher wrote (the audit transcript) and Claude Code's
    session store (the cross-check, which alone carries the dispatch text, the agent and the system prompt).
    Raises Lost when the record cannot be trusted; returns (stream events, store events, identity, problems),
    the problems being the agent's own (they make the attempt invalid, not lost)."""
    try:
        sevs = load_transcript(stream)
    except BlindError:
        raise Lost("no-result") from None
    init = next((e for e in sevs if e.get("type") == "system" and e.get("subtype") == "init"), None)
    if init is None or init.get("session_id") != att["session_id"] or \
            any(e.get("session_id") not in (None, att["session_id"]) for e in sevs):
        raise Lost("unbound")
    if not any(e.get("type") == "result" for e in sevs):
        raise Lost("no-result")
    if store is None or not Path(store).exists():
        raise Lost("store-missing")
    try:
        tevs = load_transcript(store)
    except BlindError:
        raise Lost("store-missing") from None
    try:
        bind_transcript(tevs, dispatch=st["dispatch"], session_id=att["session_id"])
    except BlindError:
        raise Lost("unbound") from None
    if tool_calls(sevs) != tool_calls(tevs) or final_text(sevs) != final_text(tevs):
        raise Lost("store-mismatch")
    ident = identity(tevs)
    ident["stream"] = {"model": init.get("model"), "tools": sorted(init.get("tools") or []),
                       "cwd_is_folder": os.path.realpath(init.get("cwd") or "") == os.path.realpath(st["folder"])}
    probs = identity_problems(ident, agent)
    if ident["stream"]["model"] != agent["model"] or ident["stream"]["tools"] != ["Read"]:
        probs.append("the stream's session is not the pinned model with Read only")
    if not ident["stream"]["cwd_is_folder"]:
        probs.append("the session did not run in the folder")
    ids, answers = [], []
    for msg, b in _blocks(sevs):
        if msg.get("id") not in ids:
            ids.append(msg.get("id"))
        if b.get("type") == "text" and "{" in (b.get("text") or "") and msg.get("id") not in answers:
            answers.append(msg.get("id"))
    ident["model_turns"] = len(ids)
    if len(ids) > agent["max_turns"]:
        probs.append(f"{len(ids)} model turns, above the agent's maxTurns ({agent['max_turns']})")
    if answers != ids[-1:]:
        probs.append("the answer is not exactly one JSON message, the last one")
    return sevs, tevs, ident, probs


def parse_output(text: str) -> dict:
    """The agent's single JSON document (a ```json fence around it is allowed, nothing else)."""
    s = (text or "").strip()
    m = re.fullmatch(r"```(?:json)?\s*\n(.*)\n\s*```", s, re.S)
    if m:
        s = m.group(1).strip()
    if not s.startswith("{") or not s.endswith("}"):
        raise BlindError("the output is not a single JSON object")
    d = loads_strict(s)
    if not isinstance(d, dict):
        raise BlindError("the output is not a JSON object")
    return d


def extra_fields(d: dict, allowed) -> list[str]:
    n = len(set(d) - set(allowed))
    return [f"{n} unexpected field(s)"] if n else []


# --- briefs -------------------------------------------------------------------------------------
def render_brief(template: str, values: dict) -> str:
    """Fill every `{{NAME}}` exactly; refuse a missing or unused value, or a value that holds a placeholder."""
    names = set(PLACEHOLDER.findall(template))
    missing, unused = names - set(values), set(values) - names
    if missing:
        raise BlindError(f"missing value(s) for {sorted(missing)}")
    if unused:
        raise BlindError(f"unused value(s) {sorted(unused)}")
    for k, v in values.items():
        if PLACEHOLDER.search(v):
            raise BlindError(f"the value for {k} holds a placeholder")
    return PLACEHOLDER.sub(lambda m: values[m.group(1)], template)


def q2_options(path) -> list[str]:
    d = loads_strict(Path(path).read_text(encoding="utf-8"))
    opts = d.get("options") if isinstance(d, dict) and d.get("schema") == Q2_SCHEMA else None
    if not isinstance(opts, list) or not opts or not all(isinstance(o, str) and o.strip() for o in opts):
        raise BlindError(f"{Path(path).name}: want schema {Q2_SCHEMA} with a list of options")
    if opts[-2:] != [NOTHING, CANT_TELL]:
        raise BlindError(f"{Path(path).name}: the last two options must be {NOTHING!r} and {CANT_TELL!r}")
    return opts


def q2_block(path) -> str:
    return "\n".join(f"- {o}" for o in q2_options(path))


def render_sealed_brief(template, q2_path, out, *, sealed_root=SEALED) -> dict:
    """Write a rater brief with the Q2 options filled in. Sealed material: refused outside `sealed_root`.
    Written once."""
    out = Path(out)
    try:
        out.resolve().relative_to(Path(sealed_root).resolve())
    except ValueError:
        raise BlindError("a rendered rater brief holds the Q2 options: write it under sealed/") from None
    if out.exists():
        raise BlindError(f"{out.name} exists: a sealed brief is rendered once (at Gate R)")
    text = render_brief(Path(template).read_text(encoding="utf-8"), {"Q2_OPTIONS": q2_block(q2_path)})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return {"out": str(out), "sha256": sha256_path(out), "template_sha256": sha256_path(template),
            "q2_sha256": sha256_path(q2_path)}


# --- contact sheets (the cue rater's input) -------------------------------------------------------
def sheet_times(duration: float, per_second: int = 2) -> list[float]:
    """Frame times for a contact sheet: `per_second` a second, each at the middle of its slot."""
    n = int(round(duration * per_second))
    if n < 1:
        raise BlindError(f"a {duration} s clip gives no frames")
    return [round((k + 0.5) / per_second, 6) for k in range(n)]


def contact_sheets(frames, times, *, cols=3, rows=3, tile=(640, 360)) -> list[np.ndarray]:
    """Tiles in reading order, each labelled with its time in seconds; empty tiles are mid grey."""
    import cv2
    tw, th = tile
    per = cols * rows
    pad = max(2, tw // 160)
    scale = 0.8 * tw / 640
    sheets = []
    for start in range(0, len(frames), per):
        sheet = np.full((rows * th, cols * tw, 3), SHEET_GREY, np.uint8)
        for j, (f, t) in enumerate(zip(frames[start:start + per], times[start:start + per])):
            r, c = divmod(j, cols)
            img = resize(f, (th, tw)).copy()
            label = f"{t:.2f} s"
            (w, h), base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
            cv2.rectangle(img, (0, 0), (w + 2 * pad, h + base + 2 * pad), (255, 255, 255), -1)
            cv2.putText(img, label, (pad, pad + h), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 1, cv2.LINE_AA)
            sheet[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = img
        sheets.append(sheet)
    return sheets


# --- the rater ----------------------------------------------------------------------------------
RATER_KINDS = ("probe-draft", "study-baseline", "study-clips")
# `rescue`: deviation D1 (Aaron, 10 Nov 2026, call 139; PREREGISTRATION §24): the keyframe rescue's rubric 1 (§14) is
# answered by the blind rater, and the registered set had no round for it once the probe round had closed.
ROUNDS = {"probe": "probe-draft", "rescue": "probe-draft", "draft-1": "probe-draft", "draft-2": "probe-draft",
          "study-baseline": "study-baseline", "study-clips": "study-clips"}


def rater_fields(kind: str, q2: list[str]) -> dict:
    """The answer fields per rater brief, each with its options (Q1 is public; Q2 is the sealed list)."""
    from rating.prepare import Q1_OPTIONS
    q1 = list(Q1_OPTIONS)
    table = {"probe-draft": {"leaves_place": ["Yes", "No", CANT_TELL], "reacted_to": q1, "did": list(q2)},
             "study-baseline": {"q1b": q1, "q2b": list(q2)},
             "study-clips": {"q1": q1, "q2": list(q2)}}
    if kind not in table:
        raise BlindError(f"rater kind {kind!r}: want one of {RATER_KINDS}")
    return table[kind]


def rater_ledger_path(round_id) -> Path:
    if round_id not in ROUNDS:
        raise BlindError(f"round {round_id!r}: want one of {sorted(ROUNDS)}")
    return Path(LOGS) / "rater" / f"{round_id}.json"


def panel_hashes() -> dict:
    """{ref: panel sha256} from the sealed rating manifest that rating/prepare.py writes."""
    p = Path(SEALED) / "rating-manifest.json"
    if not p.exists():
        raise BlindError("sealed/rating-manifest.json is missing: build the studies first (rating/prepare.py)")
    return {i["ref"]: i["panel_sha256"] for i in loads_strict(p.read_text(encoding="utf-8"))["items"]}


def build_rater_folder(items, *, round_id: str, brief, root=None) -> dict:
    """The cue rater's folder for one of the fixed rounds. `items`: [{ref, sheets}] (probe, drafts),
    [{ref, panel}] (study-baseline), [{ref, panel, sheets}] (study-clips). A ref names one rendered output
    (its file's SHA-256 is the safe choice), and the ledger holds the hash of the round's refs: a second
    round over the same refs is refused. A study `panel` is the baseline panel's file, copied byte for
    byte, and must hash to the panel in sealed/rating-manifest.json. Item codes are drawn here from a fresh
    salt; the code -> ref map stays in the sealed folder map; items.txt is shuffled by a logged seed."""
    kind = ROUNDS.get(round_id) or rater_ledger_path(round_id)
    lp = rater_ledger_path(round_id)
    require_clean_or_new(lp)
    require_clean_or_new(registry_path())
    refs_in = sorted(str(it.get("ref")) for it in items)
    refs_sha = sha256_json(refs_in)
    for other in sorted((Path(LOGS) / "rater").glob("*.json")):
        if other != lp and json.loads(other.read_text(encoding="utf-8")).get("refs_sha256") == refs_sha:
            raise BlindError(f"round {round_id}: another round already rates exactly these items")
    log = json.loads(lp.read_text(encoding="utf-8")) if lp.exists() else {
        "schema": "p47-rater-ledger/2", "round": round_id, "kind": kind, "brief_sha256": sha256_path(brief),
        "agent_sha256": sha256_path(RATER), "refs_sha256": refs_sha, **new_step()}
    if log["brief_sha256"] != sha256_path(brief) or log["refs_sha256"] != refs_sha:
        raise BlindError(f"round {round_id}: the brief or the items differ from the ledger's")
    check_registry(log, f"rater-{kind}", round_id)
    check_can_prepare(log, f"round {round_id}")
    need = {"probe-draft": {"ref", "sheets"}, "study-baseline": {"ref", "panel"},
            "study-clips": {"ref", "panel", "sheets"}}[kind]
    panels = panel_hashes() if "panel" in need else {}
    salt, seed = secrets.token_hex(16), secrets.token_hex(8)
    files, entries, refs = {RATER_BRIEF_NAME: Path(brief).read_bytes()}, {}, {}
    for it in items:
        if set(it) != need:
            raise BlindError(f"a {kind} item needs exactly {sorted(need)}")
        ref = str(it["ref"])
        if ref in refs.values():
            raise BlindError("two items share a ref")
        c = "q" + sha256_bytes(f"{salt}:{ref}".encode())[:9]
        if c in refs:
            raise BlindError("a code collision; prepare again")
        refs[c] = ref
        names = []
        if "panel" in it:
            data = Path(it["panel"]).read_bytes()
            if panels.get(ref) != sha256_bytes(data):
                raise BlindError("a reference picture is not the baseline panel the study shows")
            names.append(f"{c}.ref.png" if kind == "study-clips" else f"{c}.png")
            files[names[-1]] = data
        if "sheets" in it:
            if not it["sheets"]:
                raise BlindError("an item has no contact sheets")
            for k, sh in enumerate(it["sheets"], 1):
                names.append(f"{c}-{k}.png")
                files[names[-1]] = png_bytes(sh)
        entries[c] = names
    if not entries:
        raise BlindError("no items")
    order = sorted(entries, key=lambda c: sha256_bytes(f"{seed}:{c}".encode()))
    files["items.txt"] = "".join(f"{c}: {' '.join(entries[c])}\n" for c in order).encode()
    code = new_code()
    folder = Path(root or NEUTRAL_ROOT) / code
    inv = write_folder(folder, files)
    dispatch = dispatch_prompt(folder.resolve(), RATER_BRIEF_NAME)
    st = {"schema": "p47-blind-folder/2", "kind": f"rater-{kind}", "id": round_id, "code": code, "codes": order,
          "refs": refs, "salt": salt, "order_seed": seed, "folder": str(folder.resolve()), "inventory": inv,
          "brief_sha256": sha256_path(brief), "agent": str(Path(RATER).resolve()), "dispatch": dispatch,
          "ledger": {"path": str(lp.resolve()), "step": None}, "transcripts": str(SEALED_TRANSCRIPTS)}
    write_state(SEALED_STATE, code, st)
    register(st["kind"], round_id, code)
    log["attempts"].append({**prepared_attempt(code, dispatch, inv), "order_seed": seed, "n_items": len(order)})
    save_json(lp, log)
    commit_ledger(lp, st["kind"], code, "prepared")
    return st


def record_rater(code: str, stream, store, *, q2_path) -> dict:
    """Check a cue-rater attempt. The answers go under sealed/machine-rater/ (they hold Q2 labels); the
    ledger, committed in addendum A3, gets the read log (agent-chosen paths as hashes), problems and hashes."""
    st = read_state(SEALED_STATE, code)
    if not st.get("kind", "").startswith("rater-"):
        raise BlindError(f"{code} is not a rater folder")
    out = Path(SEALED) / "machine-rater" / f"{code}.json"
    if out.exists():
        raise BlindError(f"{out.name} exists: one record per folder")
    log, step = ledger_load(st)
    att = find_attempt(step, code)
    agent = agent_spec(st["agent"])
    sevs, tevs, ident, probs = bound_session(st, att, stream, store, agent)
    kept = {"transcript_sha256": sha256_path(keep_transcript(stream, code, st["transcripts"])),
            "store_sha256": sha256_path(keep_transcript(store, code, st["transcripts"], ".store.jsonl"))}
    folder = Path(st["folder"])
    if inventory(folder) != st["inventory"]:
        probs.append("the folder changed after it was written")
    rl = read_log(folder, sevs, [r["name"] for r in st["inventory"]], context_evs=tevs)
    probs += attempt_problems(rl, RATER_BRIEF_NAME)
    if rl["unread"]:
        probs.append(f"{len(rl['unread'])} file(s) never read")
    text = final_text(sevs)
    parsed = None
    try:
        parsed = parse_output(text)
        probs += validate_choices(parsed, st["codes"], rater_fields(st["kind"][len("rater-"):], q2_options(q2_path)))
    except BlindError as e:
        probs.append(str(e))
    valid = not probs
    rec = {"schema": "p47-machine-rater/1", "code": code, "kind": st["kind"], "round": st["id"],
           "brief_sha256": st["brief_sha256"], "agent_sha256": agent["sha256"], "q2_sha256": sha256_path(q2_path),
           "refs": st["refs"], "output": parsed, "output_sha256": sha256_bytes(text.encode()), "problems": probs,
           "valid": valid}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    att.update(status="recorded", recorded_utc=now(), read_log=rl, identity=ident, problems=probs, valid=valid,
               output_sha256=rec["output_sha256"], q2_sha256=rec["q2_sha256"], **kept)
    if valid:
        step["result"] = {"status": "rated", "code": code}
    close_if_spent(step)
    ledger_save(st, log)
    return rec


def validate_choices(out: dict, codes, fields: dict) -> list[str]:
    """Problems with a rater's output: `{"items": {code: {field: option}}, "notes": str}`, every code once,
    every field one of its options exactly. Agent-chosen keys are counted, never echoed."""
    probs = extra_fields(out, {"items", "notes"})
    if not isinstance(out.get("notes", ""), str):
        probs.append("notes is not a string")
    items = out.get("items")
    if not isinstance(items, dict):
        return probs + ["no items object"]
    for c in codes:
        if c not in items:
            probs.append(f"{c}: missing")
    stray = [c for c in items if c not in codes]
    if stray:
        probs.append(f"{len(stray)} item(s) not in this folder")
    for c in codes:
        ans = items.get(c)
        if ans is None:
            continue
        if not isinstance(ans, dict) or set(ans) != set(fields):
            probs.append(f"{c}: want exactly the fields {sorted(fields)}")
            continue
        for k, opts in fields.items():
            if ans[k] not in opts:
                probs.append(f"{c}.{k}: not one of the options")
    return probs


# --- CLI ----------------------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python seam/blind.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render-brief", help="fill a rater brief template's Q2 options (sealed output)")
    r.add_argument("--template", required=True)
    r.add_argument("--q2", default=str(SEALED / "q2-options.json"))
    r.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        print(json.dumps(render_sealed_brief(a.template, a.q2, a.out), sort_keys=True))
    except (BlindError, OSError) as e:
        print(f"blind: refuse: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    sys.exit(main())
