"""seam/frame_pick.py: the blind prompt-frame pick (calls 106, 108): ledger, registry, binding and checks."""
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from blindkit import SID, all_files, commit, dispatched, run, store, stream
from seam import blind, frame_pick

SMALL = (54, 96)
H, W = 72, 128


def frames(n=11):
    return np.stack([np.full((H, W, 3), (10 * i) % 250, np.uint8) for i in range(n)])


def home():
    m = np.zeros((H, W), bool)
    m[20:40, 10:30] = True
    return m


def prep(render="t01-ink", n=11):
    return frame_pick.build_folder(frames(n), render=render, home=home(), video_sha256="v" * 64, size=SMALL)


def rec(st, tmp_path, answer, **kw):
    return run(frame_pick.record, st, tmp_path, answer, **kw)


def ledger(render="t01-ink"):
    return json.loads(frame_pick.log_path(render).read_text())


# --- the folder ---------------------------------------------------------------------------------
def test_folder_holds_the_brief_the_list_and_outlined_stills():
    st = prep()
    folder = Path(st["folder"])
    assert folder.parent == Path(blind.NEUTRAL_ROOT).resolve()
    assert sorted(p.name for p in folder.iterdir()) == sorted([blind.BRIEF_NAME, "stills.txt"] + [f"{k:03d}.png" for k in range(1, 5)])
    assert [s["frame"] for s in st["stills"]] == [0, 3, 6, 9]                 # every 3rd analysis frame (call 135)
    assert ledger()["stride"] == 3
    import cv2
    assert (cv2.imread(str(folder / "001.png")).sum(axis=2) > 100).any()       # the dashed outline on a black frame


def test_dashed_outline_marks_only_the_border():
    drawn = blind.dashed_outline(np.zeros((H, W, 3), np.uint8), home()).any(axis=2)
    assert drawn.any() and not drawn[28:32, 18:22].any() and drawn.sum() < drawn.size * 0.1


def test_prepare_writes_a_prepared_attempt_and_a_registry_row():
    st = prep()
    a = ledger()["attempts"][0]
    assert a["status"] == "prepared" and a["code"] == st["code"]
    assert a["inventory_sha256"] == blind.sha256_json(st["inventory"])
    assert blind.registry_codes("prompt-frame", "t01-ink") == [st["code"]]


def test_no_second_folder_while_one_is_unrecorded_and_each_folder_counts(tmp_path):
    st = prep()
    with pytest.raises(blind.BlindError, match="unrecorded"):
        prep()
    rec(st, tmp_path, "no json")
    st2 = prep()
    rec(st2, tmp_path, "still no", name="u")
    assert ledger()["result"]["status"] == "failed"
    with pytest.raises(blind.BlindError, match="closed"):
        prep()


# --- forks and rewinds (round 2, C1) -------------------------------------------------------------
def test_no_command_takes_another_ledger_directory():
    for flag in ("--log-dir", "--state", "--pick-log", "--points-log"):
        assert flag not in Path(frame_pick.__file__).read_text()


def test_a_rewound_ledger_is_detected_by_the_registry(tmp_path):
    st = prep()
    rec(st, tmp_path, '{"pick": 2}')
    commit("first pick")
    led = frame_pick.log_path("t01-ink")
    led.write_text(json.dumps({**ledger(), "attempts": [], "result": None}))     # as if `git checkout` an earlier ledger
    with pytest.raises(blind.BlindError, match="changes"):
        prep()
    with pytest.raises(blind.BlindError, match="registry"):
        frame_pick.verify("t01-ink")


def test_require_committed():
    led = Path(blind.LOGS) / "prompt-frame" / "t09-ink.json"
    led.parent.mkdir(parents=True, exist_ok=True)
    led.write_text("{}\n")
    with pytest.raises(blind.BlindError, match="not committed"):
        blind.require_committed(led)
    with pytest.raises(blind.BlindError, match="never committed"):
        blind.require_clean_or_new(led)
    commit()
    blind.require_committed(led)
    led.write_text(led.read_text() + " ")
    with pytest.raises(blind.BlindError, match="changes"):
        blind.require_committed(led)
    with pytest.raises(blind.BlindError, match="not a ledger"):
        blind.require_committed(Path("/tmp/elsewhere.json"))


def test_prepare_commits_the_ledger_and_registry_with_a_fixed_message():
    st = prep()
    blind.require_committed(frame_pick.log_path("t01-ink"))
    blind.require_committed(blind.registry_path())
    msg = subprocess.run(["git", "-C", str(blind.GIT_ROOT), "log", "-1", "--format=%B"], capture_output=True,
                         text=True).stdout
    assert msg.startswith(f"blind ledger: prompt-frame {st['code']} prepared")
    assert "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" in msg
    names = subprocess.run(["git", "-C", str(blind.GIT_ROOT), "show", "--name-only", "--format=", "HEAD"],
                           capture_output=True, text=True).stdout.split()
    assert sorted(names) == ["agents/logs/prompt-frame/t01-ink.json", "agents/logs/registry.jsonl"]


