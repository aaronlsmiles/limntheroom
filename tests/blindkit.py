"""Test helpers: the two records of a blind call, in the shapes a bare `claude -p` session writes (checked
against real ones, 3 Nov 2026): the stream-json events the dispatcher writes, and Claude Code's session
store; the dispatch step that binds them; and a commit helper for the custody's git checks."""
import json
import os
import subprocess
from pathlib import Path

from seam import blind

SID = "11111111-1111-1111-1111-111111111111"


PER_MESSAGE = 1     # reads per assistant message; a real agent batches its reads (tools/rehearse.py sets 10)


def _calls(st, reads):
    out = []
    for i, n in enumerate(reads):
        fp = n if os.path.isabs(str(n)) else str(Path(st["folder"]) / n)
        out.append((f"m{i // PER_MESSAGE}", {"type": "tool_use", "id": f"r{i}", "name": "Read", "input": {"file_path": fp}}))
    return out


def store(path, st, *, reads, answer, session_id=SID, agent_name=None, model=None, first=None, prompt=None,
          tools=("Read",), extra=(), interim=()):
    spec = blind.agent_spec(st["agent"])
    evs = [{"type": "agent-setting", "agentSetting": agent_name or spec["name"], "sessionId": session_id},
           {"type": "user", "sessionId": session_id,
            "message": {"role": "user", "content": st["dispatch"] if first is None else first}},
           {"type": "attachment", "sessionId": session_id,
            "attachment": {"type": "prompt_snapshot", "systemPrompt": [spec["prompt"] if prompt is None else prompt],
                           "tools": [{"name": t} for t in tools]}}]
    evs += list(extra)
    for mid, block in _calls(st, reads):
        evs.append({"type": "assistant", "sessionId": session_id,
                    "message": {"id": mid, "role": "assistant", "model": model or spec["model"], "content": [block]}})
    for k, text in enumerate(interim):
        evs.append({"type": "assistant", "sessionId": session_id,
                    "message": {"id": f"i{k}", "role": "assistant", "model": model or spec["model"],
                                "content": [{"type": "text", "text": text}]}})
    evs.append({"type": "assistant", "sessionId": session_id,
                "message": {"id": "end", "role": "assistant", "model": model or spec["model"],
                            "content": [{"type": "text", "text": answer}]}})
    Path(path).write_text("\n".join(json.dumps(e) for e in evs) + "\n")
    return Path(path)


def stream(path, st, *, reads, answer, session_id=SID, model=None, tools=("Read",), cwd=None, interim=(), result=True):
    spec = blind.agent_spec(st["agent"])
    evs = [{"type": "system", "subtype": "init", "session_id": session_id, "model": model or spec["model"],
            "tools": list(tools), "cwd": cwd or st["folder"]}]
    for mid, block in _calls(st, reads):
        evs.append({"type": "assistant", "session_id": session_id,
                    "message": {"id": mid, "model": model or spec["model"], "content": [block]}})
        evs.append({"type": "user", "session_id": session_id,
                    "message": {"content": [{"type": "tool_result", "tool_use_id": block["id"]}]}})
    for k, text in enumerate(interim):
        evs.append({"type": "assistant", "session_id": session_id,
                    "message": {"id": f"i{k}", "model": model or spec["model"], "content": [{"type": "text", "text": text}]}})
    evs.append({"type": "assistant", "session_id": session_id,
                "message": {"id": "end", "model": model or spec["model"], "content": [{"type": "text", "text": answer}]}})
    if result:
        evs.append({"type": "result", "subtype": "success", "num_turns": len(reads) + 1, "session_id": session_id})
    Path(path).write_text("\n".join(json.dumps(e) for e in evs) + "\n")
    return Path(path)


def dispatched(st, session_id=SID):
    blind.mark_dispatched(st, session_id=session_id, command_sha256="c" * 64, agent=blind.agent_spec(st["agent"]))
    return session_id


def all_files(st, brief=blind.BRIEF_NAME):
    names = [r["name"] for r in st["inventory"]]
    return [brief] + sorted(n for n in names if n != brief)