def test_audit_copies_are_never_overwritten(tmp_path):
    src = tmp_path / "a.jsonl"
    src.write_text("x\n")
    blind.keep_transcript(src, "bcode", tmp_path / "out")
    with pytest.raises(blind.BlindError, match="exists"):
        blind.keep_transcript(src, "bcode", tmp_path / "out")


# --- binding (C2 and round 2) --------------------------------------------------------------------
def test_record_needs_a_dispatched_attempt(tmp_path):
    st = prep()
    s = stream(tmp_path / "s.jsonl", st, reads=all_files(st), answer='{"pick": 2}')
    t = store(tmp_path / "t.jsonl", st, reads=all_files(st), answer='{"pick": 2}')
    with pytest.raises(blind.BlindError, match="prepared"):
        frame_pick.record(st["code"], s, t)


@pytest.mark.parametrize("case,reason", [("empty-stream", "no-result"), ("no-result", "no-result"),
                                         ("no-store", "store-missing"), ("hinted", "unbound"),
                                         ("other-session", "unbound"), ("mismatch", "store-mismatch")])
def test_untrustworthy_records_are_lost_not_attempts(tmp_path, case, reason):
    st = prep()
    dispatched(st)
    reads = all_files(st)
    s = stream(tmp_path / "s.jsonl", st, reads=reads, answer='{"pick": 2}', result=case != "no-result",
               session_id="other" if case == "other-session" else SID)
    if case == "empty-stream":
        s.write_bytes(b"")
    t = store(tmp_path / "t.jsonl", st, reads=reads[:-1] if case == "mismatch" else reads, answer='{"pick": 2}',
              first=st["dispatch"] + " Hint: the second still." if case == "hinted" else None)
    with pytest.raises(blind.Lost) as e:
        frame_pick.record(st["code"], s, None if case == "no-store" else t)
    assert e.value.reason == reason
    assert ledger()["attempts"][0]["status"] == "dispatched"


@pytest.mark.parametrize("kw,match", [({"store_kw": {"agent_name": "general-purpose"}}, "agent"),
                                      ({"model": "claude-sonnet-5-5"}, "model"),
                                      ({"store_kw": {"prompt": "You are helpful."}}, "system prompt"),
                                      ({"tools": ("Read", "Bash")}, "Read"),
                                      ({"stream_kw": {"cwd": "/somewhere/else"}}, "folder")])
def test_wrong_agent_model_prompt_tools_or_folder_invalidate(tmp_path, kw, match):
    st = prep()
    a = rec(st, tmp_path, '{"pick": 2}', **kw)["attempts"][0]
    assert not a["valid"] and any(match in p for p in a["problems"])


def test_a_context_file_outside_the_allowlist_invalidates(tmp_path):
    st = prep()
    ctx = {"type": "attachment", "sessionId": SID, "attachment": {"type": "instructions", "files": [
        {"path": str(Path.home() / ".claude" / "CLAUDE.md"), "type": "User", "content": "global"},
        {"path": "/some/project/CLAUDE.md", "type": "Project", "content": "names the project"}]}}
    a = rec(st, tmp_path, '{"pick": 2}', extra=[ctx])["attempts"][0]
    assert not a["valid"] and any("context file" in p for p in a["problems"])
    assert a["read_log"]["context_files"][0]["sha256"] == blind.sha256_bytes(b"global")


def test_both_records_are_kept_for_audit(tmp_path):
    st = prep()
    a = rec(st, tmp_path, "garbage")["attempts"][0]
    assert a["transcript_sha256"] == blind.sha256_path(Path(blind.TRANSCRIPTS) / f"{st['code']}.jsonl")
    assert a["store_sha256"] == blind.sha256_path(Path(blind.TRANSCRIPTS) / f"{st['code']}.store.jsonl")


# --- turns and the one answer (round 2, minor) ---------------------------------------------------
def test_more_model_turns_than_max_turns_invalidate(tmp_path):
    st = frame_pick.build_folder(frames(135), render="t01-ink", home=home(), video_sha256="v" * 64, size=SMALL)
    a = rec(st, tmp_path, '{"pick": "none"}')["attempts"][0]                    # 45 stills: 48 single-read turns > 40
    assert not a["valid"] and any("maxTurns" in p for p in a["problems"])
    assert a["identity"]["model_turns"] == 48


def test_a_revised_answer_is_invalid_but_plain_narration_is_not(tmp_path):
    st = prep()
    a = rec(st, tmp_path, '{"pick": 3}', interim=['{"pick": 2}'])["attempts"][0]
    assert not a["valid"] and any("exactly one JSON message" in p for p in a["problems"])
    st2 = frame_pick.build_folder(frames(), render="t02-ink", home=home(), video_sha256="v" * 64, size=SMALL)
    a2 = rec(st2, tmp_path, '{"pick": 3}', interim=["Reading the next batch."], name="n")["attempts"][0]
    assert a2["valid"], a2["problems"]


# --- answers ------------------------------------------------------------------------------------
@pytest.mark.parametrize("out,want", [({"pick": 3}, (3, [])), ({"pick": "none"}, (None, [])), ({"pick": 3, "unreadable": []}, (3, []))])
def test_parse_pick_ok(out, want):
    assert frame_pick.parse_pick(out, 6) == want


@pytest.mark.parametrize("out", [{"pick": 0}, {"pick": 7}, {"pick": True}, {"pick": 2.0}, {"pick": "None"},
                                 {}, {"pick": 3, "note": "x"}, {"pick": 3, "unreadable": [2]}])
def test_parse_pick_problems(out):
    assert frame_pick.parse_pick(out, 6)[1]


def test_record_valid_pick_maps_still_to_frame(tmp_path):
    st = prep()
    log = rec(st, tmp_path, '{"pick": 4}', reads=[blind.BRIEF_NAME, "stills.txt", "001.png", "002.png", "003.png", "004.png"])
    assert log["result"] == {"status": "picked", "still": 4, "frame": 9}
    assert log["attempts"][0]["identity"]["agents"] == ["blind-frame-picker"]


def test_every_still_up_to_the_pick_must_be_read(tmp_path):
    st = prep()
    a = rec(st, tmp_path, '{"pick": 4}', reads=[blind.BRIEF_NAME, "stills.txt", "001.png", "003.png", "004.png"])["attempts"][0]
    assert not a["valid"] and any("002.png" in p for p in a["problems"])


def test_duplicate_keys_are_refused(tmp_path):
    st = prep()
    assert not rec(st, tmp_path, '{"pick": 2, "pick": 5}')["attempts"][0]["valid"]


SECRET = "the creature hops away from the glass"


def test_free_text_in_a_key_or_a_path_never_reaches_the_ledger(tmp_path):
    st = prep()
    rec(st, tmp_path, json.dumps({"pick": 2, SECRET: 1}))
    st2 = prep()
    inside = str(Path(st2["folder"]) / f"{SECRET}.png")
    rec(st2, tmp_path, '{"pick": 2}', reads=all_files(st2) + [inside, f"/tmp/{SECRET}.txt"], name="p")
    led = ledger()
    assert SECRET not in json.dumps(led)
    assert led["attempts"][1]["read_log"]["outside"]["count"] == 1 and led["attempts"][1]["read_log"]["unlisted"]["count"] == 1


# --- verify -------------------------------------------------------------------------------------
def write_prompts(path, frame):
    path.write_text(json.dumps({"take": "t01", "objects": {"creature": [{"frame": frame, "x": 10.0, "y": 10.0, "positive": True}]}}))
    return path


def test_verify(tmp_path):
    st = prep()
    with pytest.raises(blind.BlindError, match="unrecorded"):
        frame_pick.verify("t01-ink")
    rec(st, tmp_path, '{"pick": 4}')
    assert frame_pick.verify("t01-ink") == 9
    assert frame_pick.verify("t01-ink", prompts=write_prompts(tmp_path / "p.json", 9)) == 9
    with pytest.raises(blind.BlindError, match="prompt frame"):
        frame_pick.verify("t01-ink", prompts=write_prompts(tmp_path / "q.json", 5))
    with pytest.raises(blind.BlindError, match="no pick"):
        frame_pick.verify("t02-ink")


def test_none_and_verify(tmp_path):
    rec(prep(), tmp_path, '{"pick": "none"}')
    assert frame_pick.verify("t01-ink") is None


@pytest.mark.parametrize("name", ["t01-x", "ink", "golden", "paper-1", "limnx"])
def test_forbidden_words_in_paths(name):
    with pytest.raises(blind.BlindError):
        blind.check_folder_path(Path(blind.NEUTRAL_ROOT) / name)


def test_only_the_neutral_root(tmp_path):
    with pytest.raises(blind.BlindError, match="neutral root"):
        blind.check_folder_path(tmp_path / "bfolder")


# --- review finding 5 (call 135): every 3rd frame, or the smallest larger stride whose folder fits the payload budget ----
def test_strides_are_three_to_six():
    assert frame_pick.STRIDES == (3, 4, 5, 6) and frame_pick.STRIDE == 3


def test_the_stride_steps_up_until_the_folder_fits(monkeypatch):
    monkeypatch.setattr(blind, "payload_bytes", lambda files: 1000 * sum(n.endswith(".png") for n in files))
    monkeypatch.setattr(blind, "PAYLOAD_BUDGET", 3000)
    st = prep(n=11)                                                             # stride 3: 4 stills, 4,000 > 3,000
    assert [s["frame"] for s in st["stills"]] == [0, 4, 8] and ledger()["stride"] == 4


def test_no_stride_that_fits_refuses_before_any_attempt(monkeypatch):
    monkeypatch.setattr(blind, "payload_bytes", lambda files: 10**9)
    with pytest.raises(blind.BlindError, match="stride"):
        prep(n=11)
    assert not frame_pick.log_path("t01-ink").exists()