STORE_KW = ("agent_name", "first", "prompt", "extra")


def run(record_fn, st, tmp_path, answer, *, reads=None, name="t", stream_kw=None, store_kw=None, **kw):
    """Mark dispatched, write the bound stream and store, record them."""
    sid = dispatched(st)
    reads = all_files(st) if reads is None else reads
    common = {k: kw.pop(k) for k in ("model", "tools", "interim") if k in kw}
    s = stream(Path(tmp_path) / f"{name}-{st['code']}.stream.jsonl", st, reads=reads, answer=answer, session_id=sid,
               **{**common, **(stream_kw or {})})
    t = store(Path(tmp_path) / f"{name}-{st['code']}.store.jsonl", st, reads=reads, answer=answer, session_id=sid,
              **{**common, **{k: kw.pop(k) for k in STORE_KW if k in kw}, **(store_kw or {})})
    try:
        return record_fn(st["code"], s, t, **kw)
    finally:                                  # as seam/dispatch.py does after every attempt
        log, step = blind.ledger_load(st)
        status = next(a["status"] for a in step["attempts"] if a["code"] == st["code"])
        blind.commit_ledger(st["ledger"]["path"], st["kind"], st["code"], status)


def commit(msg="ledgers"):
    root = Path(blind.GIT_ROOT)
    git = ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(git + ["add", "-A", "."], check=True, capture_output=True)
    subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", msg], check=True)


def custody_chain(tmp, render, *, creature, frame):
    """A complete, committed blind custody for a synthetic render (pick at an even `frame`, place, check,
    final track). Returns the prompt file and what the pair's meta must carry."""
    import numpy as np
    from seam import frame_pick, masks, points
    tmp = Path(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    creature = np.asarray(creature, bool)
    n, h, w = creature.shape
    frames = np.zeros((n, h, w, 3), np.uint8)
    home = np.zeros((h, w), bool)
    home[: max(2, h // 8), : max(2, w // 8)] = True
    st = frame_pick.build_folder(frames, render=render, home=home, video_sha256="v" * 64, size=(h, w),
                                 stride=2)     # custody fixtures keep the stride-2 arithmetic below
    run(frame_pick.record, st, tmp, json.dumps({"pick": frame // 2 + 1}), name="pick")
    kw = dict(render=render, home=home, video_sha256="v" * 64)
    st = points.build_render_folder(frames, step="place", **kw)
    run(points.record, st, tmp, json.dumps({"x": w / 2, "y": h / 2}), name="place")
    first = tmp / f"{render}.first.npz"
    masks.save_masks(first, {"creature": creature}, take=render, extra={
        "prompts_sha256": blind.sha256_path(Path(points.PROMPTS) / "render" / f"{render}.p1.json"), "video_sha256": "v" * 64})
    st = points.build_render_folder(frames, step="check", masks_path=first, **kw)
    run(points.record, st, tmp, '{"covers": true}', name="check")
    final = Path(points.PROMPTS) / "render" / f"{render}.json"
    mp = tmp / f"{render}.track.npz"
    masks.save_masks(mp, {"creature": creature}, take=render,
                     extra={"prompts_sha256": blind.sha256_path(final), "video_sha256": "v" * 64})
    points.record_track(render, mp)
    commit()
    return {"prompts": final, "meta": pair_meta(render, creature, final, mp)}


def pair_meta(render, creature, prompts, track, video_sha256="v" * 64):
    """The custody fields seam/render_pair.py writes, for a pair whose creature is `creature` as it stands
    (unwarped, as the synthetic custody chains use it)."""
    from seam import masks
    return {"render": render, "render_mask_digest": masks.mask_digest({"creature": creature}),
            "render_mask_file_sha256": blind.sha256_path(track), "prompts_sha256": blind.sha256_path(prompts),
            "video_sha256": video_sha256, "gate": {"pass": True, "sha256": "g" * 64},
            "creature_digest": masks.mask_digest({"creature": creature})}
